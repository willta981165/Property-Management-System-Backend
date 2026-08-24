from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
from sqlalchemy import or_
from ..extensions import db
from ..models.parcel import Parcel, ParcelStatus, ParcelSize
from ..models.resident import Resident
from ..utils.decorators import admin_required
from ..utils.logger import app_logger
from ..utils.parcel_helpers import (
    OVERDUE_DAYS, CLOSED_STATUSES,
    utc_now as _utc_now, make_aware as _aware,
    lazy_overdue_single as _lazy_overdue_single,
    lazy_overdue_batch as _lazy_overdue_batch,
    compute_days as _compute_days,
)

admin_parcel_bp = Blueprint('admin_parcel', __name__)

_CLOSED = CLOSED_STATUSES


def _build_timeline(parcel):
    overdue_at = _aware(parcel.arrived_at) + timedelta(days=OVERDUE_DAYS)
    timeline = [{'status': 'pending', 'label': '已登記', 'at': parcel.created_at.isoformat()}]

    show_overdue = parcel.status in (ParcelStatus.overdue, ParcelStatus.returned, ParcelStatus.abnormal)
    if not show_overdue and parcel.status == ParcelStatus.picked_up:
        pickup_time = _aware(parcel.picked_up_at or parcel.updated_at)
        show_overdue = pickup_time > overdue_at

    if show_overdue:
        timeline.append({'status': 'overdue', 'label': '已逾期', 'at': overdue_at.isoformat()})

    terminal_labels = {
        ParcelStatus.picked_up: '已領取',
        ParcelStatus.returned: '已退回物流',
        ParcelStatus.abnormal: '異常',
    }
    if parcel.status in terminal_labels:
        timeline.append({
            'status': parcel.status.value,
            'label': terminal_labels[parcel.status],
            'at': parcel.updated_at.isoformat(),
        })
    return timeline


@admin_parcel_bp.route('', methods=['GET'])
@admin_required
def list_parcels():
    """
    取得包裹列表（管理員）
    ---
    tags:
      - Admin - Parcel
    security:
      - Bearer: []
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, overdue, closed]
        description: 篩選狀態；closed 包含 picked_up, returned, abnormal
      - in: query
        name: q
        type: string
        description: 搜尋住戶 unit_code 或姓名
    responses:
      200:
        description: 包裹列表
      400:
        description: 無效的狀態
    """
    query = Parcel.query.filter_by(organization_id=g.org_id)

    status_filter = (request.args.get('status') or '').strip()
    if status_filter == 'closed':
        query = query.filter(Parcel.status.in_(list(_CLOSED)))
    elif status_filter:
        try:
            query = query.filter(Parcel.status == ParcelStatus(status_filter))
        except ValueError:
            return jsonify({'error': '無效的狀態，可選 pending, overdue, closed'}), 400

    q = (request.args.get('q') or '').strip()
    if q:
        query = query.join(Resident, Parcel.resident_id == Resident.id).filter(
            or_(
                Resident.unit_code.ilike(f'%{q}%'),
                Resident.name.ilike(f'%{q}%'),
            )
        )

    parcels = query.order_by(Parcel.arrived_at.desc()).all()
    _lazy_overdue_batch(parcels)

    result = []
    for p in parcels:
        days_waiting, _, overdue_days = _compute_days(p)
        d = p.to_dict()
        d['days_waiting'] = days_waiting
        d['overdue_days'] = overdue_days
        result.append(d)

    return jsonify({'parcels': result}), 200


@admin_parcel_bp.route('', methods=['POST'])
@admin_required
def create_parcel():
    """
    登記新包裹（管理員）
    ---
    tags:
      - Admin - Parcel
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [resident_id, logistics_company, size, quantity, arrived_at]
          properties:
            resident_id:
              type: integer
              example: 10
            logistics_company:
              type: string
              example: 黑貓宅急便
            size:
              type: string
              enum: [small, medium, large]
              example: medium
            quantity:
              type: integer
              example: 1
            storage_location:
              type: string
              example: 大廳置物櫃 B3
            notes:
              type: string
              example: 易碎品
            arrived_at:
              type: string
              example: "2026-08-03"
    responses:
      201:
        description: 包裹登記成功
      400:
        description: 欄位驗證錯誤
      404:
        description: 找不到住戶
    """
    data = request.get_json(silent=True) or {}

    resident_id = data.get('resident_id')
    logistics_company = (data.get('logistics_company') or '').strip()
    size_str = (data.get('size') or '').strip()
    quantity_raw = data.get('quantity')
    arrived_at_str = (data.get('arrived_at') or '').strip()

    if not all([resident_id, logistics_company, size_str, quantity_raw is not None, arrived_at_str]):
        return jsonify({'error': 'resident_id, logistics_company, size, quantity, arrived_at 皆為必填'}), 400

    try:
        size = ParcelSize(size_str)
    except ValueError:
        return jsonify({'error': '無效的包裹大小，可選 small, medium, large'}), 400

    try:
        quantity = int(quantity_raw)
        if quantity < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'quantity 必須為正整數'}), 400

    try:
        arrived_at = datetime.strptime(arrived_at_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({'error': 'arrived_at 格式錯誤，應為 YYYY-MM-DD'}), 400

    if arrived_at.date() > _utc_now().date():
        return jsonify({'error': 'arrived_at 不可為未來日期'}), 400

    resident = Resident.query.filter_by(id=resident_id, organization_id=g.org_id).first()
    if not resident:
        return jsonify({'error': '找不到住戶'}), 404

    parcel = Parcel(
        organization_id=g.org_id,
        resident_id=resident_id,
        registered_by_admin_id=g.admin.id,
        logistics_company=logistics_company,
        size=size,
        quantity=quantity,
        storage_location=(data.get('storage_location') or '').strip() or None,
        notes=(data.get('notes') or '').strip() or None,
        arrived_at=arrived_at,
        status=ParcelStatus.pending,
    )
    db.session.add(parcel)
    db.session.flush()

    now = _utc_now()
    parcel.parcel_code = f"PCL-{now.strftime('%Y%m')}{parcel.id:04d}"
    db.session.commit()

    app_logger.info(
        f"[PARCEL] Created | admin_id={g.admin.id} | parcel_id={parcel.id} | "
        f"resident_id={resident_id} | org_id={g.org_id}"
    )
    return jsonify({'message': '包裹登記成功', 'parcel': parcel.to_dict()}), 201


@admin_parcel_bp.route('/residents/search', methods=['GET'])
@admin_required
def search_residents():
    """
    搜尋住戶（登記包裹表單用）
    ---
    tags:
      - Admin - Parcel
    security:
      - Bearer: []
    parameters:
      - in: query
        name: unit_code
        type: string
        required: true
        description: 住戶戶號（模糊搜尋）
    responses:
      200:
        description: 住戶列表
      400:
        description: 缺少搜尋參數
    """
    unit_code = (request.args.get('unit_code') or '').strip()
    if not unit_code:
        return jsonify({'error': '請提供 unit_code 搜尋參數'}), 400

    residents = Resident.query.filter(
        Resident.organization_id == g.org_id,
        Resident.unit_code.ilike(f'%{unit_code}%'),
    ).all()

    return jsonify({
        'residents': [
            {'id': r.id, 'name': r.name, 'unit_code': r.unit_code}
            for r in residents
        ]
    }), 200


@admin_parcel_bp.route('/<int:parcel_id>', methods=['GET'])
@admin_required
def get_parcel(parcel_id):
    """
    取得包裹詳情（管理員）
    ---
    tags:
      - Admin - Parcel
    security:
      - Bearer: []
    parameters:
      - in: path
        name: parcel_id
        type: integer
        required: true
    responses:
      200:
        description: 包裹詳情（含 status_timeline）
      404:
        description: 找不到包裹
    """
    parcel = Parcel.query.filter_by(id=parcel_id, organization_id=g.org_id).first_or_404()
    _lazy_overdue_single(parcel)

    days_waiting, days_remaining, overdue_days = _compute_days(parcel)
    d = parcel.to_dict()
    d['days_waiting'] = days_waiting
    d['days_remaining'] = days_remaining
    d['overdue_days'] = overdue_days
    d['status_timeline'] = _build_timeline(parcel)
    return jsonify(d), 200


@admin_parcel_bp.route('/<int:parcel_id>/status', methods=['PUT'])
@admin_required
def update_parcel_status(parcel_id):
    """
    更新逾期包裹狀態（管理員）
    ---
    tags:
      - Admin - Parcel
    security:
      - Bearer: []
    parameters:
      - in: path
        name: parcel_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [status]
          properties:
            status:
              type: string
              enum: [returned, abnormal]
              example: returned
            abnormal_reason:
              type: string
              example: 住戶地址錯誤，包裹無人認領
    responses:
      200:
        description: 狀態更新成功
      400:
        description: 狀態或欄位驗證錯誤
      404:
        description: 找不到包裹
    """
    parcel = Parcel.query.filter_by(id=parcel_id, organization_id=g.org_id).first_or_404()

    if parcel.status != ParcelStatus.overdue:
        return jsonify({'error': '只能對逾期包裹更新狀態'}), 400

    data = request.get_json(silent=True) or {}
    new_status_str = (data.get('status') or '').strip()

    if new_status_str not in ('returned', 'abnormal'):
        return jsonify({'error': '狀態只接受 returned 或 abnormal'}), 400

    if new_status_str == 'abnormal':
        reason = (data.get('abnormal_reason') or '').strip()
        if not reason:
            return jsonify({'error': 'status 為 abnormal 時，abnormal_reason 為必填'}), 400
        parcel.abnormal_reason = reason

    parcel.status = ParcelStatus(new_status_str)
    db.session.commit()

    app_logger.info(
        f"[PARCEL] Status updated | admin_id={g.admin.id} | parcel_id={parcel_id} | "
        f"status={new_status_str} | org_id={g.org_id}"
    )
    return jsonify({'message': '狀態更新成功', 'parcel': parcel.to_dict()}), 200


@admin_parcel_bp.route('/<int:parcel_id>/pickup', methods=['POST'])
@admin_required
def confirm_pickup(parcel_id):
    """
    確認住戶領取（管理員，含簽名）
    ---
    tags:
      - Admin - Parcel
    security:
      - Bearer: []
    parameters:
      - in: path
        name: parcel_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [signature_data]
          properties:
            signature_data:
              type: string
              example: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg..."
    responses:
      200:
        description: 領取確認成功
      400:
        description: 狀態或欄位驗證錯誤
      404:
        description: 找不到包裹
    """
    parcel = Parcel.query.filter_by(id=parcel_id, organization_id=g.org_id).first_or_404()

    if parcel.status not in (ParcelStatus.pending, ParcelStatus.overdue):
        return jsonify({'error': '只能對待領取或已逾期的包裹執行領取操作'}), 400

    _MAX_SIGNATURE_BYTES = 512_000  # 500 KB

    data = request.get_json(silent=True) or {}
    signature_data = (data.get('signature_data') or '').strip()
    if not signature_data:
        return jsonify({'error': 'signature_data 為必填'}), 400
    if len(signature_data.encode('utf-8')) > _MAX_SIGNATURE_BYTES:
        return jsonify({'error': 'signature_data 超過大小上限（500 KB）'}), 400

    now = _utc_now()
    parcel.status = ParcelStatus.picked_up
    parcel.picked_up_at = now
    parcel.signature_data = signature_data
    db.session.commit()

    app_logger.info(
        f"[PARCEL] Picked up | admin_id={g.admin.id} | parcel_id={parcel_id} | "
        f"resident_id={parcel.resident_id} | org_id={g.org_id}"
    )
    return jsonify({
        'message': '領取確認成功',
        'parcel': {
            'id': parcel.id,
            'parcel_code': parcel.parcel_code,
            'status': parcel.status.value,
            'picked_up_at': parcel.picked_up_at.isoformat(),
        },
    }), 200
