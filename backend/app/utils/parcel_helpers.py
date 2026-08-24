from datetime import datetime, timezone, timedelta
from ..extensions import db
from ..models.parcel import ParcelStatus

OVERDUE_DAYS = 7
CLOSED_STATUSES = {ParcelStatus.picked_up, ParcelStatus.returned, ParcelStatus.abnormal}


def utc_now():
    return datetime.now(timezone.utc)


def make_aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def lazy_overdue_single(parcel):
    if parcel.status == ParcelStatus.pending:
        if make_aware(parcel.arrived_at) + timedelta(days=OVERDUE_DAYS) < utc_now():
            parcel.status = ParcelStatus.overdue
            db.session.commit()


def lazy_overdue_batch(parcels):
    needs_commit = False
    for p in parcels:
        if p.status == ParcelStatus.pending:
            if make_aware(p.arrived_at) + timedelta(days=OVERDUE_DAYS) < utc_now():
                p.status = ParcelStatus.overdue
                needs_commit = True
    if needs_commit:
        db.session.commit()


def compute_days(parcel):
    days_waiting = (utc_now() - make_aware(parcel.arrived_at)).days
    if parcel.status == ParcelStatus.pending:
        return days_waiting, max(0, OVERDUE_DAYS - days_waiting), None
    if parcel.status == ParcelStatus.overdue:
        return days_waiting, None, max(0, days_waiting - OVERDUE_DAYS)
    return days_waiting, None, None
