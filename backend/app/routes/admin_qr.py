# [GateGuard facts]
# 1. Registered in app/__init__.py at /api/admin
# 2. NEW file — POST /api/admin/qr/verify + POST /api/admin/facility-checkins/confirm
# 3. verify: creates QrVerification (read-only on booking).
#    confirm: SELECT FOR UPDATE on token+verification+booking, booking→checked_in,
#    token.used_at=NOW, verification.confirmed_at=NOW, inserts BookingCheckinLog.
#    Log: admin_id, booking_id, org_id, trace_id. No PII.
# 4. User: "必須在單一 transaction 中完成... 兩台管理員裝置同時確認時，
#    只能一台成功；另一台回 409 BOOKING_ALREADY_CHECKED_IN，不得重複寫入"
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select
from ..extensions import db
from ..models.booking import Booking, BookingStatus
from ..models.booking_checkin_log import BookingCheckinLog
from ..models.qr_action_token import QrActionToken
from ..models.qr_verification import QrVerification, VERIFICATION_TTL_SECONDS
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

admin_qr_bp = Blueprint('admin_qr', __name__)

SUPPORTED_TYPES = {'facility_checkin', 'facility_departure'}


def _qr_err(code, message, status, details=None):
    return jsonify({
        'error': {
            'code': code,
            'message': message,
            'details': details or {},
            'trace_id': str(uuid.uuid4()),
        }
    }), status


def _get_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)


@admin_qr_bp.route('/qr/verify', methods=['POST'])
@admin_required
def verify_qr():
    """
    管理員掃描 QR Code 後驗證（唯讀，不改報到狀態）
    ---
    tags:
      - Admin - QR
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [type, token]
          properties:
            type:
              type: string
              example: facility_checkin
            token:
              type: string
              example: fci_7hD2kP9x...
    responses:
      200:
        description: 驗證成功，回傳預約資料（需再呼叫 confirm 完成報到）
      400:
        description: payload 格式錯誤 / type 不支援 / type 與 purpose 不一致
      404:
        description: token 不存在
      409:
        description: token 已使用 / 預約已報到
      410:
        description: token 已過期
    """
    trace_id = str(uuid.uuid4())
    data = request.get_json(silent=True) or {}
    qr_type = (data.get('type') or '').strip()
    raw_token = (data.get('token') or '').strip()

    if not qr_type or not raw_token:
        return _qr_err('QR_PAYLOAD_INVALID', '缺少 type 或 token', 400)

    if qr_type not in SUPPORTED_TYPES:
        return _qr_err('QR_TYPE_UNSUPPORTED', f'不支援的 QR 類型: {qr_type}', 400)

    token = db.session.execute(
        select(QrActionToken)
        .where(QrActionToken.token_hash == QrActionToken.hash_token(raw_token))
        .with_for_update()
    ).scalar_one_or_none()
    if not token:
        return _qr_err('QR_TOKEN_NOT_FOUND', '找不到此 QR Code', 404)

    if token.org_id != g.org_id:
        return _qr_err('ORG_MISMATCH', '跨社區操作不允許', 403)

    if token.purpose != qr_type:
        return _qr_err('QR_TYPE_MISMATCH', 'QR 類型與 token 用途不一致', 400)

    if token.used_at is not None:
        return _qr_err('QR_TOKEN_USED', '此 QR Code 已使用', 409)

    if token.revoked_at is not None:
        return _qr_err('QR_TOKEN_NOT_FOUND', '找不到此 QR Code', 404)

    now = datetime.now(timezone.utc)
    if token.expires_at <= now:
        return _qr_err('QR_TOKEN_EXPIRED', '報到 QR Code 已過期，請住戶重新產生', 410)

    booking = db.session.get(Booking, token.subject_id)
    if not booking:
        return _qr_err('QR_TOKEN_NOT_FOUND', '找不到預約', 404)

    if token.purpose == 'facility_checkin':
        if booking.status != BookingStatus.confirmed:
            return _qr_err('BOOKING_ALREADY_CHECKED_IN', '預約狀態已變更，無法報到', 409)
    else:  # facility_departure
        if booking.status != BookingStatus.checked_in:
            return _qr_err('BOOKING_ALREADY_CHECKED_IN', '住戶尚未報到或已完成離場', 409)

    verification = QrVerification(
        verification_id=QrVerification.generate_id(),
        token_id=token.id,
        verified_by_admin_id=g.admin.id,
        verified_at=now,
        expires_at=now + timedelta(seconds=VERIFICATION_TTL_SECONDS),
        result='pending',
    )
    db.session.add(verification)
    db.session.add(BookingCheckinLog(
        org_id=g.org_id,
        booking_id=booking.id,
        action='verify',
        admin_id=g.admin.id,
        ip_address=_get_ip(),
        result='success',
        trace_id=trace_id,
    ))
    db.session.commit()

    app_logger.info(
        f"[QR] Verify | admin_id={g.admin.id} | booking_id={booking.id} | "
        f"verification_id={verification.verification_id} | org_id={g.org_id}"
    )

    slot = booking.slot
    resident = booking.resident
    return jsonify({
        'data': {
            'action': token.purpose,
            'verification_id': verification.verification_id,
            'verification_expires_at': verification.expires_at.isoformat(),
            'booking': {
                'id': booking.id,
                'status': booking.status.value,
                'booking_date': booking.booking_date.isoformat(),
                'start_time': slot.start_time.strftime('%H:%M') if slot else None,
                'end_time': slot.end_time.strftime('%H:%M') if slot else None,
                'num_people': booking.num_people,
                'resident': {
                    'name': resident.name if resident else None,
                    'unit_code': resident.unit_code if resident else None,
                },
                'facility': {
                    'id': booking.facility_id,
                    'name': booking.facility.name if booking.facility else None,
                    'icon': booking.facility.icon if booking.facility else None,
                },
            },
        }
    }), 200


@admin_qr_bp.route('/facility-checkins/confirm', methods=['POST'])
@admin_required
def confirm_checkin():
    """
    管理員二次確認並完成報到（單一 transaction，防重複）
    ---
    tags:
      - Admin - QR
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [verification_id, token]
          properties:
            verification_id:
              type: string
              example: qrv_a82f...
            token:
              type: string
              example: fci_7hD2kP9x...
    responses:
      200:
        description: 報到完成
      409:
        description: 預約已報到（兩台裝置競爭時第二台收到）
      410:
        description: QR 或驗證已過期
    """
    trace_id = str(uuid.uuid4())
    data = request.get_json(silent=True) or {}
    verification_id = (data.get('verification_id') or '').strip()
    raw_token = (data.get('token') or '').strip()

    if not verification_id or not raw_token:
        return _qr_err('QR_PAYLOAD_INVALID', '缺少 verification_id 或 token', 400)

    now = datetime.now(timezone.utc)
    booking = None

    try:
        token = db.session.execute(
            select(QrActionToken)
            .where(QrActionToken.token_hash == QrActionToken.hash_token(raw_token))
            .with_for_update()
        ).scalar_one_or_none()

        if not token:
            return _qr_err('QR_TOKEN_NOT_FOUND', '找不到此 QR Code', 404)
        if token.org_id != g.org_id:
            return _qr_err('ORG_MISMATCH', '跨社區操作不允許', 403)
        if token.used_at is not None:
            return _qr_err('QR_TOKEN_USED', '此 QR Code 已使用', 409)
        if token.revoked_at is not None or token.expires_at <= now:
            return _qr_err('QR_TOKEN_EXPIRED', '報到 QR Code 已過期', 410)

        verification = db.session.execute(
            select(QrVerification)
            .where(QrVerification.verification_id == verification_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not verification or verification.token_id != token.id:
            return _qr_err('QR_TOKEN_NOT_FOUND', '驗證記錄不存在', 404)
        if not verification.is_valid():
            return _qr_err('QR_TOKEN_EXPIRED', '驗證已過期，請重新掃描', 410)

        booking = db.session.execute(
            select(Booking)
            .where(Booking.id == token.subject_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not booking:
            return _qr_err('QR_TOKEN_NOT_FOUND', '找不到預約', 404)
        if booking.status == BookingStatus.checked_in:
            return _qr_err('BOOKING_ALREADY_CHECKED_IN', '預約已報到', 409)
        if booking.status != BookingStatus.confirmed:
            return _qr_err('BOOKING_ALREADY_CHECKED_IN', '預約狀態無效', 409)

        booking.status = BookingStatus.checked_in
        booking.checked_in_at = now
        booking.facility.current_occupancy += booking.num_people
        token.mark_used()
        verification.confirmed_at = now
        verification.result = 'confirmed'

        db.session.add(BookingCheckinLog(
            org_id=g.org_id,
            booking_id=booking.id,
            action='check_in',
            admin_id=g.admin.id,
            ip_address=_get_ip(),
            result='success',
            trace_id=trace_id,
        ))
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        app_logger.error(
            f"[QR] Confirm error | admin_id={g.admin.id} | "
            f"trace_id={trace_id} | error={str(e)}"
        )
        return _qr_err('QR_PAYLOAD_INVALID', '確認失敗，請重試', 500)

    app_logger.info(
        f"[QR] Confirm checkin | admin_id={g.admin.id} | booking_id={booking.id} | "
        f"verification_id={verification_id} | org_id={g.org_id} | trace_id={trace_id}"
    )

    return jsonify({
        'data': {
            'booking_id': booking.id,
            'status': booking.status.value,
            'checked_in_at': booking.checked_in_at.isoformat(),
            'checked_in_by': {
                'admin_id': g.admin.id,
                'employee_id': g.admin.employee_id,
            },
        }
    }), 200


@admin_qr_bp.route('/facility-departures/confirm', methods=['POST'])
@admin_required
def confirm_departure():
    """
    管理員確認住戶離場（單一 transaction，防重複）
    ---
    tags:
      - Admin - QR
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [verification_id, token]
          properties:
            verification_id:
              type: string
              example: qrv_b91c...
            token:
              type: string
              example: fdp_3xK7mQ2y...
    responses:
      200:
        description: 離場完成
      409:
        description: 預約已離場（兩台裝置競爭時第二台收到）
      410:
        description: QR 或驗證已過期
    """
    trace_id = str(uuid.uuid4())
    data = request.get_json(silent=True) or {}
    verification_id = (data.get('verification_id') or '').strip()
    raw_token = (data.get('token') or '').strip()

    if not verification_id or not raw_token:
        return _qr_err('QR_PAYLOAD_INVALID', '缺少 verification_id 或 token', 400)

    now = datetime.now(timezone.utc)
    booking = None

    try:
        token = db.session.execute(
            select(QrActionToken)
            .where(QrActionToken.token_hash == QrActionToken.hash_token(raw_token))
            .with_for_update()
        ).scalar_one_or_none()

        if not token:
            return _qr_err('QR_TOKEN_NOT_FOUND', '找不到此 QR Code', 404)
        if token.org_id != g.org_id:
            return _qr_err('ORG_MISMATCH', '跨社區操作不允許', 403)
        if token.purpose != 'facility_departure':
            return _qr_err('QR_TYPE_MISMATCH', 'QR 類型與用途不一致', 400)
        if token.used_at is not None:
            return _qr_err('QR_TOKEN_USED', '此 QR Code 已使用', 409)
        if token.revoked_at is not None or token.expires_at <= now:
            return _qr_err('QR_TOKEN_EXPIRED', '離場 QR Code 已過期', 410)

        verification = db.session.execute(
            select(QrVerification)
            .where(QrVerification.verification_id == verification_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not verification or verification.token_id != token.id:
            return _qr_err('QR_TOKEN_NOT_FOUND', '驗證記錄不存在', 404)
        if not verification.is_valid():
            return _qr_err('QR_TOKEN_EXPIRED', '驗證已過期，請重新掃描', 410)

        booking = db.session.execute(
            select(Booking)
            .where(Booking.id == token.subject_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not booking:
            return _qr_err('QR_TOKEN_NOT_FOUND', '找不到預約', 404)
        if booking.status == BookingStatus.departed:
            return _qr_err('BOOKING_ALREADY_CHECKED_IN', '預約已離場', 409)
        if booking.status != BookingStatus.checked_in:
            return _qr_err('BOOKING_ALREADY_CHECKED_IN', '預約狀態無效', 409)

        booking.status = BookingStatus.departed
        booking.departed_at = now
        booking.facility.current_occupancy = max(
            0, booking.facility.current_occupancy - booking.num_people
        )
        token.mark_used()
        verification.confirmed_at = now
        verification.result = 'confirmed'

        db.session.add(BookingCheckinLog(
            org_id=g.org_id,
            booking_id=booking.id,
            action='depart',
            admin_id=g.admin.id,
            ip_address=_get_ip(),
            result='success',
            trace_id=trace_id,
        ))
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        app_logger.error(
            f"[QR] Departure error | admin_id={g.admin.id} | "
            f"trace_id={trace_id} | error={str(e)}"
        )
        return _qr_err('QR_PAYLOAD_INVALID', '確認失敗，請重試', 500)

    app_logger.info(
        f"[QR] Confirm departure | admin_id={g.admin.id} | booking_id={booking.id} | "
        f"facility_id={booking.facility_id} | org_id={g.org_id} | trace_id={trace_id}"
    )

    return jsonify({
        'data': {
            'booking_id': booking.id,
            'facility_id': booking.facility_id,
            'status': booking.status.value,
            'departed_at': booking.departed_at.isoformat(),
            'confirmed_by': {
                'admin_id': g.admin.id,
                'employee_id': g.admin.employee_id,
            },
        }
    }), 200
