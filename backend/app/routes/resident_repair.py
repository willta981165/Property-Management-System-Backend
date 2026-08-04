# [GateGuard facts]
# 1. Registered in app/__init__.py at /api
# 2. NEW file — no existing resident_repair route exists
# 3. APIs: GET /api/repair-categories, GET /api/repairs, POST /api/repairs,
#    GET /api/repairs/<id>. Log: resident_id(int), ticket_id(int),
#    category_id(int), org_id(int). No PII.
# 4. User: resident submits repair ticket, views own list and detail
from datetime import date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from ..extensions import db
from ..models.repair_category import RepairCategory
from ..models.repair_ticket import RepairTicket, RepairStatus
from ..models.resident import Resident
from ..utils.logger import app_logger

resident_repair_bp = Blueprint('resident_repair', __name__)

VALID_SLOTS = {'09:00-12:00', '13:00-17:00', '18:00-21:00'}


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    org_id = claims.get('org_id')
    resident = db.session.get(Resident, int(get_jwt_identity()))
    return resident, org_id


@resident_repair_bp.route('/repair-categories', methods=['GET'])
@jwt_required()
def list_repair_categories():
    """
    取得維修類別列表（住戶用，供表單選擇）
    ---
    tags:
      - Resident - Repair
    security:
      - Bearer: []
    responses:
      200:
        description: 類別列表
    """
    claims = get_jwt()
    org_id = claims.get('org_id')

    categories = (
        RepairCategory.query
        .filter_by(organization_id=org_id)
        .order_by(RepairCategory.sort_order.asc(), RepairCategory.id.asc())
        .all()
    )
    return jsonify({'categories': [c.to_dict() for c in categories]}), 200


@resident_repair_bp.route('/repairs', methods=['GET'])
@jwt_required()
def list_my_repairs():
    """
    取得我的報修紀錄
    ---
    tags:
      - Resident - Repair
    security:
      - Bearer: []
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, in_progress, completed]
        description: 篩選狀態，不帶則回傳全部
    responses:
      200:
        description: 報修紀錄列表
      403:
        description: 僅住戶可使用
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    query = RepairTicket.query.filter_by(
        resident_id=resident.id,
        organization_id=org_id,
    )

    status_filter = request.args.get('status')
    if status_filter:
        try:
            query = query.filter(RepairTicket.status == RepairStatus(status_filter))
        except ValueError:
            return jsonify({'error': '無效的狀態，可選 pending, in_progress, completed'}), 400

    tickets = query.order_by(RepairTicket.created_at.desc()).all()
    return jsonify({'tickets': [t.to_dict() for t in tickets]}), 200


@resident_repair_bp.route('/repairs', methods=['POST'])
@jwt_required()
def create_repair():
    """
    住戶新增報修申請
    ---
    tags:
      - Resident - Repair
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [category_id, title, description]
          properties:
            category_id:
              type: integer
              example: 1
            title:
              type: string
              example: 水龍頭漏水
            description:
              type: string
              example: 廚房水龍頭持續滴水，已無法關閉。
            appointment_date:
              type: string
              example: "2024-08-15"
            appointment_slot:
              type: string
              example: "09:00-12:00"
              description: 可選 09:00-12:00 / 13:00-17:00 / 18:00-21:00
    responses:
      201:
        description: 報修申請已提交
      400:
        description: 欄位驗證錯誤
      403:
        description: 僅住戶可使用
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403
    if not resident.is_active:
        return jsonify({'error': '帳號已停用'}), 403

    data = request.get_json(silent=True) or {}

    category_id = data.get('category_id')
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()

    if not category_id or not title or not description:
        return jsonify({'error': '維修類別、標題、問題描述皆為必填'}), 400

    category = RepairCategory.query.filter_by(
        id=category_id, organization_id=org_id
    ).first()
    if not category:
        return jsonify({'error': '找不到維修類別'}), 404

    appointment_date = None
    appointment_slot_val = None

    date_str = (data.get('appointment_date') or '').strip()
    slot_str = (data.get('appointment_slot') or '').strip()

    if date_str:
        try:
            appointment_date = date.fromisoformat(date_str)
            if appointment_date < date.today():
                return jsonify({'error': '預約日期不能早於今天'}), 400
        except ValueError:
            return jsonify({'error': '日期格式錯誤，應為 YYYY-MM-DD'}), 400

    if slot_str:
        if slot_str not in VALID_SLOTS:
            return jsonify({'error': f'無效的時段，可選 {", ".join(sorted(VALID_SLOTS))}'}), 400
        appointment_slot_val = slot_str

    ticket = RepairTicket(
        organization_id=org_id,
        resident_id=resident.id,
        category_id=category_id,
        title=title,
        description=description,
        appointment_date=appointment_date,
        appointment_slot=appointment_slot_val,
    )
    db.session.add(ticket)
    db.session.commit()

    app_logger.info(
        f"[REPAIR] Created | resident_id={resident.id} | ticket_id={ticket.id} | "
        f"category_id={category_id} | org_id={org_id}"
    )
    return jsonify({'message': '報修申請已提交', 'ticket': ticket.to_dict()}), 201


@resident_repair_bp.route('/repairs/<int:ticket_id>', methods=['GET'])
@jwt_required()
def get_repair(ticket_id):
    """
    取得報修詳情（住戶）
    ---
    tags:
      - Resident - Repair
    security:
      - Bearer: []
    parameters:
      - in: path
        name: ticket_id
        type: integer
        required: true
    responses:
      200:
        description: 報修詳情
      403:
        description: 無權查看此報修單
      404:
        description: 找不到報修單
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    ticket = RepairTicket.query.filter_by(
        id=ticket_id, organization_id=org_id
    ).first_or_404()

    if ticket.resident_id != resident.id:
        return jsonify({'error': '無權查看此報修單'}), 403

    return jsonify({'ticket': ticket.to_dict()}), 200
