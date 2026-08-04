from datetime import datetime, timezone
from ..extensions import db


class RepairCategory(db.Model):
    __tablename__ = 'repair_categories'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    icon = db.Column(db.String(50), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    tickets = db.relationship('RepairTicket', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'sort_order': self.sort_order,
        }
