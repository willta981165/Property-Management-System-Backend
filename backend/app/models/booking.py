# [GateGuard facts]
# 1. Importers: routes/resident_booking.py (create_booking, my_bookings, cancel,
#    checkin, departure), routes/admin_booking.py (list_facility_bookings,
#    bookings_overview, cancel_booking), run.py
# 2. EDIT existing file — replaced start_time/end_time columns with slot_id FK
#    → facility_slots.id; added slot relationship.
# 3. bookings table fields: id, organization_id(FK), facility_id(FK), resident_id(FK),
#    slot_id(int NOT NULL FK→facility_slots.id), booking_date(date), num_people(int),
#    status(enum: confirmed/checked_in/departed/cancelled), notes(text),
#    cancelled_by_admin(bool), checked_in_at(datetime nullable), departed_at(datetime nullable)
# 4. User verbatim: "用戶在預約公設的時候也可以看到各個時間區段 可以選擇自己要的時間區段
#    每個時段的預約人數 已報到 已離場 已預約 已取消 會依照住戶的預約 都會不同"
import enum
from datetime import datetime, timezone
from ..extensions import db


class BookingStatus(enum.Enum):
    confirmed  = 'confirmed'   # 已預約
    checked_in = 'checked_in'  # 已報到
    departed   = 'departed'    # 已離場
    cancelled  = 'cancelled'   # 已取消


class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'), nullable=False)
    resident_id = db.Column(db.Integer, db.ForeignKey('residents.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('facility_slots.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    num_people = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.Enum(BookingStatus), nullable=False, default=BookingStatus.confirmed)
    notes = db.Column(db.Text, nullable=True)
    cancelled_by_admin = db.Column(db.Boolean, nullable=False, default=False)
    checked_in_at = db.Column(db.DateTime, nullable=True)
    departed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    facility = db.relationship('Facility', backref='bookings', lazy=True)
    resident = db.relationship('Resident', backref='bookings', lazy=True)
    slot = db.relationship('FacilitySlot', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'facility_id': self.facility_id,
            'facility_name': self.facility.name if self.facility else None,
            'facility_icon': self.facility.icon if self.facility else None,
            'resident_id': self.resident_id,
            'resident_name': self.resident.name if self.resident else None,
            'resident_unit_code': self.resident.unit_code if self.resident else None,
            'booking_date': self.booking_date.isoformat(),
            'slot_id': self.slot_id,
            'start_time': self.slot.start_time.strftime('%H:%M') if self.slot else None,
            'end_time': self.slot.end_time.strftime('%H:%M') if self.slot else None,
            'num_people': self.num_people,
            'status': self.status.value,
            'notes': self.notes,
            'cancelled_by_admin': self.cancelled_by_admin,
            'checked_in_at': self.checked_in_at.isoformat() if self.checked_in_at else None,
            'departed_at': self.departed_at.isoformat() if self.departed_at else None,
            'created_at': self.created_at.isoformat(),
        }
