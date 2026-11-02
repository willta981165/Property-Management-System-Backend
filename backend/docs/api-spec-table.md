# API 規格總表

> 所有 API 路徑皆帶 `/api` prefix（Nginx 代理後去除）。  
> 認證方式：`Authorization: Bearer <access_token>`（除 `/admin/register`、`/login`、`/org/:org_code` 外）

---

## 全域規則

| 項目 | 說明 |
|------|------|
| 資料格式 | JSON（`Content-Type: application/json`） |
| 資料隔離 | 所有資料以 `org_id` 隔離，跨 org 存取回 403 / 404 |
| 成功格式 | `{"message": "...", "data": ...}` |
| 錯誤格式 | `{"error": "..."}` |
| 時間格式 | ISO 8601 UTC（`2026-10-30T08:00:00+00:00`） |

---

## 一、Auth（認證）

### 1-1 管理員註冊
`POST /admin/register`（無需 JWT）

| 欄位 | 型別 | 必填 | 限制 | 說明 |
|------|------|:----:|------|------|
| `org_code` | string | ✅ | 大寫，格式 `XXXX-0000` | 建案代碼 |
| `name` | string | ✅ | 無長度限制 | 管理員姓名 |
| `employee_id` | string | ✅ | 格式 `ID-\d{4}`（如 ID-0001），同 org 唯一 | 員工編號 |
| `department` | string | ✅ | 無長度限制 | 部門名稱 |
| `email` | string | — | 合法 email 格式，同 org 唯一 | 選填 |
| `password` | string | ✅ | **最少 8 碼** | 密碼 |
| `confirm_password` | string | ✅ | 必須與 `password` 相同 | 確認密碼 |

**回應**

| 狀態碼 | 情境 |
|:------:|------|
| 201 | 成功，回傳 `access_token` + `refresh_token` + `user` |
| 400 | 必填欄位缺失 / `employee_id` 格式錯誤 / 密碼不足 8 碼 / 兩次密碼不符 |
| 404 | `org_code` 不存在 |
| 409 | `employee_id` 或 `email` 在此建案已被使用 |

---

### 1-2 登入（管理員 & 住戶共用）
`POST /login`（無需 JWT）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `org_code` | string | ✅ | 建案代碼（不分大小寫） |
| `identifier` | string | ✅ | 管理員填 `employee_id` 或 `email`；住戶填 `unit_code` 或手機號碼 |
| `password` | string | ✅ | 密碼 |

**回應**

| 狀態碼 | 情境 |
|:------:|------|
| 200 | 成功，回傳 `access_token` + `refresh_token` + `user` |
| 400 | 欄位缺失 / `org_code` 無效 |
| 401 | 帳號或密碼錯誤 |
| 403 | 帳號已停用 |

**JWT Claims 內容**

| user_type | claims |
|-----------|--------|
| admin | `user_type=admin` · `org_id` · `role=admin` |
| resident | `user_type=resident` · `org_id` · `role=owner/tenant/family` |

---

### 1-3 Refresh Token
`POST /refresh`（需 **Refresh** JWT）

| Header | 說明 |
|--------|------|
| `Authorization: Bearer <refresh_token>` | 用 Refresh Token，不是 Access Token |

**回應**：200 回傳新 `access_token`；401 無效 token 或帳號停用

---

### 1-4 取得目前登入者資料
`GET /me`（需 JWT）

**回應**：200 回傳 `user` 物件；403 帳號已停用

---

### 1-5 修改密碼（管理員 & 住戶共用）
`PUT /change-password`（需 JWT）

| 欄位 | 型別 | 必填 | 限制 |
|------|------|:----:|------|
| `current_password` | string | ✅ | 當前密碼 |
| `new_password` | string | ✅ | **管理員最少 8 碼；住戶最少 6 碼** |
| `confirm_password` | string | — | 選填，若填則必須與 `new_password` 相同 |

**回應**：200 成功；400 格式錯誤 / 目前密碼錯誤；403 帳號停用

---

## 二、Organization（建案）

### 2-1 查詢建案代碼是否有效
`GET /org/:org_code`（無需 JWT）

| 路徑參數 | 說明 |
|----------|------|
| `org_code` | 建案代碼（自動轉大寫） |

**回應**：200 回傳 `{name, org_code}`；404 無效

---

## 三、Admin — 住戶管理

### 3-1 取得住戶列表
`GET /admin/residents`（需 Admin JWT）

| Query 參數 | 型別 | 預設 | 說明 |
|-----------|------|------|------|
| `page` | integer | 1 | 頁碼 |
| `per_page` | integer | 20 | 每頁筆數 |
| `role` | string | — | `resident` 或 `family` |

---

### 3-2 建立住戶帳號
`POST /admin/residents`（需 Admin JWT）

| 欄位 | 型別 | 必填 | 限制 |
|------|------|:----:|------|
| `name` | string | ✅ | 無限制 |
| `unit_code` | string | ✅ | 同 org 唯一（如 A101） |
| `phone` | string | — | 同 org 唯一 |
| `email` | string | — | 同 org 唯一 |
| `password` | string | ✅ | 無最低長度限制（由管理員設初始密碼） |
| `role` | string | — | `resident`（預設）或 `family` |
| `notes` | string | — | 備註 |

**回應**：201 成功；400 缺必填；409 unit_code / phone / email 衝突

---

### 3-3 更新住戶資料 / 重設密碼
`PUT /admin/residents/:id`（需 Admin JWT）

所有欄位皆選填（Partial Update）。傳入 `password` 即為重設密碼（無最低長度限制）。

| 欄位 | 說明 |
|------|------|
| `name` | 姓名 |
| `unit_code` | 戶號（不可與同 org 其他住戶衝突） |
| `phone` | 手機 |
| `email` | 信箱 |
| `password` | 填入即重設密碼 |
| `role` | `resident` 或 `family` |
| `notes` | 備註 |
| `is_active` | boolean，`false` = 停用帳號 |

---

### 3-4 刪除住戶
`DELETE /admin/residents/:id`（需 Admin JWT）

**回應**：200 成功；404 找不到

---

## 四、Facility（公設）

### 4-1 取得公設列表
`GET /admin/facilities`（需 Admin JWT）
依 `sort_order` 排序，回傳所有公設。

### 4-2 建立公設
`POST /admin/facilities`（需 Admin JWT）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `name` | string | ✅ | 公設名稱 |
| `icon` | string | — | 圖示識別碼 |
| `max_capacity` | integer | ✅ | 最大容量 |
| `rules` | string | — | 使用規則說明 |
| `sort_order` | integer | — | 排序（預設 0） |

### 4-3 更新公設
`PATCH /admin/facilities/:id`（需 Admin JWT）— 所有欄位選填

### 4-4 取得時段列表
`GET /admin/facilities/:id/slots`（需 Admin JWT）

### 4-5 建立時段
`POST /admin/facilities/:id/slots`（需 Admin JWT）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `label` | string | ✅ | 時段名稱（如「09:00–11:00」） |
| `sort_order` | integer | — | 排序 |

---

## 五、Booking（預約）

### 5-1 住戶建立預約
`POST /resident/bookings`（需 Resident JWT）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `slot_id` | integer | ✅ | 時段 ID |
| `booking_date` | string | ✅ | 日期，格式 `YYYY-MM-DD` |
| `num_people` | integer | ✅ | 人數 |
| `notes` | string | — | 備註 |

**回應**：201 成功；409 超過容量 / 同時段重複預約

### 5-2 住戶取消預約
`DELETE /resident/bookings/:id`（需 Resident JWT）
**回應**：200 成功；400 時段已過

### 5-3 管理員查看每日預約概覽
`GET /admin/bookings/overview`（需 Admin JWT）
回傳各公設當日預約統計。

### 5-4 管理員查看特定公設預約名單
`GET /admin/facilities/:id/bookings`（需 Admin JWT）

| Query 參數 | 說明 |
|-----------|------|
| `date` | 篩選日期（`YYYY-MM-DD`） |
| `status` | `confirmed` / `checked_in` / `departed` / `cancelled` |
| `slot_id` | 篩選時段 |

### 5-5 管理員強制取消預約
`PATCH /admin/bookings/:id/cancel`（需 Admin JWT）
觸發 `booking_cancelled` 通知。

**預約狀態流：**
```
confirmed → checked_in → departed
confirmed → cancelled（住戶主動 或 管理員強制）
```

---

## 六、QR Code（報到 / 離場）

### 6-1 住戶產生 QR Token
`POST /resident/qr/generate`（需 Resident JWT）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `booking_id` | integer | ✅ | 要報到的預約 ID |
| `purpose` | string | ✅ | `checkin` 或 `departure` |

**回應**：200 回傳 `token`（有效 45 秒）

### 6-2 管理員掃描驗證（唯讀）
`POST /admin/qr/verify`（需 Admin JWT）

| 欄位 | 型別 | 必填 |
|------|------|:----:|
| `token` | string | ✅ |

**回應**：200 回傳 `verification_id` + 預約資料（不改變狀態）

### 6-3 管理員確認報到
`POST /admin/facility-checkins/confirm`（需 Admin JWT）

| 欄位 | 型別 | 必填 |
|------|------|:----:|
| `verification_id` | integer | ✅ |
| `token` | string | ✅ |

**回應**：200 → booking 改 `checked_in`，觸發 `booking_checkin` 通知；409 已報到（防重複）

### 6-4 管理員確認離場
`POST /admin/facility-departures/confirm`（需 Admin JWT）

| 欄位 | 型別 | 必填 |
|------|------|:----:|
| `verification_id` | integer | ✅ |
| `token` | string | ✅ |

**回應**：200 → booking 改 `departed`，觸發 `booking_departed` 通知

**Token 規則：**

| 項目 | 值 |
|------|----|
| Token TTL | **45 秒** |
| 驗證確認 TTL | **180 秒** |
| 儲存方式 | SHA-256 hash，不儲存明文 |
| Purpose prefix | `fci_`（報到）/ `fdp_`（離場） |
| 防重複 | SELECT FOR UPDATE；第二台同時確認回 409 |

---

## 七、Repair（報修）

### 7-1 住戶建立報修單
`POST /resident/repairs`（需 Resident JWT）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `title` | string | ✅ | 報修標題 |
| `description` | string | ✅ | 問題描述 |
| `category_id` | integer | — | 維修類別 ID |
| `location` | string | — | 位置描述 |

### 7-2 住戶查詢自己的報修單列表
`GET /resident/repairs`（需 Resident JWT）

### 7-3 管理員查詢報修單列表
`GET /admin/repairs`（需 Admin JWT）

| Query 參數 | 說明 |
|-----------|------|
| `status` | `pending` / `in_progress` / `completed` |
| `category_id` | 篩選類別 |

### 7-4 管理員更新報修單
`PATCH /admin/repairs/:id`（需 Admin JWT）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | string | `pending` → `in_progress` → `completed` |
| `admin_reply` | string | 管理員回覆 |
| `scheduled_date` | string | 維修預約日期 |

狀態變更為 `in_progress` 或 `completed` 時觸發 `repair_updated` 通知。

### 7-5 維修類別管理
| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/admin/repair-categories` | 取得類別列表 |
| POST | `/admin/repair-categories` | 新增類別（需 `name` 欄位） |
| DELETE | `/admin/repair-categories/:id` | 刪除類別 |

**工單編號格式：** `REQ-YYYYMM{id:04d}`（如 REQ-2026100001）

**報修狀態流：**
```
pending → in_progress → completed
```

---

## 八、Parcel（包裹）

### 8-1 管理員登記包裹
`POST /admin/parcels`（需 Admin JWT）— 觸發 `parcel_arrived` 通知

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `resident_id` | integer | ✅ | 住戶 ID |
| `sender` | string | ✅ | 寄件人 / 快遞公司名稱 |
| `tracking_number` | string | — | 追蹤號碼 |
| `notes` | string | — | 備註 |

### 8-2 管理員取得包裹列表
`GET /admin/parcels`（需 Admin JWT）

| Query 參數 | 說明 |
|-----------|------|
| `status` | `pending` / `overdue` / `picked_up` / `returned` / `abnormal` |
| `q` | 搜尋住戶姓名 / unit_code |

### 8-3 管理員確認領取
`POST /admin/parcels/:id/pickup`（需 Admin JWT）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `signature_data` | string | ✅ | 住戶簽名 Base64 字串 |

### 8-4 管理員更新逾期包裹狀態
`PUT /admin/parcels/:id/status`（需 Admin JWT）
只能對 `overdue` 狀態包裹操作，新狀態僅限 `returned` 或 `abnormal`。

| 欄位 | 型別 | 必填 |
|------|------|:----:|
| `status` | string | ✅ |

### 8-5 管理員搜尋住戶（登記包裹用）
`GET /admin/parcels/residents/search`（需 Admin JWT）

| Query 參數 | 說明 |
|-----------|------|
| `q` | 搜尋 unit_code / 姓名 |

### 8-6 住戶取得我的包裹列表
`GET /resident/parcels`（需 Resident JWT）

| Query 參數 | 說明 |
|-----------|------|
| `status` | 篩選狀態 |

### 8-7 住戶取得包裹詳情
`GET /resident/parcels/:id`（需 Resident JWT）

**包裹規則：**

| 項目 | 規則 |
|------|------|
| 包裹編號格式 | `PCL-YYYYMM{id:04d}`（如 PCL-2026100001） |
| 逾期判斷 | 到達後超過設定天數未領，API 查詢時 lazy update |
| 狀態流 | `pending` → `overdue` → `picked_up` / `returned` / `abnormal` |

---

## 九、Notification（通知）

### 9-1 住戶取得通知列表
`GET /resident/notifications`（需 Resident JWT）

回傳格式：
```json
{
  "unread_count": 3,
  "notifications": [
    {
      "id": 1,
      "type": "parcel_arrived",
      "title": "包裹已到達",
      "body": "您有一件來自「黑貓宅急便」的包裹待領取",
      "is_read": false,
      "related_type": "parcel",
      "related_id": 5,
      "created_at": "2026-10-30T08:00:00"
    }
  ]
}
```

最多回傳最新 **50 筆**。

### 9-2 全部標為已讀
`PATCH /resident/notifications/read-all`（需 Resident JWT）
**回應**：200 成功；403 非住戶 token

**通知觸發時機：**

| type | 觸發情境 |
|------|---------|
| `parcel_arrived` | 管理員登記包裹 |
| `repair_updated` | 報修狀態變更為 in_progress 或 completed |
| `booking_cancelled` | 管理員強制取消預約 |
| `booking_checkin` | QR 報到確認完成 |
| `booking_departed` | QR 離場確認完成 |

---

## 十、Dashboard（住戶首頁角標）

### 10-1 取得角標總覽
`GET /resident/dashboard/summary`（需 Resident JWT）

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

| 欄位 | 計算條件 |
|------|---------|
| `parcel_pending` | parcels.status IN (pending, overdue) |
| `announcement_unread` | 未過期公告 且 無該住戶讀取記錄 |
| `repair_active` | repair_tickets.status IN (pending, in_progress) |
| `booking_upcoming` | bookings.status=confirmed 且 booking_date >= 今日 |
| `notification_unread` | notifications.is_read=false |

---

## 十一、Announcement（公告）

### 11-1 管理員建立公告
`POST /admin/announcements`（需 Admin JWT）
支援附件上傳（`multipart/form-data`）

| 欄位 | 型別 | 必填 | 限制 |
|------|------|:----:|------|
| `title` | string | ✅ | 公告標題 |
| `content` | string | ✅ | 公告內文 |
| `is_pinned` | boolean | — | 是否置頂（預設 false） |
| `expires_at` | string | — | 過期時間（ISO 8601） |
| `category_id` | integer | — | 公告類別 |
| `attachment` | file | — | PDF / Word / Excel / 圖片，**上限 10MB** |

### 11-2 管理員取得公告列表
`GET /admin/announcements`（需 Admin JWT）

### 11-3 管理員刪除公告
`DELETE /admin/announcements/:id`（需 Admin JWT）

### 11-4 住戶取得公告列表
`GET /resident/announcements`（需 Resident JWT）
只回傳**未過期**公告。

### 11-5 住戶標記已讀
`POST /resident/announcements/:id/read`（需 Resident JWT）
寫入 `announcement_reads` 表。

### 11-6 附件下載
`GET /resident/announcements/:id/attachment`（需 Resident JWT）
回傳檔案串流。

### 11-7 公告類別管理
| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/admin/announcement-categories` | 取得類別列表 |
| POST | `/admin/announcement-categories` | 新增類別 |
| DELETE | `/admin/announcement-categories/:id` | 刪除類別 |

---

## 附錄 A：帳號密碼規則速查

| 使用者 | 登入識別碼 | 密碼最低長度 | 備註 |
|--------|-----------|:----------:|------|
| **管理員** | `employee_id`（格式 `ID-\d{4}`）或 `email` | **8 碼** | 註冊 & 改密皆需 ≥8 |
| **住戶** | `unit_code` 或手機號碼 | **6 碼** | 改密時限制；管理員建立初始密碼無最低限制 |

## 附錄 B：狀態碼速查

| 狀態碼 | 語意 |
|:------:|------|
| 200 | 成功 |
| 201 | 建立成功 |
| 400 | 欄位驗證失敗 / 格式錯誤 |
| 401 | 未認證 / 帳密錯誤 |
| 403 | 無權限 / 帳號停用 |
| 404 | 資源不存在 |
| 409 | 唯一性衝突（重複） |

## 附錄 C：編號格式速查

| 模組 | 格式 | 範例 |
|------|------|------|
| 員工編號 | `ID-\d{4}` | ID-0001 |
| 建案代碼 | `XXXX-0000`（大寫） | HAPPY-0001 |
| 包裹編號 | `PCL-YYYYMM{id:04d}` | PCL-2026100001 |
| 工單編號 | `REQ-YYYYMM{id:04d}` | REQ-2026100001 |
