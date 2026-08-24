import enum
from datetime import datetime, timezone
from ..extensions import db


class ParcelSize(enum.Enum):
    small = 'small'
    medium = 'medium'
    large = 'large'


class ParcelStatus(enum.Enum):
    pending = 'pending'
    overdue = 'overdue'
    picked_up = 'picked_up'
    returned = 'returned'
    abnormal = 'abnormal'


class Parcel(db.Model):
    __tablename__ = 'parcels'

    id = db.Column(db.Integer, primary_key=True)
    parcel_code = db.Column(db.String(20), unique=True, nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    resident_id = db.Column(db.Integer, db.ForeignKey('residents.id'), nullable=False)
    registered_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    logistics_company = db.Column(db.String(50), nullable=False)
    size = db.Column(db.Enum(ParcelSize), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    storage_location = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    arrived_at = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(
        db.Enum(ParcelStatus), nullable=False, default=ParcelStatus.pending,
    )
    picked_up_at = db.Column(db.DateTime(timezone=True), nullable=True)
    signature_data = db.Column(db.Text, nullable=True)
    abnormal_reason = db.Column(db.Text, nullable=True)
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
    registered_by = db.relationship('Admin', lazy=True)

    def to_dict(self):
        r = self.resident
        return {
            'id': self.id,
            'parcel_code': self.parcel_code,
            'organization_id': self.organization_id,
            'resident': {
                'id': r.id,
                'name': r.name,
                'unit_code': r.unit_code,
            } if r else None,
            'registered_by_admin_id': self.registered_by_admin_id,
            'logistics_company': self.logistics_company,
            'size': self.size.value if self.size else None,
            'quantity': self.quantity,
            'storage_location': self.storage_location,
            'notes': self.notes,
            'arrived_at': self.arrived_at.isoformat() if self.arrived_at else None,
            'status': self.status.value if self.status else None,
            'picked_up_at': self.picked_up_at.isoformat() if self.picked_up_at else None,
            'abnormal_reason': self.abnormal_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
