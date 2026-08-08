import secrets
from datetime import datetime, timezone
from ..extensions import db

VERIFICATION_TTL_SECONDS = 180  # 3 minutes to confirm after verify


class QrVerification(db.Model):
    __tablename__ = 'qr_verifications'

    id = db.Column(db.Integer, primary_key=True)
    verification_id = db.Column(db.String(30), unique=True, nullable=False, index=True)
    token_id = db.Column(db.Integer, db.ForeignKey('qr_action_tokens.id'), nullable=False)
    verified_by_admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=False)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    result = db.Column(db.String(20), nullable=False, default='pending')

    token = db.relationship('QrActionToken', lazy=True)

    @staticmethod
    def generate_id() -> str:
        return 'qrv_' + secrets.token_urlsafe(16)

    def is_valid(self) -> bool:
        now = datetime.now(timezone.utc)
        return (
            self.confirmed_at is None
            and self.result == 'pending'
            and self.expires_at > now
        )
