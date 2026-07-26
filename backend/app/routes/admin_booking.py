# [GateGuard facts]
# 1. Caller: app/__init__.py:111 registers admin_booking_bp at /api/admin
# 2. EDIT existing file — added FacilitySlot import; added slot_id filter to
#    list_facility_bookings; ordering fixed (Booking.start_time removed, now join
#    FacilitySlot); status_filter error msg updated to include all 4 statuses.
# 3. Affected APIs: GET /api/admin/facilities/:id/bookings (slot_id filter added),
#    GET /api/admin/bookings/overview, PATCH /api/admin/bookings/:id/cancel
#    Log: admin_id(int), booking_id(int), resident_id(int), facility_id(int),
#    booking_date(YYYY-MM-DD), org_id(int). No PII.
# 4. User verbatim: "在使用者名單 前端會追加一個option 可以選擇 8:00~9:00 9:00~10:00
#    10:00~11:00 這些時段 每個時段的預約人數 已報到 已離場 已預約 已取消 會依照住戶的預約 都會不同"
from datetime import date
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models.booking import Booking, BookingStatus
from ..models.facility import Facility
from ..models.facility_slot import FacilitySlot
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

admin_booking_bp = Blueprint('admin_booking', __name__)


@admin_booking_bp.route('/bookings/overview', methods=['GET'])
@admin_required
def bookings_overview():
    """
    取得所有公設今日預約總覽（管理員）
    ---
    tags:
      - Admin - Booking
    security:
      - Bearer: []
    parameters:
      - in: query
        name: date
        type: string
        description: 查詢日期 YYYY-MM-DD，不帶預設今天
    responses:
      200:
        description: 各公設預約人數統計（含 current_occupancy）
    """
    query_date_str = request.args.get('date')
    try:
        query_date = date.fromisoformat(query_date_str) if query_date_str else date.today()
    except ValueError:
        return jsonify({'error': '日期格式錯誤，應為 YYYY-MM-DD'}), 400

    facilities = Facility.query.filter_by(
        organization_id=g.org_id
    ).order_by(Facility.sort_order.asc(), Facility.id.asc()).all()

    result = []
    for facility in facilities:
        bookings = Booking.query.filter_by(
            facility_id=facility.id,
            organization_id=g.org_id,
            booking_date=query_date,
        ).all()

        counts = {s.value: 0 for s in BookingStatus}
        total_people = 0
        for b in bookings:
            counts[b.status.value] += b.num_people
            if b.status != BookingStatus.cancelled:
                total_people += b.num_people

        result.append({
            'facility_id': facility.id,
            'name': facility.name,
            'icon': facility.icon,
            'is_active': facility.is_active,
            'max_capacity': facility.max_capacity,
            'current_occupancy': facility.current_occupancy,
            'total_people': total_people,
            'confirmed': counts['confirmed'],
            'checked_in': counts['checked_in'],
            'departed': counts['departed'],
            'cancelled': counts['cancelled'],
        })

    return jsonify({
        'date': query_date.isoformat(),
        'facilities': result,
    }), 200


@admin_booking_bp.route('/facilities/<int:facility_id>/bookings', methods=['GET'])
@admin_required
def list_facility_bookings(facility_id):
    """
    取得某公設的預約名單（管理員）
    ---
    tags:
      - Admin - Booking
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
        description: 查詢日期，格式 YYYY-MM-DD，預設今天
        example: "2024-10-08"
      - in: query
        name: status
        type: string
        enum: [confirmed, checked_in, departed, cancelled]
        description: 篩選狀態，不帶則回傳全部
      - in: query
        name: slot_id
        type: integer
        description: 篩選時段，不帶則回傳所有時段
    responses:
      200:
        description: 預約名單
      404:
        description: 找不到公設
    """
    facility = Facility.query.filter_by(
        id=facility_id, organization_id=g.org_id
    ).first_or_404()

    query_date_str = request.args.get('date')
    try:
        query_date = date.fromisoformat(query_date_str) if query_date_str else date.today()
    except ValueError:
        return jsonify({'error': '日期格式錯誤，應為 YYYY-MM-DD'}), 400

    query = Booking.query.filter_by(
        facility_id=facility_id,
        organization_id=g.org_id,
        booking_date=query_date,
    )

    status_filter = request.args.get('status')
    if status_filter:
        try:
            query = query.filter(Booking.status == BookingStatus(status_filter))
        except ValueError:
            return jsonify({'error': '無效的狀態篩選值，可選 confirmed, checked_in, departed, cancelled'}), 400

    slot_id_filter = request.args.get('slot_id')
    if slot_id_filter:
        try:
            query = query.filter(Booking.slot_id == int(slot_id_filter))
        except (ValueError, TypeError):
            return jsonify({'error': '無效的 slot_id'}), 400

    bookings = (
        query.join(FacilitySlot, Booking.slot_id == FacilitySlot.id)
             .order_by(FacilitySlot.start_time.asc())
             .all()
    )
    total_people = sum(b.num_people for b in bookings if b.status != BookingStatus.cancelled)

    return jsonify({
        'facility': facility.to_dict(),
        'date': query_date.isoformat(),
        'total_people': total_people,
        'bookings': [b.to_dict() for b in bookings],
    }), 200


@admin_booking_bp.route('/bookings/<int:booking_id>/cancel', methods=['PATCH'])
@admin_required
def cancel_booking(booking_id):
    """
    管理員取消預約
    ---
    tags:
      - Admin - Booking
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
        description: 預約已取消，無法重複操作
      404:
        description: 找不到預約
    """
    booking = Booking.query.filter_by(
        id=booking_id, organization_id=g.org_id
    ).first_or_404()

    if booking.status == BookingStatus.cancelled:
        return jsonify({'error': '此預約已取消'}), 400

    booking.status = BookingStatus.cancelled
    booking.cancelled_by_admin = True
    db.session.commit()

    app_logger.warning(
        f"[BOOKING] Admin forced cancel | admin_id={g.admin.id} | "
        f"booking_id={booking_id} | resident_id={booking.resident_id} | "
        f"facility_id={booking.facility_id} | date={booking.booking_date} | "
        f"org_id={g.org_id}"
    )
    return jsonify({'message': '預約已取消', 'booking': booking.to_dict()}), 200
