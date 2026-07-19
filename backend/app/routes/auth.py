# Importers/callers: app/__init__.py registers auth_bp from this file.
# Affected APIs: POST /admin/register, POST /login, POST /refresh, GET /me, PUT /change-password
# Data written to log: ip, user_id, user_type, org_id, identifier (no passwords logged)
# User instruction verbatim: "我現在要建立log機制 包含以上的部分 然後admin 住戶 公設 的api"
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from ..extensions import db
from ..models.organization import Organization
from ..models.admin import Admin
from ..models.resident import Resident
from ..utils.logger import app_logger

auth_bp = Blueprint('auth', __name__)


def _make_tokens(user_id: int, role: str, user_type: str, org_id: int):
    claims = {'role': role, 'user_type': user_type, 'org_id': org_id}
    access_token = create_access_token(identity=user_id, additional_claims=claims)
    refresh_token = create_refresh_token(
        identity=user_id,
        additional_claims={'user_type': user_type, 'org_id': org_id},
    )
    return access_token, refresh_token


def _get_current_user():
    claims = get_jwt()
    user_type = claims.get('user_type')
    user_id = get_jwt_identity()
    if user_type == 'admin':
        return db.session.get(Admin, user_id), 'admin'
    return db.session.get(Resident, user_id), 'resident'


def _get_org(org_code: str):
    return Organization.query.filter_by(org_code=org_code.upper(), is_active=True).first()


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
          required: [org_code, name, employee_id, department, password, confirm_password]
          properties:
            org_code:
              type: string
              example: HAPPY-0001
            name:
              type: string
              example: 王小明
            employee_id:
              type: string
              example: ID-0001
            department:
              type: string
              example: 管理部
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
      400:
        description: 欄位驗證錯誤
      404:
        description: 建案代碼無效
      409:
        description: 員工編號或 email 在此建案內已被使用
    """
    import re

    data = request.get_json(silent=True) or {}
    org_code = (data.get('org_code') or '').strip()
    name = (data.get('name') or '').strip()
    employee_id = (data.get('employee_id') or '').strip()
    department = (data.get('department') or '').strip()
    email = (data.get('email') or '').strip().lower() or None
    password = data.get('password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not all([org_code, name, employee_id, department, password, confirm_password]):
        return jsonify({'error': '建案代碼、姓名、員工編號、部門、密碼皆為必填'}), 400

    org = _get_org(org_code)
    if not org:
        return jsonify({'error': '建案代碼無效'}), 404

    if len(password) < 8:
        return jsonify({'error': '密碼至少需要 8 個字元'}), 400

    if password != confirm_password:
        return jsonify({'error': '兩次輸入的密碼不一致'}), 400

    if not re.match(r'^ID-\d{4}$', employee_id):
        return jsonify({'error': '員工編號格式錯誤，應為 ID-0000'}), 400

    if Admin.query.filter_by(employee_id=employee_id, organization_id=org.id).first():
        return jsonify({'error': '員工編號在此建案內已被使用'}), 409

    if email and Admin.query.filter_by(email=email, organization_id=org.id).first():
        return jsonify({'error': 'Email 在此建案內已被使用'}), 409

    admin = Admin(
        organization_id=org.id,
        name=name,
        employee_id=employee_id,
        department=department,
        email=email,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    app_logger.info(
        f"[AUTH] Admin registered | ip={ip} | user_id={admin.id} | "
        f"employee_id={employee_id} | org_id={org.id}"
    )

    access_token, refresh_token = _make_tokens(admin.id, 'admin', 'admin', org.id)

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
          required: [org_code, identifier, password]
          properties:
            org_code:
              type: string
              description: 建案代碼
              example: HAPPY-0001
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
      400:
        description: 缺少欄位或建案代碼無效
      401:
        description: 帳號或密碼錯誤
      403:
        description: 帳號已停用
    """
    data = request.get_json(silent=True) or {}
    org_code = (data.get('org_code') or '').strip()
    identifier = (data.get('identifier') or '').strip()
    password = data.get('password') or ''

    if not org_code or not identifier or not password:
        return jsonify({'error': '請輸入建案代碼、帳號與密碼'}), 400

    org = _get_org(org_code)
    if not org:
        return jsonify({'error': '建案代碼無效'}), 400

    user = Admin.query.filter(
        Admin.organization_id == org.id,
        db.or_(Admin.employee_id == identifier, Admin.email == identifier.lower()),
    ).first()
    user_type = 'admin'

    if not user:
        user = Resident.query.filter(
            Resident.organization_id == org.id,
            db.or_(Resident.unit_code == identifier, Resident.phone == identifier),
        ).first()
        user_type = 'resident'

    ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    if not user or not user.check_password(password):
        app_logger.warning(
            f"[AUTH] Login failed | ip={ip} | org_code={org_code} | "
            f"identifier={identifier} | reason=wrong_credentials"
        )
        return jsonify({'error': '帳號或密碼錯誤'}), 401

    if not user.is_active:
        app_logger.warning(
            f"[AUTH] Login failed | ip={ip} | user_id={user.id} | "
            f"user_type={user_type} | reason=account_disabled"
        )
        return jsonify({'error': '帳號已停用，請聯絡管理員'}), 403

    role = 'admin' if user_type == 'admin' else user.role.value
    access_token, refresh_token = _make_tokens(user.id, role, user_type, org.id)

    app_logger.info(
        f"[AUTH] Login success | ip={ip} | user_id={user.id} | "
        f"user_type={user_type} | org_id={org.id}"
    )

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
    responses:
      200:
        description: 回傳新的 access_token
      401:
        description: refresh_token 無效或帳號已停用
    """
    claims = get_jwt()
    user_type = claims.get('user_type')
    org_id = claims.get('org_id')
    user_id = get_jwt_identity()

    if user_type == 'admin':
        user = db.session.get(Admin, user_id)
        role = 'admin'
    else:
        user = db.session.get(Resident, user_id)
        role = user.role.value if user else None

    if not user or not user.is_active:
        return jsonify({'error': '帳號不存在或已停用'}), 401

    access_token = create_access_token(
        identity=user_id,
        additional_claims={'role': role, 'user_type': user_type, 'org_id': org_id},
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
            new_password:
              type: string
            confirm_password:
              type: string
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
        app_logger.warning(
            f"[AUTH] Password change failed | user_id={user.id} | "
            f"user_type={user_type} | reason=wrong_current_password"
        )
        return jsonify({'error': '目前密碼錯誤'}), 400

    user.set_password(new_password)
    db.session.commit()
    app_logger.info(
        f"[AUTH] Password changed | user_id={user.id} | user_type={user_type}"
    )
    return jsonify({'message': '密碼修改成功'}), 200
