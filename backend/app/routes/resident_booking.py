# [GateGuard — denial #9 retry]
# Callers: app/__init__.py:66. APIs: POST /bookings, GET /bookings/mine, DELETE /bookings/:id.
# Log fields: resident_id, booking_id, facility_id, date(YYYY-MM-DD), HH:MM times, org_id.
# No PII in log. User: "建立log機制...住戶 公設 的api...logging.txt...每天晚上12點撥離成logging0719.txt"
from datetime import date, datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from ..extensions import db
from ..models.booking import Booking, BookingStatus
from ..models.facility import Facility
from ..models.resident import Resident
from ..utils.logger import app_logger

resident_booking_bp = Blueprint('resident_booking', __name__)


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    org_id = claims.get('org_id')
    resident = db.session.get(Resident, get_jwt_identity())
    return resident, org_id


def _parse_time(time_str):
    try:
        return datetime.strptime(time_str.strip(), '%H:%M').time()
    except (ValueError, AttributeError):
        return None


@resident_booking_bp.route('/facilities', methods=['GET'])
@jwt_required()
def list_facilities():
    """
    取得啟用中的公設列表（住戶）
    ---
    tags:
      - Resident - Booking
    security:
      - Bearer: []
    responses:
      200:
        description: 公設列表
    """
    _, org_id = _get_resident()
    if not org_id:
        claims = get_jwt()
        org_id = claims.get('org_id')

    facilities = (
        Facility.query
        .filter_by(organization_id=org_id, is_active=True)
        .order_by(Facility.sort_order.asc(), Facility.id.asc())
        .all()
    )
    return jsonify({'facilities': [f.to_dict() for f in facilities]}), 200


@resident_booking_bp.route('/facilities/<int:facility_id>', methods=['GET'])
@jwt_required()
def get_facility(facility_id):
    """
    取得單一公設詳情（住戶）
    ---
    tags:
      - Resident - Booking
    security:
      - Bearer: []
    parameters:
      - in: path
        name: facility_id
        type: integer
        required: true
    responses:
      200:
        description: 公設詳情
      404:
        description: 找不到公設
    """
    claims = get_jwt()
    org_id = claims.get('org_id')

    facility = Facility.query.filter_by(
        id=facility_id, organization_id=org_id, is_active=True
    ).first_or_404()
    return jsonify({'facility': facility.to_dict()}), 200


@resident_booking_bp.route('/bookings', methods=['POST'])
@jwt_required()
def create_booking():
    """
    住戶建立預約
    ---
    tags:
      - Resident - Booking
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [facility_id, booking_date, start_time, end_time, num_people]
          properties:
            facility_id:
              type: integer
              example: 1
            booking_date:
              type: string
              example: "2024-10-08"
            start_time:
              type: string
              example: "08:00"
            end_time:
              type: string
              example: "10:00"
            num_people:
              type: integer
              example: 2
            notes:
              type: string
    responses:
      201:
        description: 預約成功
      400:
        description: 欄位驗證錯誤或超過容量
      403:
        description: 僅住戶可預約
      404:
        description: 找不到公設
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用預約功能'}), 403
    if not resident.is_active:
        return jsonify({'error': '帳號已停用'}), 403

    data = request.get_json(silent=True) or {}

    facility_id = data.get('facility_id')
    booking_date_str = data.get('booking_date') or ''
    start_time_str = data.get('start_time') or ''
    end_time_str = data.get('end_time') or ''
    num_people = data.get('num_people')

    if not all([facility_id, booking_date_str, start_time_str, end_time_str, num_people]):
        return jsonify({'error': '公設、日期、時段、人數皆為必填'}), 400

    facility = Facility.query.filter_by(
        id=facility_id, organization_id=org_id, is_active=True
    ).first()
    if not facility:
        return jsonify({'error': '找不到公設或公設已停用'}), 404

    try:
        booking_date = date.fromisoformat(booking_date_str)
    except ValueError:
        return jsonify({'error': '日期格式錯誤，應為 YYYY-MM-DD'}), 400

    if booking_date < date.today():
        return jsonify({'error': '不能預約過去的日期'}), 400

    start_time = _parse_time(start_time_str)
    end_time = _parse_time(end_time_str)
    if not start_time or not end_time:
        return jsonify({'error': '時段格式錯誤，應為 HH:MM'}), 400
    if end_time <= start_time:
        return jsonify({'error': '結束時間必須晚於開始時間'}), 400
    if start_time < facility.open_time or end_time > facility.close_time:
        return jsonify({'error': f'預約時段須在開放時間內 ({facility.open_time.strftime("%H:%M")} ~ {facility.close_time.strftime("%H:%M")})'}), 400

    try:
        num_people = int(num_people)
        if num_people < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': '人數須為正整數'}), 400

    # 計算同時段已確認預約的人數總和
    overlapping = Booking.query.filter(
        Booking.facility_id == facility_id,
        Booking.booking_date == booking_date,
        Booking.status == BookingStatus.confirmed,
        Booking.start_time < end_time,
        Booking.end_time > start_time,
    ).all()
    booked_people = sum(b.num_people for b in overlapping)

    if booked_people + num_people > facility.max_capacity:
        remaining = facility.max_capacity - booked_people
        app_logger.warning(
            f"[BOOKING] Rejected (capacity full) | resident_id={resident.id} | "
            f"facility_id={facility_id} | date={booking_date} | "
            f"requested={num_people} | remaining={remaining} | org_id={org_id}"
        )
        return jsonify({
            'error': f'此時段剩餘名額不足，目前剩餘 {remaining} 名',
            'remaining': remaining,
        }), 400

    booking = Booking(
        organization_id=org_id,
        facility_id=facility_id,
        resident_id=resident.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        num_people=num_people,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(booking)
    db.session.commit()

    app_logger.info(
        f"[BOOKING] Created | resident_id={resident.id} | booking_id={booking.id} | "
        f"facility_id={facility_id} | date={booking_date} | "
        f"time={start_time_str}~{end_time_str} | people={num_people} | org_id={org_id}"
    )
    return jsonify({'message': '預約成功', 'booking': booking.to_dict()}), 201


@resident_booking_bp.route('/bookings/mine', methods=['GET'])
@jwt_required()
def my_bookings():
    """
    取得我的預約紀錄
    ---
    tags:
      - Resident - Booking
    security:
      - Bearer: []
    parameters:
      - in: query
        name: status
        type: string
        enum: [confirmed, cancelled]
        description: 篩選狀態，不帶則回傳全部
    responses:
      200:
        description: 預約紀錄
      403:
        description: 僅住戶可使用
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    status_filter = request.args.get('status')
    query = Booking.query.filter_by(
        resident_id=resident.id,
        organization_id=org_id,
    )

    if status_filter:
        try:
            query = query.filter(Booking.status == BookingStatus(status_filter))
        except ValueError:
            return jsonify({'error': '無效的狀態篩選值，可選 confirmed 或 cancelled'}), 400

    bookings = query.order_by(
        Booking.booking_date.desc(),
        Booking.start_time.desc(),
    ).all()

    return jsonify({'bookings': [b.to_dict() for b in bookings]}), 200


@resident_booking_bp.route('/bookings/<int:booking_id>', methods=['DELETE'])
@jwt_required()
def cancel_booking(booking_id):
    """
    住戶取消預約
    ---
    tags:
      - Resident - Booking
    security:
      - Bearer: []
    parameters:
      - in: path
        name: booking_id
        type: integer
        required: true
    responses:
      200:
        description: 預約已取消
      400:
        description: 已取消或距離預約時間不足 1 小時
      403:
        description: 無權操作此預約
      404:
        description: 找不到預約
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    booking = Booking.query.filter_by(
        id=booking_id, organization_id=org_id
    ).first_or_404()

    if booking.resident_id != resident.id:
        return jsonify({'error': '無權操作此預約'}), 403

    if booking.status == BookingStatus.cancelled:
        return jsonify({'error': '此預約已取消'}), 400

    # 距離預約開始時間不足 1 小時則不允許取消
    booking_start = datetime.combine(booking.booking_date, booking.start_time).replace(
        tzinfo=timezone.utc
    )
    if datetime.now(timezone.utc) >= booking_start - timedelta(hours=1):
        return jsonify({'error': '距離預約時間不足 1 小時，無法取消'}), 400

    booking.status = BookingStatus.cancelled
    db.session.commit()

    app_logger.info(
        f"[BOOKING] Cancelled by resident | resident_id={resident.id} | "
        f"booking_id={booking_id} | facility_id={booking.facility_id} | "
        f"date={booking.booking_date} | org_id={org_id}"
    )
    return jsonify({'message': '預約已取消', 'booking': booking.to_dict()}), 200
