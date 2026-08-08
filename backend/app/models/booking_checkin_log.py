from datetime import datetime, timezone
from ..extensions import db


class BookingCheckinLog(db.Model):
    __tablename__ = 'booking_checkin_logs'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)   # verify / check_in
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    occurred_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    ip_address = db.Column(db.String(45), nullable=True)
    result = db.Column(db.String(20), nullable=False)   # success / failure
    trace_id = db.Column(db.String(36), nullable=True)
