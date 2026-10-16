from ..extensions import db
from ..models.notification import Notification


def push_notification(org_id, resident_id, ntype, title, body,
                      related_type=None, related_id=None):
    """session.add only — caller is responsible for commit."""
    db.session.add(Notification(
        org_id=org_id,
        resident_id=resident_id,
        type=ntype,
        title=title,
        body=body,
        related_type=related_type,
        related_id=related_id,
    ))
