# QR Spec（QR Code 報到/離場）

## Requirement: 住戶產生 QR Token
`POST /api/resident/qr/generate`（需 resident JWT）
- 成功 → 200，回傳 token（有效期限內）

## Requirement: 管理員掃描驗證（唯讀）
`POST /api/admin/qr/verify`（需 admin JWT）
- 成功 → 200，回傳 verification_id 及預約資料
- 不改變報到狀態

## Requirement: 管理員確認報到
`POST /api/admin/facility-checkins/confirm`（需 admin JWT）
- 需 verification_id + token
- 成功 → 200，booking→checked_in，觸發 booking_checkin 通知

## Requirement: 管理員確認離場
`POST /api/admin/facility-departures/confirm`（需 admin JWT）
- 需 verification_id + token
- 成功 → 200，booking→departed，觸發 booking_departed 通知

---

## Invariant: 防重複報到
- SELECT FOR UPDATE 鎖定 token + verification + booking
- 兩台裝置同時確認，第二台回 409 BOOKING_ALREADY_CHECKED_IN

## Invariant: Token 生命週期
- token 一旦 used_at 不為 null，即視為已使用，不可再次觸發確認
