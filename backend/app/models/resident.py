import enum
from datetime import datetime
from ..extensions import db, bcrypt


class ResidentRole(enum.Enum):
    resident = 'resident'
    family = 'family'


class Resident(db.Model):
    __tablename__ = 'residents'
    __table_args__ = (
        db.UniqueConstraint('unit_code', 'organization_id', name='uq_resident_unit_org'),
        db.UniqueConstraint('phone', 'organization_id', name='uq_resident_phone_org'),
        db.UniqueConstraint('email', 'organization_id', name='uq_resident_email_org'),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    unit_code = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(ResidentRole), nullable=False, default=ResidentRole.resident)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)

    def set_password(self, password: str):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'name': self.name,
            'unit_code': self.unit_code,
            'phone': self.phone,
            'email': self.email,
            'role': self.role.value,
            'notes': self.notes,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
