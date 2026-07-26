# [GateGuard facts]
# 1. Importers: run.py imports FacilitySlot for db.create_all(); admin_facility.py
#    for slot CRUD; resident_booking.py for availability check; admin_booking.py for filter.
# 2. NEW file — facility_slots table: id, facility_id FK→facilities.id,
#    start_time Time, end_time Time, sort_order int.
# 3. Affected APIs: GET/POST/DELETE /api/admin/facilities/:id/slots
#    GET /api/facilities/:id/slots?date=
# 4. User: "管理員追加公設的時候 可以自訂時間區段 像是 8:00~9:00 9:00~10:00 10:00~11:00
#    然後用戶在預約公設的時候也可以看到各個時間區段 可以選擇自己要的時間區段"
from ..extensions import db


class FacilitySlot(db.Model):
    __tablename__ = 'facility_slots'

    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'facility_id': self.facility_id,
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M'),
            'sort_order': self.sort_order,
        }
