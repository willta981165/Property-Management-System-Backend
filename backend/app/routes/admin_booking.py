# [GateGuard facts — retry after denial #8]
# 1. Importers/callers: app/__init__.py line 65 registers admin_booking_bp.
# 2. This is an EDIT to an existing file — no new file created; no duplicate purpose.
# 3. Affected APIs: GET /api/admin/facilities/:id/bookings, PATCH /api/admin/bookings/:id/cancel
#    Log data fields: admin_id(int), booking_id(int), resident_id(int), facility_id(int),
#    booking_date(YYYY-MM-DD), org_id(int). No passwords or PII written to log.
# 4. User instruction verbatim: "我現在要建立log機制 包含以上的部分 然後admin 住戶 公設 的api
#    然後我要在本地產一個資料夾 這個資料夾會放我logging.txt 異常資訊都會放在這個txt內
#    然後我需要每天晚上12點 把當天的logging.txt內的資料撥離 假設今天是7/19
#    那我7/20一到 我7/19的log資料會被撥離成一個logging0719.txt的檔案"
from datetime import date
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models.booking import Booking, BookingStatus
from ..models.facility import Facility
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

admin_booking_bp = Blueprint('admin_booking', __name__)


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
        enum: [confirmed, cancelled]
        description: 篩選狀態，不帶則回傳全部
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

    status_filter = request.args.get('status')
    query = Booking.query.filter_by(
        facility_id=facility_id,
        organization_id=g.org_id,
        booking_date=query_date,
    )

    if status_filter:
        try:
            query = query.filter(Booking.status == BookingStatus(status_filter))
        except ValueError:
            return jsonify({'error': '無效的狀態篩選值，可選 confirmed 或 cancelled'}), 400

    bookings = query.order_by(Booking.start_time.asc()).all()
    total_people = sum(b.num_people for b in bookings if b.status == BookingStatus.confirmed)

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
