# [GateGuard facts]
# 1. Importers: routes/admin_facility.py (all facility CRUD), routes/resident_booking.py
#    (list_facilities, get_facility, create_booking, checkin, departure),
#    routes/admin_booking.py (bookings_overview, list_facility_bookings), run.py
# 2. EDIT existing file — open_time/close_time changed to nullable=True (admin-defined
#    slots now handle time validation); added slots relationship.
# 3. facilities table fields: id, organization_id(FK), name(str200), icon(str100),
#    is_active(bool), open_time(Time nullable), close_time(Time nullable),
#    max_capacity(int), rules(text), sort_order(int), current_occupancy(int default=0)
# 4. User verbatim: "管理員追加公設的時候 可以自訂時間區段 像是 8:00~9:00 9:00~10:00
#    10:00~11:00 這樣追加 然後用戶在預約公設的時候也可以看到各個時間區段 可以選擇自己要的時間區段
#    每個時段的容納人數都一樣 所以這個是唯一"
from datetime import datetime, timezone
from ..extensions import db


class Facility(db.Model):
    __tablename__ = 'facilities'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    open_time = db.Column(db.Time, nullable=True)
    close_time = db.Column(db.Time, nullable=True)
    max_capacity = db.Column(db.Integer, nullable=False, default=10)
    rules = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    current_occupancy = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    slots = db.relationship('FacilitySlot', backref='facility', lazy=True,
                            order_by='FacilitySlot.sort_order')

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'name': self.name,
            'icon': self.icon,
            'is_active': self.is_active,
            'open_time': self.open_time.strftime('%H:%M') if self.open_time else None,
            'close_time': self.close_time.strftime('%H:%M') if self.close_time else None,
            'max_capacity': self.max_capacity,
            'rules': self.rules,
            'sort_order': self.sort_order,
            'current_occupancy': self.current_occupancy,
            'slots': [s.to_dict() for s in self.slots],
        }
