from datetime import date, datetime, timezone

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from ..extensions import db
from ..models.announcement import Announcement
from ..models.announcement_read import AnnouncementRead
from ..models.booking import Booking, BookingStatus
from ..models.notification import Notification
from ..models.parcel import Parcel, ParcelStatus
from ..models.repair_ticket import RepairTicket, RepairStatus
from ..models.resident import Resident

resident_dashboard_bp = Blueprint('resident_dashboard', __name__)

_PARCEL_ACTIVE = {ParcelStatus.pending, ParcelStatus.overdue}
_REPAIR_ACTIVE = {RepairStatus.pending, RepairStatus.in_progress}


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    return db.session.get(Resident, int(get_jwt_identity())), claims.get('org_id')


@resident_dashboard_bp.route('/summary', methods=['GET'])
@jwt_required()
def dashboard_summary():
    """
    住戶首頁角標總覽
    ---
    tags:
      - Resident - Dashboard
    security:
      - Bearer: []
    responses:
      200:
        description: 各模組未處理數量
        schema:
          type: object
          properties:
            parcel_pending:
              type: integer
            announcement_unread:
              type: integer
            repair_active:
              type: integer
            booking_upcoming:
              type: integer
            notification_unread:
              type: integer
      403:
        description: 僅住戶可使用
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    parcel_pending = Parcel.query.filter(
        Parcel.resident_id == resident.id,
        Parcel.organization_id == org_id,
        Parcel.status.in_(list(_PARCEL_ACTIVE)),
    ).count()

    now = datetime.now(timezone.utc)
    active_announcement_ids = db.session.query(Announcement.id).filter(
        Announcement.organization_id == org_id,
        db.or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
    ).subquery()

    read_ids = db.session.query(AnnouncementRead.announcement_id).filter(
        AnnouncementRead.resident_id == resident.id,
        AnnouncementRead.organization_id == org_id,
    ).subquery()

    announcement_unread = db.session.query(active_announcement_ids).filter(
        ~active_announcement_ids.c.id.in_(read_ids)
    ).count()

    repair_active = RepairTicket.query.filter(
        RepairTicket.resident_id == resident.id,
        RepairTicket.organization_id == org_id,
        RepairTicket.status.in_(list(_REPAIR_ACTIVE)),
    ).count()

    booking_upcoming = Booking.query.filter(
        Booking.resident_id == resident.id,
        Booking.organization_id == org_id,
        Booking.status == BookingStatus.confirmed,
        Booking.booking_date >= date.today(),
    ).count()

    notification_unread = Notification.query.filter_by(
        resident_id=resident.id,
        org_id=org_id,
        is_read=False,
    ).count()

    return jsonify({
        'parcel_pending': parcel_pending,
        'announcement_unread': announcement_unread,
        'repair_active': repair_active,
        'booking_upcoming': booking_upcoming,
        'notification_unread': notification_unread,
    }), 200
