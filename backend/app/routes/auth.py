from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from ..extensions import db
from ..models.admin import Admin
from ..models.resident import Resident

auth_bp = Blueprint('auth', __name__)


def _make_tokens(user_id: int, role: str, user_type: str):
    claims = {'role': role, 'user_type': user_type}
    access_token = create_access_token(identity=user_id, additional_claims=claims)
    refresh_token = create_refresh_token(identity=user_id, additional_claims={'user_type': user_type})
    return access_token, refresh_token


def _get_current_user():
    """從 JWT 取出目前使用者，回傳 (user, user_type)。"""
    claims = get_jwt()
    user_type = claims.get('user_type')
    user_id = get_jwt_identity()
    if user_type == 'admin':
        return Admin.query.get(user_id), 'admin'
    return Resident.query.get(user_id), 'resident'


@auth_bp.route('/admin/register', methods=['POST'])
def admin_register():
    """
    管理員帳號建立
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name, employee_id, department, project_name, email, password, confirm_password]
          properties:
            name:
              type: string
              example: 王小明
            employee_id:
              type: string
              example: ID-0001
            department:
              type: string
              example: 管理部
            project_name:
              type: string
              example: 幸福花園社區
            email:
              type: string
              example: admin@example.com
            password:
              type: string
              example: password123
            confirm_password:
              type: string
              example: password123
    responses:
      201:
        description: 管理員建立成功，回傳 token
        schema:
          type: object
          properties:
            message:
              type: string
            access_token:
              type: string
            refresh_token:
              type: string
            user:
              type: object
      400:
        description: 欄位驗證錯誤
      409:
        description: 員工編號或 email 已被使用
    """
    import re

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    employee_id = (data.get('employee_id') or '').strip()
    department = (data.get('department') or '').strip()
    project_name = (data.get('project_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not all([name, employee_id, department, project_name, email, password, confirm_password]):
        return jsonify({'error': '所有欄位皆為必填'}), 400

    if len(password) < 8:
        return jsonify({'error': '密碼至少需要 8 個字元'}), 400

    if password != confirm_password:
        return jsonify({'error': '兩次輸入的密碼不一致'}), 400

    if not re.match(r'^ID-\d{4}$', employee_id):
        return jsonify({'error': '員工編號格式錯誤，應為 ID-0000'}), 400

    if Admin.query.filter_by(employee_id=employee_id).first():
        return jsonify({'error': '員工編號已被使用'}), 409

    if Admin.query.filter_by(email=email).first():
        return jsonify({'error': 'Email 已被使用'}), 409

    admin = Admin(
        name=name,
        employee_id=employee_id,
        department=department,
        project_name=project_name,
        email=email,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    access_token, refresh_token = _make_tokens(admin.id, 'admin', 'admin')

    return jsonify({
        'message': '管理員帳號建立成功',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': admin.to_dict(),
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    使用者登入（管理員 & 住戶共用）
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [identifier, password]
          properties:
            identifier:
              type: string
              description: 管理員填員工編號或 email；住戶填 unit_code 或手機號碼
              example: ID-0001
            password:
              type: string
              example: password123
    responses:
      200:
        description: 登入成功
        schema:
          type: object
          properties:
            access_token:
              type: string
            refresh_token:
              type: string
            user:
              type: object
      400:
        description: 缺少帳號或密碼
      401:
        description: 帳號或密碼錯誤
      403:
        description: 帳號已停用
    """
    data = request.get_json(silent=True) or {}
    identifier = (data.get('identifier') or '').strip()
    password = data.get('password') or ''

    if not identifier or not password:
        return jsonify({'error': '請輸入帳號與密碼'}), 400

    user = Admin.query.filter(
        (Admin.employee_id == identifier) | (Admin.email == identifier.lower())
    ).first()
    user_type = 'admin'

    if not user:
        user = Resident.query.filter(
            (Resident.unit_code == identifier) | (Resident.phone == identifier)
        ).first()
        user_type = 'resident'

    if not user or not user.check_password(password):
        return jsonify({'error': '帳號或密碼錯誤'}), 401

    if not user.is_active:
        return jsonify({'error': '帳號已停用，請聯絡管理員'}), 403

    role = 'admin' if user_type == 'admin' else user.role.value
    access_token, refresh_token = _make_tokens(user.id, role, user_type)

    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict(),
    }), 200


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    刷新 Access Token
    ---
    tags:
      - Auth
    security:
      - Bearer: []
    parameters:
      - in: header
        name: Authorization
        required: true
        type: string
        description: "格式：Bearer <refresh_token>"
    responses:
      200:
        description: 回傳新的 access_token
        schema:
          type: object
          properties:
            access_token:
              type: string
      401:
        description: refresh_token 無效或帳號已停用
    """
    claims = get_jwt()
    user_type = claims.get('user_type')
    user_id = get_jwt_identity()

    if user_type == 'admin':
        user = Admin.query.get(user_id)
        role = 'admin'
    else:
        user = Resident.query.get(user_id)
        role = user.role.value if user else None

    if not user or not user.is_active:
        return jsonify({'error': '帳號不存在或已停用'}), 401

    access_token = create_access_token(
        identity=user_id,
        additional_claims={'role': role, 'user_type': user_type},
    )
    return jsonify({'access_token': access_token}), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_me():
    """
    取得目前登入使用者的資料
    ---
    tags:
      - Auth
    security:
      - Bearer: []
    responses:
      200:
        description: 使用者資料
        schema:
          type: object
          properties:
            user:
              type: object
      403:
        description: 帳號已停用
    """
    user, _ = _get_current_user()
    if not user or not user.is_active:
        return jsonify({'error': '帳號已停用，請聯絡管理員'}), 403
    return jsonify({'user': user.to_dict()}), 200


@auth_bp.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    """
    修改密碼（管理員 & 住戶共用）
    ---
    tags:
      - Auth
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [current_password, new_password]
          properties:
            current_password:
              type: string
              example: oldpassword
            new_password:
              type: string
              example: newpassword123
            confirm_password:
              type: string
              example: newpassword123
    responses:
      200:
        description: 密碼修改成功
      400:
        description: 欄位驗證錯誤或目前密碼錯誤
      403:
        description: 帳號已停用
    """
    user, user_type = _get_current_user()
    if not user or not user.is_active:
        return jsonify({'error': '帳號已停用，請聯絡管理員'}), 403

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not current_password or not new_password:
        return jsonify({'error': '請填寫所有欄位'}), 400

    min_len = 8 if user_type == 'admin' else 6
    if len(new_password) < min_len:
        return jsonify({'error': f'新密碼至少需要 {min_len} 個字元'}), 400

    if confirm_password and new_password != confirm_password:
        return jsonify({'error': '兩次輸入的密碼不一致'}), 400

    if not user.check_password(current_password):
        return jsonify({'error': '目前密碼錯誤'}), 400

    user.set_password(new_password)
    db.session.commit()
    return jsonify({'message': '密碼修改成功'}), 200
