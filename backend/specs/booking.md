# Booking Spec（公設預約）

## Requirement: 住戶建立預約
`POST /api/resident/bookings`（需 resident JWT）
- 成功 → 201
- 超過容量 → 409
- 同時段重複預約 → 409

## Requirement: 住戶取消預約
`DELETE /api/resident/bookings/:id`（需 resident JWT）
- 成功 → 200
- 已過時段 → 400

## Requirement: 管理員取得預約總覽
`GET /api/admin/bookings/overview`（需 admin JWT）
- 成功 → 200，各公設當日預約統計

## Requirement: 管理員取得預約名單
`GET /api/admin/facilities/:id/bookings`（需 admin JWT）
- 支援 date、status、slot_id 篩選

## Requirement: 管理員強制取消
`PATCH /api/admin/bookings/:id/cancel`（需 admin JWT）
- 成功 → 200，觸發 booking_cancelled 通知

---

## Invariant: 狀態流
confirmed → checked_in → departed
confirmed → cancelled（住戶或管理員）
