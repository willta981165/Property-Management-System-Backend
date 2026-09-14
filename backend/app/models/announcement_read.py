from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint
from ..extensions import db


class AnnouncementRead(db.Model):
    __tablename__ = 'announcement_reads'
    __table_args__ = (UniqueConstraint('announcement_id', 'resident_id'),)

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False)
    resident_id = db.Column(db.Integer, db.ForeignKey('residents.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    read_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'announcement_id': self.announcement_id,
            'resident_id': self.resident_id,
            'organization_id': self.organization_id,
            'read_at': self.read_at.isoformat() if self.read_at else None,
        }
