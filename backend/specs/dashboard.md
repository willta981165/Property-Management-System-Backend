# Dashboard Spec（住戶首頁角標）

## Requirement: 取得角標總覽
`GET /api/resident/dashboard/summary`（需 resident JWT）
- 成功 → 200，一次回傳所有模組的未處理數量
- 非住戶 token → 403

回傳格式：
```json
{
  "parcel_pending": 2,
  "announcement_unread": 3,
  "repair_active": 1,
  "booking_upcoming": 2,
  "notification_unread": 1
}
```

---

## Invariant: 各欄位計算邏輯

| 欄位 | 計算條件 |
|------|---------|
| `parcel_pending` | parcels.status IN (pending, overdue)，屬於該住戶 |
| `announcement_unread` | 未過期公告 且 announcement_reads 中無該住戶讀取記錄 |
| `repair_active` | repair_tickets.status IN (pending, in_progress)，屬於該住戶 |
| `booking_upcoming` | bookings.status = confirmed 且 booking_date >= 今天，屬於該住戶 |
| `notification_unread` | notifications.is_read = false，屬於該住戶 |

## Invariant: 設計原則
- 單一 API 取代前端四次獨立請求，減少網路開銷
- 所有欄位皆為 COUNT，不回傳明細資料
