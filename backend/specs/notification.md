# Notification Spec（住戶鈴鐺通知）

## Requirement: 取得通知列表
`GET /api/resident/notifications`（需 resident JWT）
- 成功 → 200，回傳最新 50 筆通知及 unread_count
- 非住戶 token → 403

回傳格式：
```json
{
  "unread_count": 3,
  "notifications": [
    {
      "id": 1,
      "type": "parcel_arrived",
      "title": "包裹已到達",
      "body": "您有一件來自「黑貓宅急便」的包裹待領取，請至管理處領取。",
      "is_read": false,
      "related_type": "parcel",
      "related_id": 5,
      "created_at": "2026-10-16T10:00:00"
    }
  ]
}
```

## Requirement: 全部標為已讀（鈴鐺歸零）
`PATCH /api/resident/notifications/read-all`（需 resident JWT）
- 成功 → 200，所有 is_read=false 的通知改為 true
- 非住戶 token → 403

---

## Invariant: 通知觸發時機

| type | 觸發位置 | 觸發條件 |
|------|---------|---------|
| `parcel_arrived` | `admin_parcel.py` → `create_parcel` | 管理員登記包裹時 |
| `repair_updated` | `admin_repair.py` → `update_repair` | 狀態變更為 in_progress 或 completed |
| `booking_cancelled` | `admin_booking.py` → `cancel_booking` | 管理員強制取消預約 |
| `booking_checkin` | `admin_qr.py` → `confirm_checkin` | QR 報到確認完成 |
| `booking_departed` | `admin_qr.py` → `confirm_departure` | QR 離場確認完成 |

## Invariant: 通知寫入方式
- 所有通知使用 `push_notification()` helper 加入 session
- 不單獨 commit，與觸發點的業務操作在同一個 transaction 完成
- 任一環節 rollback，通知也一併取消

## Invariant: 鈴鐺角標來源
- `GET /api/resident/dashboard/summary` 回傳的 `notification_unread` = notifications table 中 is_read=false 的數量
- 使用者點開鈴鐺後，前端呼叫 `PATCH /read-all` 將所有通知標為已讀，角標歸零
