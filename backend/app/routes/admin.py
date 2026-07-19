# [GateGuard facts]
# 1. Importers/callers: app/__init__.py:62 registers admin_bp from this file.
# 2. This is an EDIT to an existing file — no new file created; no duplicate purpose.
# 3. Affected APIs: GET/POST/PUT/DELETE /api/admin/residents
#    Log data fields: admin_id(int), resident_id(int), unit_code(str), org_id(int), action(str).
#    No passwords or PII (name/phone/email) written to log.
# 4. User verbatim: "我現在要建立log機制 包含以上的部分 然後admin 住戶 公設 的api
#    然後我要在本地產一個資料夾 這個資料夾會放我logging.txt"
from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import get_jwt_identity

from ..extensions import db
from ..models.resident import Resident, ResidentRole
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/residents', methods=['GET'])
@admin_required
def list_residents():
    """
    取得住戶列表
    ---
    tags:
      - Admin
    security:
      - Bearer: []
    parameters:
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: per_page
        type: integer
        default: 20
      - in: query
        name: role
        type: string
        enum: [resident, family]
    responses:
      200:
        description: 住戶列表
      400:
        description: 無效的角色篩選值
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    role_filter = request.args.get('role')

    query = Resident.query.filter_by(organization_id=g.org_id)
    if role_filter:
        try:
            query = query.filter(Resident.role == ResidentRole(role_filter))
        except ValueError:
            return jsonify({'error': '無效的角色篩選值，可選 resident 或 family'}), 400

    paginated = query.order_by(Resident.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'residents': [r.to_dict() for r in paginated.items],
        'total': paginated.total,
        'page': page,
        'pages': paginated.pages,
    }), 200


@admin_bp.route('/residents', methods=['POST'])
@admin_required
def create_resident():
    """
    建立住戶帳號
    ---
    tags:
      - Admin
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name, unit_code, password]
          properties:
            name:
              type: string
              example: 李大華
            unit_code:
              type: string
              example: A101
            phone:
              type: string
              example: "0912345678"
            email:
              type: string
              example: resident@example.com
            password:
              type: string
              example: init1234
            role:
              type: string
              enum: [resident, family]
              default: resident
            notes:
              type: string
    responses:
      201:
        description: 帳號建立成功
      400:
        description: 必填欄位缺少或格式錯誤
      409:
        description: 單位編號、手機或 email 在此建案內已被使用
    """
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    unit_code = (data.get('unit_code') or '').strip()
    phone = (data.get('phone') or '').strip() or None
    email = (data.get('email') or '').strip() or None
    password = (data.get('password') or '').strip()
    role_str = data.get('role', 'resident')
    notes = (data.get('notes') or '').strip() or None

    if not name or not unit_code or not password:
        return jsonify({'error': '姓名、單位編號、初始密碼為必填'}), 400

    try:
        role = ResidentRole(role_str)
    except ValueError:
        return jsonify({'error': '帳號類型無效，可選 resident 或 family'}), 400

    if Resident.query.filter_by(unit_code=unit_code, organization_id=g.org_id).first():
        return jsonify({'error': '單位編號在此建案內已存在'}), 409

    if phone and Resident.query.filter_by(phone=phone, organization_id=g.org_id).first():
        return jsonify({'error': '手機號碼在此建案內已被使用'}), 409

    if email and Resident.query.filter_by(email=email, organization_id=g.org_id).first():
        return jsonify({'error': '電子郵件在此建案內已被使用'}), 409

    resident = Resident(
        organization_id=g.org_id,
        name=name,
        unit_code=unit_code,
        phone=phone,
        email=email,
        role=role,
        notes=notes,
        created_by=get_jwt_identity(),
    )
    resident.set_password(password)
    db.session.add(resident)
    db.session.commit()

    app_logger.info(
        f"[ADMIN] Resident created | admin_id={g.admin.id} | "
        f"resident_id={resident.id} | unit_code={unit_code} | org_id={g.org_id}"
    )
    return jsonify({'message': '帳號建立成功', 'resident': resident.to_dict()}), 201


@admin_bp.route('/residents/<int:resident_id>', methods=['PUT'])
@admin_required
def update_resident(resident_id):
    """
    修改住戶資料 / 重設密碼
    ---
    tags:
      - Admin
    security:
      - Bearer: []
    parameters:
      - in: path
        name: resident_id
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
            unit_code:
              type: string
            phone:
              type: string
            email:
              type: string
            password:
              type: string
              description: 填入則重設密碼
            role:
              type: string
              enum: [resident, family]
            notes:
              type: string
            is_active:
              type: boolean
    responses:
      200:
        description: 帳號更新成功
      404:
        description: 找不到住戶
      409:
        description: 單位編號、手機或 email 已被使用
    """
    resident = Resident.query.filter_by(id=resident_id, organization_id=g.org_id).first_or_404()
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        resident.name = (data['name'] or '').strip()

    if 'unit_code' in data:
        new_val = (data['unit_code'] or '').strip()
        if Resident.query.filter(
            Resident.unit_code == new_val,
            Resident.organization_id == g.org_id,
            Resident.id != resident_id,
        ).first():
            return jsonify({'error': '單位編號在此建案內已存在'}), 409
        resident.unit_code = new_val

    if 'phone' in data:
        new_val = (data['phone'] or '').strip() or None
        if new_val and Resident.query.filter(
            Resident.phone == new_val,
            Resident.organization_id == g.org_id,
            Resident.id != resident_id,
        ).first():
            return jsonify({'error': '手機號碼在此建案內已被使用'}), 409
        resident.phone = new_val

    if 'email' in data:
        new_val = (data['email'] or '').strip() or None
        if new_val and Resident.query.filter(
            Resident.email == new_val,
            Resident.organization_id == g.org_id,
            Resident.id != resident_id,
        ).first():
            return jsonify({'error': '電子郵件在此建案內已被使用'}), 409
        resident.email = new_val

    if 'password' in data and data['password']:
        resident.set_password(data['password'])
        app_logger.warning(
            f"[ADMIN] Resident password reset | admin_id={g.admin.id} | "
            f"resident_id={resident_id} | org_id={g.org_id}"
        )

    if 'role' in data:
        try:
            resident.role = ResidentRole(data['role'])
        except ValueError:
            return jsonify({'error': '帳號類型無效'}), 400

    if 'notes' in data:
        resident.notes = (data['notes'] or '').strip() or None

    if 'is_active' in data:
        new_active = bool(data['is_active'])
        if not new_active:
            app_logger.warning(
                f"[ADMIN] Resident disabled | admin_id={g.admin.id} | "
                f"resident_id={resident_id} | org_id={g.org_id}"
            )
        resident.is_active = new_active

    db.session.commit()
    app_logger.info(
        f"[ADMIN] Resident updated | admin_id={g.admin.id} | "
        f"resident_id={resident_id} | org_id={g.org_id}"
    )
    return jsonify({'message': '帳號更新成功', 'resident': resident.to_dict()}), 200


@admin_bp.route('/residents/<int:resident_id>', methods=['DELETE'])
@admin_required
def delete_resident(resident_id):
    """
    刪除住戶帳號
    ---
    tags:
      - Admin
    security:
      - Bearer: []
    parameters:
      - in: path
        name: resident_id
        type: integer
        required: true
    responses:
      200:
        description: 帳號已刪除
      404:
        description: 找不到住戶
    """
    resident = Resident.query.filter_by(id=resident_id, organization_id=g.org_id).first_or_404()
    unit_code = resident.unit_code
    db.session.delete(resident)
    db.session.commit()
    app_logger.warning(
        f"[ADMIN] Resident deleted | admin_id={g.admin.id} | "
        f"resident_id={resident_id} | unit_code={unit_code} | org_id={g.org_id}"
    )
    return jsonify({'message': '帳號已刪除'}), 200
