# [GateGuard facts]
# 1. Registered in app/__init__.py at /api
# 2. NEW file — POST /api/bookings/<id>/checkin-token
# 3. Writes to qr_action_tokens: token_hash(SHA-256), expires_at(now+45s),
#    purpose='facility_checkin', subject_type='booking', subject_id=booking_id.
#    Raw token returned to client, never stored. Log: resident_id, booking_id, org_id.
# 4. User spec: "資料庫只存 token hash，不存明文... token 建議有效 30～60 秒"
import uuid
from datetime import date, datetime, timezone, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from ..extensions import db
from ..models.booking import Booking, BookingStatus
from ..models.qr_action_token import QrActionToken, TOKEN_TTL_SECONDS
from ..models.resident import Resident
from ..utils.logger import app_logger

resident_qr_bp = Blueprint('resident_qr', __name__)

CHECKIN_OPEN_BEFORE_MINUTES = 15


def _qr_err(code, message, status, details=None):
    return jsonify({
        'error': {
            'code': code,
            'message': message,
            'details': details or {},
            'trace_id': str(uuid.uuid4()),
        }
    }), status


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    return db.session.get(Resident, int(get_jwt_identity())), claims.get('org_id')


@resident_qr_bp.route('/bookings/<int:booking_id>/checkin-token', methods=['POST'])
@jwt_required()
def get_checkin_token(booking_id):
    """
    住戶取得報到 QR token
    ---
    tags:
      - Resident - QR
    security:
      - Bearer: []
    parameters:
      - in: path
        name: booking_id
        type: integer
        required: true
    responses:
      200:
        description: 回傳短效 QR token（45 秒有效）
      403:
        description: 無權操作
      409:
        description: 預約已取消 / 已報到
      422:
        description: 尚未到可報到時間
    """
    resident, org_id = _get_resident()
    if not resident:
        return _qr_err('AUTH_REQUIRED', '僅住戶可使用此功能', 401)

    booking = Booking.query.filter_by(
        id=booking_id, organization_id=org_id
    ).first()
    if not booking:
        return _qr_err('QR_TOKEN_NOT_FOUND', '找不到預約', 404)

    if booking.resident_id != resident.id:
        return _qr_err('BOOKING_NOT_OWNED', '無權操作此預約', 403)

    if booking.status == BookingStatus.cancelled:
        return _qr_err('BOOKING_CANCELLED', '此預約已取消', 409)

    if booking.status in (BookingStatus.checked_in, BookingStatus.departed):
        return _qr_err('BOOKING_ALREADY_CHECKED_IN', '此預約已完成報到', 409)

    if booking.status != BookingStatus.confirmed:
        return _qr_err('BOOKING_CANCELLED', '此預約狀態無法報到', 409)

    if booking.booking_date != date.today():
        return _qr_err('CHECKIN_NOT_OPEN', '僅可在預約當天取得報到 QR', 422)

    now = datetime.now(timezone.utc)
    slot = booking.slot
    slot_start = datetime.combine(booking.booking_date, slot.start_time).replace(tzinfo=timezone.utc)
    slot_end = datetime.combine(booking.booking_date, slot.end_time).replace(tzinfo=timezone.utc)
    open_from = slot_start - timedelta(minutes=CHECKIN_OPEN_BEFORE_MINUTES)

    if now < open_from or now > slot_end:
        return _qr_err(
            'CHECKIN_NOT_OPEN',
            f'報到時間為 {slot.start_time.strftime("%H:%M")} 前 {CHECKIN_OPEN_BEFORE_MINUTES} 分鐘至 {slot.end_time.strftime("%H:%M")}',
            422,
        )

    # Revoke all previous unused tokens for this booking
    old_tokens = QrActionToken.query.filter_by(
        subject_type='booking',
        subject_id=booking_id,
        purpose='facility_checkin',
    ).filter(
        QrActionToken.used_at.is_(None),
        QrActionToken.revoked_at.is_(None),
    ).all()
    for old in old_tokens:
        old.revoke()

    raw_token = QrActionToken.generate_raw('facility_checkin')
    expires_at = now + timedelta(seconds=TOKEN_TTL_SECONDS)
    refresh_after = expires_at - timedelta(seconds=15)

    qr_token = QrActionToken(
        org_id=org_id,
        purpose='facility_checkin',
        token_hash=QrActionToken.hash_token(raw_token),
        subject_type='booking',
        subject_id=booking_id,
        issued_to_user_id=resident.id,
        expires_at=expires_at,
    )
    db.session.add(qr_token)
    db.session.commit()

    app_logger.info(
        f"[QR] Token issued | resident_id={resident.id} | booking_id={booking_id} | "
        f"org_id={org_id} | expires_at={expires_at.isoformat()}"
    )

    return jsonify({
        'data': {
            'version': 1,
            'type': 'facility_checkin',
            'token': raw_token,
            'expires_at': expires_at.isoformat(),
            'refresh_after': refresh_after.isoformat(),
        }
    }), 200


@resident_qr_bp.route('/bookings/<int:booking_id>/departure-token', methods=['POST'])
@jwt_required()
def get_departure_token(booking_id):
    """
    住戶取得離場 QR token
    ---
    tags:
      - Resident - QR
    security:
      - Bearer: []
    parameters:
      - in: path
        name: booking_id
        type: integer
        required: true
    responses:
      200:
        description: 回傳短效離場 QR token（45 秒有效）
      403:
        description: 無權操作
      409:
        description: 尚未報到 / 已離場
    """
    resident, org_id = _get_resident()
    if not resident:
        return _qr_err('AUTH_REQUIRED', '僅住戶可使用此功能', 401)

    booking = Booking.query.filter_by(
        id=booking_id, organization_id=org_id
    ).first()
    if not booking:
        return _qr_err('QR_TOKEN_NOT_FOUND', '找不到預約', 404)

    if booking.resident_id != resident.id:
        return _qr_err('BOOKING_NOT_OWNED', '無權操作此預約', 403)

    if booking.status == BookingStatus.confirmed:
        return _qr_err('BOOKING_NOT_OWNED', '尚未報到，無法取得離場 QR', 409)

    if booking.status == BookingStatus.departed:
        return _qr_err('BOOKING_ALREADY_CHECKED_IN', '此預約已完成離場', 409)

    if booking.status == BookingStatus.cancelled:
        return _qr_err('BOOKING_CANCELLED', '此預約已取消', 409)

    if booking.status != BookingStatus.checked_in:
        return _qr_err('BOOKING_NOT_OWNED', '此預約狀態無法離場', 409)

    now = datetime.now(timezone.utc)

    # Revoke previous unused departure tokens for this booking
    old_tokens = QrActionToken.query.filter_by(
        subject_type='booking',
        subject_id=booking_id,
        purpose='facility_departure',
    ).filter(
        QrActionToken.used_at.is_(None),
        QrActionToken.revoked_at.is_(None),
    ).all()
    for old in old_tokens:
        old.revoke()

    raw_token = QrActionToken.generate_raw('facility_departure')
    expires_at = now + timedelta(seconds=TOKEN_TTL_SECONDS)
    refresh_after = expires_at - timedelta(seconds=15)

    qr_token = QrActionToken(
        org_id=org_id,
        purpose='facility_departure',
        token_hash=QrActionToken.hash_token(raw_token),
        subject_type='booking',
        subject_id=booking_id,
        issued_to_user_id=resident.id,
        expires_at=expires_at,
    )
    db.session.add(qr_token)
    db.session.commit()

    app_logger.info(
        f"[QR] Departure token issued | resident_id={resident.id} | "
        f"booking_id={booking_id} | org_id={org_id} | expires_at={expires_at.isoformat()}"
    )

    return jsonify({
        'data': {
            'version': 1,
            'type': 'facility_departure',
            'token': raw_token,
            'expires_at': expires_at.isoformat(),
            'refresh_after': refresh_after.isoformat(),
        }
    }), 200
