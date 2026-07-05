from functools import wraps
from flask import jsonify, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from ..extensions import db
from ..models.admin import Admin


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()

        if claims.get('role') != 'admin':
            return jsonify({'error': '需要管理員權限'}), 403

        admin = db.session.get(Admin, get_jwt_identity())
        if not admin or not admin.is_active:
            return jsonify({'error': '帳號已停用'}), 403

        g.org_id = claims.get('org_id')
        g.admin = admin

        return fn(*args, **kwargs)
    return wrapper
