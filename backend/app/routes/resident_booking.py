# [GateGuard facts]
# 1. Caller: app/__init__.py:112 registers resident_booking_bp at /api
# 2. EDIT existing file — added FacilitySlot import + list_facility_slots route;
#    create_booking rewritten to use slot_id (removed start_time/end_time params);
#    cancel_booking now uses booking.slot.start_time; my_bookings ordering updated.
# 3. New API: GET /api/facilities/:id/slots?date= (returns slot availability)
#    POST /api/bookings body: {facility_id, booking_date, slot_id, num_people, notes}
#    Log fields: resident_id(int), booking_id(int), facility_id(int), slot_id(int),
#    booking_date(YYYY-MM-DD), org_id(int). No PII.
# 4. User verbatim: "用戶在預約公設的時候也可以看到各個時間區段 可以選擇自己要的時間區段
#    每個時段的預約人數 已報到 已離場 已預約 已取消 會依照住戶的預約 都會不同 這樣是否可行 好 先幫我改"
from datetime import date, datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from ..extensions import db
from ..models.booking import Booking, BookingStatus
from ..models.facility import Facility
from ..models.facility_slot import FacilitySlot
from ..models.resident import Resident
from ..utils.logger import app_logger

resident_booking_bp = Blueprint('resident_booking', __name__)


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    org_id = claims.get('org_id')
    resident = db.session.get(Resident, int(get_jwt_identity()))
    return resident, org_id


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
        description: 公設列表（含各公設 slots）
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

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
        description: 公設詳情（含 slots）
      404:
        description: 找不到公設
    """
    claims = get_jwt()
    org_id = claims.get('org_id')

    facility = Facility.query.filter_by(
        id=facility_id, organization_id=org_id, is_active=True
    ).first_or_404()
    return jsonify({'facility': facility.to_dict()}), 200


@resident_booking_bp.route('/facilities/<int:facility_id>/slots', methods=['GET'])
@jwt_required()
def list_facility_slots(facility_id):
    """
    取得公設各時段的剩餘名額（住戶）
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
      - in: query
        name: date
        type: string
        description: 查詢日期 YYYY-MM-DD，不帶預設今天
    responses:
      200:
        description: 各時段資訊含已預約人數與剩餘名額
      400:
        description: 日期格式錯誤
      404:
        description: 找不到公設
    """
    claims = get_jwt()
    org_id = claims.get('org_id')

    facility = Facility.query.filter_by(
        id=facility_id, organization_id=org_id, is_active=True
    ).first_or_404()

    date_str = request.args.get('date')
    try:
        query_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        return jsonify({'error': '日期格式錯誤，應為 YYYY-MM-DD'}), 400

    slots = (
        FacilitySlot.query
        .filter_by(facility_id=facility_id)
        .order_by(FacilitySlot.sort_order.asc(), FacilitySlot.id.asc())
        .all()
    )

    result = []
    for slot in slots:
        booked = db.session.query(db.func.sum(Booking.num_people)).filter(
            Booking.slot_id == slot.id,
            Booking.booking_date == query_date,
            Booking.status != BookingStatus.cancelled,
        ).scalar() or 0
        d = slot.to_dict()
        d['booked_people'] = int(booked)
        d['remaining'] = max(0, facility.max_capacity - int(booked))
        result.append(d)

    return jsonify({'date': query_date.isoformat(), 'slots': result}), 200


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
          required: [facility_id, booking_date, slot_id, num_people]
          properties:
            facility_id:
              type: integer
              example: 1
            booking_date:
              type: string
              example: "2024-10-08"
            slot_id:
              type: integer
              example: 3
              description: 由 GET /api/facilities/:id/slots 取得
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
        description: 找不到公設或時段
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用預約功能'}), 403
    if not resident.is_active:
        return jsonify({'error': '帳號已停用'}), 403

    data = request.get_json(silent=True) or {}

    facility_id = data.get('facility_id')
    booking_date_str = data.get('booking_date') or ''
    slot_id = data.get('slot_id')
    num_people = data.get('num_people')

    if not facility_id or not booking_date_str or slot_id is None or num_people is None:
        return jsonify({'error': '公設、日期、時段、人數皆為必填'}), 400

    facility = Facility.query.filter_by(
        id=facility_id, organization_id=org_id, is_active=True
    ).with_for_update().first()
    if not facility:
        return jsonify({'error': '找不到公設或公設已停用'}), 404

    try:
        booking_date = date.fromisoformat(booking_date_str)
    except ValueError:
        return jsonify({'error': '日期格式錯誤，應為 YYYY-MM-DD'}), 400

    if booking_date < date.today():
        return jsonify({'error': '不能預約過去的日期'}), 400

    slot = FacilitySlot.query.filter_by(id=slot_id, facility_id=facility_id).first()
    if not slot:
        return jsonify({'error': '找不到該時段'}), 404

    try:
        num_people = int(num_people)
        if num_people < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': '人數須為正整數'}), 400

    booked_people = db.session.query(db.func.sum(Booking.num_people)).filter(
        Booking.slot_id == slot_id,
        Booking.booking_date == booking_date,
        Booking.status != BookingStatus.cancelled,
    ).scalar() or 0

    if booked_people + num_people > facility.max_capacity:
        remaining = facility.max_capacity - booked_people
        app_logger.warning(
            f"[BOOKING] Rejected (capacity full) | resident_id={resident.id} | "
            f"facility_id={facility_id} | slot_id={slot_id} | date={booking_date} | "
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
        slot_id=slot_id,
        booking_date=booking_date,
        num_people=num_people,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(booking)
    db.session.commit()

    app_logger.info(
        f"[BOOKING] Created | resident_id={resident.id} | booking_id={booking.id} | "
        f"facility_id={facility_id} | slot_id={slot_id} | date={booking_date} | "
        f"people={num_people} | org_id={org_id}"
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
        enum: [confirmed, checked_in, departed, cancelled]
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
            return jsonify({'error': '無效的狀態篩選值，可選 confirmed, checked_in, departed, cancelled'}), 400

    bookings = query.order_by(
        Booking.booking_date.desc(),
        Booking.slot_id.asc(),
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

    if booking.status in (BookingStatus.checked_in, BookingStatus.departed):
        return jsonify({'error': '已報到或已離場的預約無法取消'}), 400

    booking_start = datetime.combine(
        booking.booking_date, booking.slot.start_time
    ).replace(tzinfo=timezone.utc)
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


# ── QR Code 報到 / 離場 ──

@resident_booking_bp.route('/bookings/<int:booking_id>/checkin', methods=['PATCH'])
@jwt_required()
def checkin_booking(booking_id):
    """
    住戶掃 QR Code 報到
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
        description: 報到成功
      400:
        description: 非預約當天 / 狀態錯誤
      403:
        description: 無權操作
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

    if booking.status != BookingStatus.confirmed:
        return jsonify({'error': '此預約目前無法報到'}), 400

    if booking.booking_date != date.today():
        return jsonify({'error': '僅可在預約當天報到'}), 400

    facility = Facility.query.filter_by(
        id=booking.facility_id
    ).with_for_update().first()
    booking.status = BookingStatus.checked_in
    booking.checked_in_at = datetime.now(timezone.utc)
    facility.current_occupancy += booking.num_people
    db.session.commit()

    app_logger.info(
        f"[BOOKING] Check-in | resident_id={resident.id} | booking_id={booking_id} | "
        f"facility_id={booking.facility_id} | org_id={org_id}"
    )
    return jsonify({'message': '報到成功', 'booking': booking.to_dict()}), 200


@resident_booking_bp.route('/bookings/<int:booking_id>/departure', methods=['PATCH'])
@jwt_required()
def departure_booking(booking_id):
    """
    住戶掃 QR Code 離場
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
        description: 離場成功
      400:
        description: 尚未報到 / 狀態錯誤
      403:
        description: 無權操作
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

    if booking.status != BookingStatus.checked_in:
        return jsonify({'error': '尚未報到，無法進行離場'}), 400

    facility = Facility.query.filter_by(
        id=booking.facility_id
    ).with_for_update().first()
    booking.status = BookingStatus.departed
    booking.departed_at = datetime.now(timezone.utc)
    facility.current_occupancy = max(
        0, facility.current_occupancy - booking.num_people
    )
    db.session.commit()

    app_logger.info(
        f"[BOOKING] Departure | resident_id={resident.id} | booking_id={booking_id} | "
        f"facility_id={booking.facility_id} | org_id={org_id}"
    )
    return jsonify({'message': '離場成功', 'booking': booking.to_dict()}), 200
