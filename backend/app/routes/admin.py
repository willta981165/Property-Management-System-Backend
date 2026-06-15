import random
import string

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity

from ..extensions import db
from ..models.resident import Resident, ResidentRole
from ..utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__)


def _generate_password(length: int = 10) -> str:
    prefix = ''.join(random.choices(string.ascii_uppercase, k=2))
    body = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 3))
    return f"{prefix}-{body}"


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
        description: 篩選角色（不填則回傳全部）
    responses:
      200:
        description: 住戶列表
        schema:
          type: object
          properties:
            residents:
              type: array
              items:
                type: object
            total:
              type: integer
            page:
              type: integer
            pages:
              type: integer
      400:
        description: 無效的角色篩選值
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    role_filter = request.args.get('role')

    query = Resident.query
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
              example: 備註說明
    responses:
      201:
        description: 帳號建立成功
      400:
        description: 必填欄位缺少或格式錯誤
      409:
        description: 單位編號、手機或 email 已被使用
    """
    admin_id = get_jwt_identity()
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

    if Resident.query.filter_by(unit_code=unit_code).first():
        return jsonify({'error': '單位編號已存在'}), 409

    if phone and Resident.query.filter_by(phone=phone).first():
        return jsonify({'error': '手機號碼已被使用'}), 409

    if email and Resident.query.filter_by(email=email).first():
        return jsonify({'error': '電子郵件已被使用'}), 409

    resident = Resident(
        name=name,
        unit_code=unit_code,
        phone=phone,
        email=email,
        role=role,
        notes=notes,
        created_by=admin_id,
    )
    resident.set_password(password)
    db.session.add(resident)
    db.session.commit()

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
    resident = db.get_or_404(Resident, resident_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        resident.name = (data['name'] or '').strip()

    if 'unit_code' in data:
        new_val = (data['unit_code'] or '').strip()
        if Resident.query.filter(Resident.unit_code == new_val, Resident.id != resident_id).first():
            return jsonify({'error': '單位編號已存在'}), 409
        resident.unit_code = new_val

    if 'phone' in data:
        new_val = (data['phone'] or '').strip() or None
        if new_val and Resident.query.filter(Resident.phone == new_val, Resident.id != resident_id).first():
            return jsonify({'error': '手機號碼已被使用'}), 409
        resident.phone = new_val

    if 'email' in data:
        new_val = (data['email'] or '').strip() or None
        if new_val and Resident.query.filter(Resident.email == new_val, Resident.id != resident_id).first():
            return jsonify({'error': '電子郵件已被使用'}), 409
        resident.email = new_val

    if 'password' in data and data['password']:
        resident.set_password(data['password'])

    if 'role' in data:
        try:
            resident.role = ResidentRole(data['role'])
        except ValueError:
            return jsonify({'error': '帳號類型無效'}), 400

    if 'notes' in data:
        resident.notes = (data['notes'] or '').strip() or None

    if 'is_active' in data:
        resident.is_active = bool(data['is_active'])

    db.session.commit()
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
    resident = db.get_or_404(Resident, resident_id)
    db.session.delete(resident)
    db.session.commit()
    return jsonify({'message': '帳號已刪除'}), 200


@admin_bp.route('/generate-password', methods=['GET'])
@admin_required
def generate_password():
    """
    產生隨機初始密碼
    ---
    tags:
      - Admin
    security:
      - Bearer: []
    responses:
      200:
        description: 隨機密碼
        schema:
          type: object
          properties:
            password:
              type: string
              example: AB-xK3mPq7
    """
    return jsonify({'password': _generate_password()}), 200
