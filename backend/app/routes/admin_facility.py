# [GateGuard facts]
# 1. Caller: app/__init__.py:110 registers admin_facility_bp at /api/admin/facilities
# 2. EDIT existing file — open_time/close_time now optional; added FacilitySlot import;
#    added 3 slot management routes.
# 3. New slot APIs: GET/POST /api/admin/facilities/:id/slots,
#    DELETE /api/admin/facilities/:id/slots/:slot_id
#    FacilitySlot fields: facility_id(FK), start_time(HH:MM), end_time(HH:MM), sort_order(int)
#    Log: admin_id(int), facility_id(int), slot_id(int), org_id(int). No PII.
# 4. User verbatim: "管理員追加公設的時候 可以自訂時間區段 像是 8:00~9:00 9:00~10:00
#    10:00~11:00 這樣追加 然後用戶在預約公設的時候也可以看到各個時間區段"
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models.facility import Facility
from ..models.facility_slot import FacilitySlot
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

admin_facility_bp = Blueprint('admin_facility', __name__)


def _parse_time(time_str):
    try:
        return datetime.strptime(time_str.strip(), '%H:%M').time()
    except (ValueError, AttributeError):
        return None


@admin_facility_bp.route('', methods=['GET'])
@admin_required
def list_facilities():
    """
    取得公設列表（管理員）
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    responses:
      200:
        description: 公設列表（含各公設 slots）
    """
    facilities = (
        Facility.query
        .filter_by(organization_id=g.org_id)
        .order_by(Facility.sort_order.asc(), Facility.id.asc())
        .all()
    )
    return jsonify({'facilities': [f.to_dict() for f in facilities]}), 200


@admin_facility_bp.route('', methods=['POST'])
@admin_required
def create_facility():
    """
    新增公設
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name, max_capacity]
          properties:
            name:
              type: string
              example: 頂樓無邊際泳池
            icon:
              type: string
              example: pool
            is_active:
              type: boolean
              default: true
            open_time:
              type: string
              example: "08:00"
              description: 選填，純顯示用，預約時段由 slots 管理
            close_time:
              type: string
              example: "22:00"
              description: 選填，需與 open_time 同時提供或省略
            max_capacity:
              type: integer
              example: 15
              description: 各時段共用的最大容納人數
            rules:
              type: string
              example: "1. 請穿著泳裝入池。"
    responses:
      201:
        description: 公設建立成功
      400:
        description: 欄位驗證錯誤
    """
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': '公設名稱為必填'}), 400

    ot_str = data.get('open_time') or ''
    ct_str = data.get('close_time') or ''
    open_time = _parse_time(ot_str) if ot_str else None
    close_time = _parse_time(ct_str) if ct_str else None

    if bool(open_time) != bool(close_time):
        return jsonify({'error': '開放時段與關閉時段需同時提供或省略'}), 400
    if open_time and close_time and close_time <= open_time:
        return jsonify({'error': '關閉時段必須晚於開放時段'}), 400

    try:
        max_capacity = int(data.get('max_capacity'))
        if max_capacity < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': '最大容納人數須為正整數'}), 400

    max_order = db.session.query(
        db.func.max(Facility.sort_order)
    ).filter_by(organization_id=g.org_id).scalar()
    next_order = (max_order or 0) + 1

    facility = Facility(
        organization_id=g.org_id,
        name=name,
        icon=(data.get('icon') or '').strip() or None,
        is_active=bool(data.get('is_active', True)),
        open_time=open_time,
        close_time=close_time,
        max_capacity=max_capacity,
        rules=(data.get('rules') or '').strip() or None,
        sort_order=next_order,
    )
    db.session.add(facility)
    db.session.commit()

    app_logger.info(
        f"[FACILITY] Created | admin_id={g.admin.id} | facility_id={facility.id} | "
        f"name={name} | org_id={g.org_id}"
    )
    return jsonify({'message': '公設建立成功', 'facility': facility.to_dict()}), 201


@admin_facility_bp.route('/<int:facility_id>', methods=['GET'])
@admin_required
def get_facility(facility_id):
    """
    取得單一公設詳情（管理員）
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    parameters:
      - in: path
        name: facility_id
        type: integer
        required: true
    responses:
      200:
        description: 公設詳情（含 slots）
      404:
        description: 找不到公設
    """
    facility = Facility.query.filter_by(
        id=facility_id, organization_id=g.org_id
    ).first_or_404()
    return jsonify({'facility': facility.to_dict()}), 200


@admin_facility_bp.route('/<int:facility_id>', methods=['PUT'])
@admin_required
def update_facility(facility_id):
    """
    更新公設資訊
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    parameters:
      - in: path
        name: facility_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            is_active:
              type: boolean
            open_time:
              type: string
              example: "08:00"
            close_time:
              type: string
              example: "22:00"
            max_capacity:
              type: integer
            rules:
              type: string
            sort_order:
              type: integer
    responses:
      200:
        description: 公設資料已更新
      400:
        description: 欄位驗證錯誤
      404:
        description: 找不到公設
    """
    facility = Facility.query.filter_by(
        id=facility_id, organization_id=g.org_id
    ).first_or_404()
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return jsonify({'error': '公設名稱不可為空'}), 400
        facility.name = name

    if 'icon' in data:
        facility.icon = (data['icon'] or '').strip() or None

    if 'is_active' in data:
        new_active = bool(data['is_active'])
        if not new_active:
            app_logger.warning(
                f"[FACILITY] Disabled | admin_id={g.admin.id} | "
                f"facility_id={facility_id} | org_id={g.org_id}"
            )
        facility.is_active = new_active

    if 'open_time' in data or 'close_time' in data:
        ot_str = data.get('open_time') or ''
        ct_str = data.get('close_time') or ''
        open_time = _parse_time(ot_str) if ot_str else None
        close_time = _parse_time(ct_str) if ct_str else None
        if 'open_time' not in data:
            open_time = facility.open_time
        if 'close_time' not in data:
            close_time = facility.close_time
        if open_time and close_time and close_time <= open_time:
            return jsonify({'error': '關閉時段必須晚於開放時段'}), 400
        facility.open_time = open_time
        facility.close_time = close_time

    if 'max_capacity' in data:
        try:
            val = int(data['max_capacity'])
            if val < 1:
                raise ValueError
            facility.max_capacity = val
        except (ValueError, TypeError):
            return jsonify({'error': '最大容納人數須為正整數'}), 400

    if 'rules' in data:
        facility.rules = (data['rules'] or '').strip() or None

    if 'sort_order' in data:
        try:
            facility.sort_order = int(data['sort_order'])
        except (ValueError, TypeError):
            return jsonify({'error': 'sort_order 須為整數'}), 400

    db.session.commit()
    app_logger.info(
        f"[FACILITY] Updated | admin_id={g.admin.id} | "
        f"facility_id={facility_id} | org_id={g.org_id}"
    )
    return jsonify({'message': '公設資料已更新', 'facility': facility.to_dict()}), 200


@admin_facility_bp.route('/<int:facility_id>', methods=['DELETE'])
@admin_required
def delete_facility(facility_id):
    """
    刪除公設
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    parameters:
      - in: path
        name: facility_id
        type: integer
        required: true
    responses:
      200:
        description: 公設已刪除
      404:
        description: 找不到公設
    """
    facility = Facility.query.filter_by(
        id=facility_id, organization_id=g.org_id
    ).first_or_404()
    facility_name = facility.name
    db.session.delete(facility)
    db.session.commit()
    app_logger.warning(
        f"[FACILITY] Deleted | admin_id={g.admin.id} | facility_id={facility_id} | "
        f"name={facility_name} | org_id={g.org_id}"
    )
    return jsonify({'message': '公設已刪除'}), 200


# ── 時段管理 (Slot CRUD) ──

@admin_facility_bp.route('/<int:facility_id>/slots', methods=['GET'])
@admin_required
def list_slots(facility_id):
    """
    取得公設所有時段（管理員）
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    parameters:
      - in: path
        name: facility_id
        type: integer
        required: true
    responses:
      200:
        description: 時段列表
      404:
        description: 找不到公設
    """
    Facility.query.filter_by(
        id=facility_id, organization_id=g.org_id
    ).first_or_404()
    slots = (
        FacilitySlot.query
        .filter_by(facility_id=facility_id)
        .order_by(FacilitySlot.sort_order.asc(), FacilitySlot.id.asc())
        .all()
    )
    return jsonify({'slots': [s.to_dict() for s in slots]}), 200


@admin_facility_bp.route('/<int:facility_id>/slots', methods=['POST'])
@admin_required
def create_slot(facility_id):
    """
    新增公設時段
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    parameters:
      - in: path
        name: facility_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [start_time, end_time]
          properties:
            start_time:
              type: string
              example: "08:00"
            end_time:
              type: string
              example: "09:00"
    responses:
      201:
        description: 時段建立成功
      400:
        description: 格式錯誤
      404:
        description: 找不到公設
    """
    Facility.query.filter_by(
        id=facility_id, organization_id=g.org_id
    ).first_or_404()
    data = request.get_json(silent=True) or {}

    start_time = _parse_time(data.get('start_time') or '')
    end_time = _parse_time(data.get('end_time') or '')
    if not start_time or not end_time:
        return jsonify({'error': '時段格式錯誤，應為 HH:MM'}), 400
    if end_time <= start_time:
        return jsonify({'error': '結束時間必須晚於開始時間'}), 400

    max_order = db.session.query(db.func.max(FacilitySlot.sort_order))\
                          .filter_by(facility_id=facility_id).scalar()
    slot = FacilitySlot(
        facility_id=facility_id,
        start_time=start_time,
        end_time=end_time,
        sort_order=(max_order or 0) + 1,
    )
    db.session.add(slot)
    db.session.commit()

    app_logger.info(
        f"[FACILITY] Slot created | admin_id={g.admin.id} | "
        f"facility_id={facility_id} | slot_id={slot.id} | "
        f"{start_time.strftime('%H:%M')}~{end_time.strftime('%H:%M')} | org_id={g.org_id}"
    )
    return jsonify({'message': '時段建立成功', 'slot': slot.to_dict()}), 201


@admin_facility_bp.route('/<int:facility_id>/slots/<int:slot_id>', methods=['DELETE'])
@admin_required
def delete_slot(facility_id, slot_id):
    """
    刪除公設時段
    ---
    tags:
      - Admin - Facility
    security:
      - Bearer: []
    parameters:
      - in: path
        name: facility_id
        type: integer
        required: true
      - in: path
        name: slot_id
        type: integer
        required: true
    responses:
      200:
        description: 時段已刪除
      404:
        description: 找不到公設或時段
    """
    Facility.query.filter_by(
        id=facility_id, organization_id=g.org_id
    ).first_or_404()
    slot = FacilitySlot.query.filter_by(
        id=slot_id, facility_id=facility_id
    ).first_or_404()
    db.session.delete(slot)
    db.session.commit()

    app_logger.warning(
        f"[FACILITY] Slot deleted | admin_id={g.admin.id} | "
        f"facility_id={facility_id} | slot_id={slot_id} | org_id={g.org_id}"
    )
    return jsonify({'message': '時段已刪除'}), 200
