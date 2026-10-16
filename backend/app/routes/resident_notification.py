from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from ..extensions import db
from ..models.notification import Notification
from ..models.resident import Resident

resident_notification_bp = Blueprint('resident_notification', __name__)


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    return db.session.get(Resident, int(get_jwt_identity())), claims.get('org_id')


@resident_notification_bp.route('', methods=['GET'])
@jwt_required()
def list_notifications():
    """
    取得住戶通知列表（最新 50 筆）
    ---
    tags:
      - Resident - Notification
    security:
      - Bearer: []
    responses:
      200:
        description: 通知列表及未讀數
      403:
        description: 僅住戶可使用
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    notifications = (
        Notification.query
        .filter_by(resident_id=resident.id, org_id=org_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    unread_count = sum(1 for n in notifications if not n.is_read)

    return jsonify({
        'unread_count': unread_count,
        'notifications': [n.to_dict() for n in notifications],
    }), 200


@resident_notification_bp.route('/read-all', methods=['PATCH'])
@jwt_required()
def mark_all_read():
    """
    全部標為已讀（鈴鐺歸零）
    ---
    tags:
      - Resident - Notification
    security:
      - Bearer: []
    responses:
      200:
        description: 所有通知已標為已讀
      403:
        description: 僅住戶可使用
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    Notification.query.filter_by(
        resident_id=resident.id,
        org_id=org_id,
        is_read=False,
    ).update({'is_read': True})
    db.session.commit()

    return jsonify({'message': '已全部標為已讀'}), 200
