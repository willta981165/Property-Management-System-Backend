# [GateGuard facts]
# 1. Registered in app/__init__.py at /api/admin
# 2. NEW file — no existing admin_repair route exists
# 3. PATCH updates repair_tickets: status(enum), admin_reply(text),
#    replied_by_admin_id(int), replied_at(datetime UTC).
#    POST category: repair_categories(organization_id, name, icon, sort_order).
#    Log: admin_id(int), ticket_id(int), org_id(int). No PII.
# 4. User: "在管理員的頁面 可以看到住戶追加的報修單 也可以透過維修類別去查詢
#    管理員也可以回覆 然後可以儲存 該狀態會同步反映在住戶端 也可以新增維修類別"
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models.repair_category import RepairCategory
from ..models.repair_ticket import RepairTicket, RepairStatus
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

admin_repair_bp = Blueprint('admin_repair', __name__)


# ── 維修類別管理 ──

@admin_repair_bp.route('/repair-categories', methods=['GET'])
@admin_required
def list_repair_categories():
    """
    取得維修類別列表（管理員）
    ---
    tags:
      - Admin - Repair
    security:
      - Bearer: []
    responses:
      200:
        description: 類別列表
    """
    categories = (
        RepairCategory.query
        .filter_by(organization_id=g.org_id)
        .order_by(RepairCategory.sort_order.asc(), RepairCategory.id.asc())
        .all()
    )
    return jsonify({'categories': [c.to_dict() for c in categories]}), 200


@admin_repair_bp.route('/repair-categories', methods=['POST'])
@admin_required
def create_repair_category():
    """
    新增維修類別
    ---
    tags:
      - Admin - Repair
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name]
          properties:
            name:
              type: string
              example: 水電
            icon:
              type: string
              example: plumbing
    responses:
      201:
        description: 類別建立成功
      400:
        description: 類別名稱為必填
    """
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': '類別名稱為必填'}), 400

    max_order = db.session.query(
        db.func.max(RepairCategory.sort_order)
    ).filter_by(organization_id=g.org_id).scalar()

    category = RepairCategory(
        organization_id=g.org_id,
        name=name,
        icon=(data.get('icon') or '').strip() or None,
        sort_order=(max_order or 0) + 1,
    )
    db.session.add(category)
    db.session.commit()

    app_logger.info(
        f"[REPAIR] Category created | admin_id={g.admin.id} | "
        f"category_id={category.id} | name={name} | org_id={g.org_id}"
    )
    return jsonify({'message': '類別建立成功', 'category': category.to_dict()}), 201


@admin_repair_bp.route('/repair-categories/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_repair_category(category_id):
    """
    刪除維修類別
    ---
    tags:
      - Admin - Repair
    security:
      - Bearer: []
    parameters:
      - in: path
        name: category_id
        type: integer
        required: true
    responses:
      200:
        description: 類別已刪除
      400:
        description: 此類別仍有報修單，無法刪除
      404:
        description: 找不到類別
    """
    category = RepairCategory.query.filter_by(
        id=category_id, organization_id=g.org_id
    ).first_or_404()

    has_tickets = RepairTicket.query.filter_by(category_id=category_id).first()
    if has_tickets:
        return jsonify({'error': '此類別仍有報修單，無法刪除'}), 400

    category_name = category.name
    db.session.delete(category)
    db.session.commit()

    app_logger.warning(
        f"[REPAIR] Category deleted | admin_id={g.admin.id} | "
        f"category_id={category_id} | name={category_name} | org_id={g.org_id}"
    )
    return jsonify({'message': '類別已刪除'}), 200


# ── 報修工單管理 ──

@admin_repair_bp.route('/repairs', methods=['GET'])
@admin_required
def list_repairs():
    """
    取得報修工單列表（管理員）
    ---
    tags:
      - Admin - Repair
    security:
      - Bearer: []
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, in_progress, completed]
        description: 篩選狀態，不帶則回傳全部
      - in: query
        name: category_id
        type: integer
        description: 篩選維修類別
    responses:
      200:
        description: 工單列表
    """
    query = RepairTicket.query.filter_by(organization_id=g.org_id)

    status_filter = request.args.get('status')
    if status_filter:
        try:
            query = query.filter(RepairTicket.status == RepairStatus(status_filter))
        except ValueError:
            return jsonify({'error': '無效的狀態，可選 pending, in_progress, completed'}), 400

    category_id_filter = request.args.get('category_id')
    if category_id_filter:
        try:
            query = query.filter(RepairTicket.category_id == int(category_id_filter))
        except (ValueError, TypeError):
            return jsonify({'error': '無效的 category_id'}), 400

    tickets = query.order_by(RepairTicket.created_at.desc()).all()
    return jsonify({'tickets': [t.to_dict() for t in tickets]}), 200


@admin_repair_bp.route('/repairs/<int:ticket_id>', methods=['GET'])
@admin_required
def get_repair(ticket_id):
    """
    取得報修工單詳情（管理員）
    ---
    tags:
      - Admin - Repair
    security:
      - Bearer: []
    parameters:
      - in: path
        name: ticket_id
        type: integer
        required: true
    responses:
      200:
        description: 工單詳情
      404:
        description: 找不到工單
    """
    ticket = RepairTicket.query.filter_by(
        id=ticket_id, organization_id=g.org_id
    ).first_or_404()
    return jsonify({'ticket': ticket.to_dict()}), 200


@admin_repair_bp.route('/repairs/<int:ticket_id>', methods=['PATCH'])
@admin_required
def update_repair(ticket_id):
    """
    更新報修工單狀態與回覆（管理員）
    ---
    tags:
      - Admin - Repair
    security:
      - Bearer: []
    parameters:
      - in: path
        name: ticket_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            status:
              type: string
              enum: [pending, in_progress, completed]
            admin_reply:
              type: string
              example: 已收到您的報修申請，維修人員將於明日上午前往處理。
    responses:
      200:
        description: 工單已更新
      400:
        description: 欄位驗證錯誤
      404:
        description: 找不到工單
    """
    ticket = RepairTicket.query.filter_by(
        id=ticket_id, organization_id=g.org_id
    ).first_or_404()

    data = request.get_json(silent=True) or {}
    changed = False

    if 'status' in data:
        try:
            ticket.status = RepairStatus(data['status'])
        except ValueError:
            return jsonify({'error': '無效的狀態，可選 pending, in_progress, completed'}), 400
        changed = True

    if 'admin_reply' in data:
        reply = (data['admin_reply'] or '').strip()
        ticket.admin_reply = reply or None
        if reply:
            ticket.replied_by_admin_id = g.admin.id
            ticket.replied_at = datetime.now(timezone.utc)
        changed = True

    if not changed:
        return jsonify({'error': '請提供 status 或 admin_reply'}), 400

    db.session.commit()

    app_logger.info(
        f"[REPAIR] Updated | admin_id={g.admin.id} | ticket_id={ticket_id} | "
        f"status={ticket.status.value} | org_id={g.org_id}"
    )
    return jsonify({'message': '工單已更新', 'ticket': ticket.to_dict()}), 200
