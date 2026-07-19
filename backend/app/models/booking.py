import enum
from datetime import datetime, timezone
from ..extensions import db


class BookingStatus(enum.Enum):
    confirmed = 'confirmed'
    cancelled = 'cancelled'


class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'), nullable=False)
    resident_id = db.Column(db.Integer, db.ForeignKey('residents.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    num_people = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.Enum(BookingStatus), nullable=False, default=BookingStatus.confirmed)
    notes = db.Column(db.Text, nullable=True)
    cancelled_by_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    facility = db.relationship('Facility', backref='bookings', lazy=True)
    resident = db.relationship('Resident', backref='bookings', lazy=True)

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
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M'),
            'num_people': self.num_people,
            'status': self.status.value,
            'notes': self.notes,
            'cancelled_by_admin': self.cancelled_by_admin,
            'created_at': self.created_at.isoformat(),
        }
