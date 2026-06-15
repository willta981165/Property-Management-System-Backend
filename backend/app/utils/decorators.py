from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from ..models.admin import Admin


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()

        if claims.get('role') != 'admin':
            return jsonify({'error': '需要管理員權限'}), 403

        admin = Admin.query.get(get_jwt_identity())
        if not admin or not admin.is_active:
            return jsonify({'error': '帳號已停用'}), 403

        return fn(*args, **kwargs)
    return wrapper
