import enum
from datetime import datetime, timezone
from ..extensions import db


class RepairStatus(enum.Enum):
    pending = 'pending'
    in_progress = 'in_progress'
    completed = 'completed'


class RepairTicket(db.Model):
    __tablename__ = 'repair_tickets'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    resident_id = db.Column(db.Integer, db.ForeignKey('residents.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('repair_categories.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.Enum(RepairStatus), nullable=False, default=RepairStatus.pending,
    )
    appointment_date = db.Column(db.Date, nullable=True)
    appointment_slot = db.Column(db.String(20), nullable=True)  # e.g. "09:00-12:00"
    admin_reply = db.Column(db.Text, nullable=True)
    replied_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    replied_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    resident = db.relationship('Resident', lazy=True)
    replied_by = db.relationship('Admin', lazy=True)

    @property
    def ticket_number(self):
        prefix = self.created_at.strftime('%Y%m') if self.created_at else '000000'
        return f'REQ-{prefix}{self.id:04d}'

    def to_dict(self):
        r = self.resident
        return {
            'id': self.id,
            'ticket_number': self.ticket_number,
            'category': self.category.to_dict() if self.category else None,
            'title': self.title,
            'description': self.description,
            'status': self.status.value,
            'appointment_date': self.appointment_date.isoformat() if self.appointment_date else None,
            'appointment_slot': self.appointment_slot,
            'admin_reply': self.admin_reply,
            'replied_at': self.replied_at.isoformat() if self.replied_at else None,
            'replied_by': self.replied_by.name if self.replied_by else None,
            'resident': {
                'id': r.id,
                'name': r.name,
                'unit': r.unit,
                'phone': r.phone,
            } if r else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
