import hashlib
import secrets
from datetime import datetime, timezone
from ..extensions import db

TOKEN_TTL_SECONDS = 45  # QR code valid for 45 seconds
TOKEN_PREFIX = {'facility_checkin': 'fci_', 'facility_departure': 'fdp_'}


class QrActionToken(db.Model):
    __tablename__ = 'qr_action_tokens'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    purpose = db.Column(db.String(50), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    subject_type = db.Column(db.String(20), nullable=False)   # 'booking'
    subject_id = db.Column(db.Integer, nullable=False)         # booking_id
    issued_to_user_id = db.Column(db.Integer, db.ForeignKey('residents.id'), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    @staticmethod
    def generate_raw(purpose: str) -> str:
        prefix = TOKEN_PREFIX.get(purpose, 'tok_')
        return prefix + secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def find_by_raw(cls, raw_token: str):
        return cls.query.filter_by(
            token_hash=cls.hash_token(raw_token)
        ).first()

    def is_valid(self) -> bool:
        now = datetime.now(timezone.utc)
        return (
            self.used_at is None
            and self.revoked_at is None
            and self.expires_at > now
        )

    def revoke(self):
        self.revoked_at = datetime.now(timezone.utc)

    def mark_used(self):
        self.used_at = datetime.now(timezone.utc)
