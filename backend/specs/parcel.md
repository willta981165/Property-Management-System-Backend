# Parcel Spec（包裹管理）

## Requirement: 管理員登記包裹
`POST /api/admin/parcels`（需 admin JWT）
- 成功 → 201，觸發 parcel_arrived 通知

## Requirement: 管理員取得包裹列表
`GET /api/admin/parcels`（需 admin JWT）
- 支援 status（pending/overdue/closed）、q（搜尋住戶）篩選

## Requirement: 確認領取
`POST /api/admin/parcels/:id/pickup`（需 admin JWT）
- 成功 → 200，需提供 signature_data（Base64）

## Requirement: 更新逾期包裹狀態
`PUT /api/admin/parcels/:id/status`（需 admin JWT）
- 只可對 overdue 包裹操作，新狀態限 returned / abnormal

## Requirement: 住戶取得自己的包裹
`GET /api/resident/parcels`（需 resident JWT）

---

## Invariant: 逾期機制
- 到達後超過 OVERDUE_DAYS 天未領取，狀態自動標為 overdue（lazy evaluation）

## Invariant: parcel_code 格式
- `PCL-YYYYMM{id:04d}`，於 flush 後取得 id 再組合
