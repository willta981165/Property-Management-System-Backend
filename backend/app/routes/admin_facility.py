# [GateGuard facts]
# 1. Importers/callers: app/__init__.py line 64 registers admin_facility_bp from this file.
# 2. This is an EDIT to an existing file — no new file created; no duplicate purpose.
# 3. Affected APIs: GET/POST/PUT/DELETE /api/admin/facilities/:id
#    Log data fields: admin_id(int), facility_id(int), facility_name(str), org_id(int), is_active(bool).
#    No passwords or user PII written to log.
# 4. User instruction verbatim: "我現在要建立log機制 包含以上的部分 然後admin 住戶 公設 的api
#    然後我要在本地產一個資料夾 這個資料夾會放我logging.txt 異常資訊都會放在這個txt內"
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models.facility import Facility
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
        description: 公設列表
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
          required: [name, open_time, close_time, max_capacity]
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
            close_time:
              type: string
              example: "22:00"
            max_capacity:
              type: integer
              example: 15
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

    open_time = _parse_time(data.get('open_time') or '')
    close_time = _parse_time(data.get('close_time') or '')
    if not open_time or not close_time:
        return jsonify({'error': '開放時段格式錯誤，應為 HH:MM'}), 400
    if close_time <= open_time:
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
        description: 公設詳情
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
        open_time = _parse_time(
            data.get('open_time') or facility.open_time.strftime('%H:%M')
        )
        close_time = _parse_time(
            data.get('close_time') or facility.close_time.strftime('%H:%M')
        )
        if not open_time or not close_time:
            return jsonify({'error': '時段格式錯誤，應為 HH:MM'}), 400
        if close_time <= open_time:
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
