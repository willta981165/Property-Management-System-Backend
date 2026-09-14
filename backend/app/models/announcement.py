from datetime import datetime, timezone
from ..extensions import db


class AnnouncementCategory(db.Model):
    __tablename__ = 'announcement_categories'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(30), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
        }


class Announcement(db.Model):
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('announcement_categories.id'), nullable=True)
    title = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    category = db.relationship('AnnouncementCategory', lazy=True)
    attachments = db.relationship('AnnouncementAttachment', lazy=True, cascade='all, delete-orphan')
    reads = db.relationship('AnnouncementRead', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_attachments=False, read_count=None):
        now = datetime.now(timezone.utc)
        data = {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'category': self.category.to_dict() if self.category else None,
            'is_pinned': self.is_pinned,
            'is_expired': bool(self.expires_at and self.expires_at < now),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_by_admin_id': self.created_by_admin_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_attachments:
            data['attachments'] = [a.to_dict() for a in self.attachments]
            data['attachment_count'] = len(self.attachments)
        if read_count is not None:
            data['read_count'] = read_count
        return data


class AnnouncementAttachment(db.Model):
    __tablename__ = 'announcement_attachments'

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'original_filename': self.original_filename,
            'mime_type': self.mime_type,
            'file_size': self.file_size,
        }
