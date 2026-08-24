# 包裹管理功能 Spec

> 產出日期：2026-08-24  
> 由 Planner Agent 根據 UIUX 設計圖與產品討論產出  
> Model Agent 與 API Agent 開發前必須完整閱讀此文件與 CLAUDE.md

---

## 一、功能概述

社區管理員在前台登記住戶收到的包裹，住戶可在 App 查詢包裹狀態與存放位置。包裹超過 7 天未領取自動標記為逾期，管理員可進行後續處置（住戶領取 / 退回物流 / 標記異常）。

---

## 二、使用者角色

| 角色 | 可執行操作 |
|------|-----------|
| 管理員 (Admin) | 登記包裹、查看所有包裹、確認領取（走簽名流程）、更新逾期包裹狀態 |
| 住戶 (Resident) | 查看自己名下的包裹、查看包裹詳情與存放位置 |

---

## 三、包裹狀態流

```
pending（待領取）
    ├─ 住戶親自來領 ──────────────→ picked_up → 已結案 ✅
    └─ 超過 7 天 ──→ overdue（已逾期）
                        ├─ 住戶領取  ──→ picked_up  → 已結案 ✅
                        ├─ 已退回物流 ──→ returned   → 已結案 🔄
                        └─ 異常      ──→ abnormal   → 已結案 ⚠️
```

### 狀態說明

| 狀態 | Enum 值 | 說明 |
|------|---------|------|
| 待領取 | `pending` | 包裹已登記，等待住戶領取 |
| 已逾期 | `overdue` | 超過 7 天未領取，自動轉換 |
| 已領取 | `picked_up` | 住戶簽名確認領取，結案 |
| 已退回物流 | `returned` | 管理員標記退回，結案 |
| 異常 | `abnormal` | 管理員標記異常（含說明），結案 |

> **逾期判斷邏輯**：`arrived_at` + 7 天 < 當前時間，且狀態為 `pending`，系統自動轉為 `overdue`。  
> 實作方式：列表與詳情 API 回傳資料前，對 `pending` 包裹做 lazy update（不需背景排程）。

---

## 四、資料庫欄位設計

### Model：`Parcel`
**檔案：** `app/models/parcel.py`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer, PK | 主鍵 |
| `parcel_code` | String(20), unique | 系統自動產生，格式：`PCL-YYYYMM{id:04d}` |
| `organization_id` | Integer, FK → organizations.id | 建案隔離，必填 |
| `resident_id` | Integer, FK → residents.id | 收件住戶，必填 |
| `registered_by_admin_id` | Integer, FK → admins.id | 登記管理員 |
| `logistics_company` | String(50) | 物流公司名稱（黑貓、郵局、順豐等），必填 |
| `size` | Enum(ParcelSize) | 包裹大小：`small` / `medium` / `large`，必填 |
| `quantity` | Integer, default=1 | 件數，必填 |
| `storage_location` | String(100), nullable | 存放位置（大廳置物櫃 B3 / 管理室等） |
| `notes` | Text, nullable | 備註 |
| `arrived_at` | DateTime | 到貨日期，必填 |
| `status` | Enum(ParcelStatus) | 包裹狀態，default=`pending` |
| `picked_up_at` | DateTime, nullable | 領取時間（picked_up 時記錄） |
| `signature_data` | Text, nullable | 住戶簽名（base64 PNG 字串） |
| `abnormal_reason` | Text, nullable | 異常說明（status=abnormal 時必填） |
| `created_at` | DateTime | 建立時間（UTC） |
| `updated_at` | DateTime | 更新時間（UTC） |

### Enum 定義

```python
class ParcelSize(enum.Enum):
    small = "small"
    medium = "medium"
    large = "large"

class ParcelStatus(enum.Enum):
    pending = "pending"
    overdue = "overdue"
    picked_up = "picked_up"
    returned = "returned"
    abnormal = "abnormal"
```

### `parcel_code` 產生邏輯
在 route 建立 parcel 後，根據 id 產生並寫回 DB：
```python
parcel.parcel_code = f"PCL-{now.strftime('%Y%m')}{parcel.id:04d}"
```

---

## 五、API Endpoints

### 管理員端

#### 5.1 取得包裹列表
```
GET /admin/parcels
```
**權限：** `@admin_required`

**Query Params：**
| 參數 | 說明 |
|------|------|
| `status` | 篩選狀態：`pending` / `overdue` / `closed`（picked_up+returned+abnormal） |
| `q` | 搜尋（住戶 unit_code 或住戶姓名） |

**Response 200：**
```json
{
  "parcels": [
    {
      "id": 1,
      "parcel_code": "PCL-202608001",
      "resident": {
        "id": 10,
        "name": "王小明",
        "unit_code": "A-12F"
      },
      "logistics_company": "黑貓宅急便",
      "size": "medium",
      "quantity": 3,
      "storage_location": "大廳置物櫃 B3",
      "arrived_at": "2026-08-03T10:21:00+00:00",
      "status": "overdue",
      "days_waiting": 9,
      "overdue_days": 2,
      "created_at": "2026-08-03T10:21:00+00:00"
    }
  ]
}
```

> `days_waiting`：距今天數（arrived_at 起算）  
> `overdue_days`：逾期天數（超過 7 天後才有值，否則為 null）

---

#### 5.2 登記新包裹
```
POST /admin/parcels
```
**權限：** `@admin_required`

**Request Body：**
```json
{
  "resident_id": 10,
  "logistics_company": "黑貓宅急便",
  "size": "medium",
  "quantity": 3,
  "storage_location": "大廳置物櫃 B3",
  "notes": "易碎品",
  "arrived_at": "2026-08-03"
}
```

**驗證規則：**
- `resident_id`：必填，必須屬於同一 `organization_id`
- `logistics_company`：必填，非空字串
- `size`：必填，值必須為 `small` / `medium` / `large`
- `quantity`：必填，正整數
- `arrived_at`：必填，日期格式（YYYY-MM-DD）

**Response 201：**
```json
{
  "message": "包裹登記成功",
  "parcel": { "...to_dict()" : "..." }
}
```

---

#### 5.3 取得包裹詳情
```
GET /admin/parcels/<parcel_id>
```
**權限：** `@admin_required`

**Response 200：**
```json
{
  "id": 1,
  "parcel_code": "PCL-202608001",
  "resident": {
    "id": 10,
    "name": "王小明",
    "unit_code": "A-12F"
  },
  "logistics_company": "黑貓宅急便",
  "size": "medium",
  "quantity": 3,
  "storage_location": "大廳置物櫃 B3",
  "notes": "易碎品",
  "arrived_at": "2026-08-03T10:21:00+00:00",
  "status": "overdue",
  "days_waiting": 9,
  "overdue_days": 2,
  "days_remaining": null,
  "picked_up_at": null,
  "abnormal_reason": null,
  "status_timeline": [
    { "status": "pending", "label": "已登記", "at": "2026-08-03T10:21:00+00:00" },
    { "status": "overdue", "label": "已逾期", "at": "2026-08-10T10:21:00+00:00" }
  ],
  "created_at": "2026-08-03T10:21:00+00:00",
  "updated_at": "2026-08-11T00:00:00+00:00"
}
```

> `status_timeline` 由 API 層計算產生，不需獨立 DB 表：  
> - `pending` 時間 = `created_at`  
> - `overdue` 時間 = `arrived_at` + 7 天  
> - 後續終態時間 = `updated_at`

---

#### 5.4 更新逾期包裹狀態
```
PUT /admin/parcels/<parcel_id>/status
```
**權限：** `@admin_required`

**適用時機：** 包裹狀態為 `overdue`，管理員選擇退回物流或標記異常。

**Request Body（退回物流）：**
```json
{
  "status": "returned"
}
```

**Request Body（標記異常）：**
```json
{
  "status": "abnormal",
  "abnormal_reason": "住戶地址錯誤，包裹無人認領"
}
```

**驗證規則：**
- 只允許對 `overdue` 狀態的包裹操作，其他狀態回 400
- `status` 只接受 `returned` 或 `abnormal`，其他值回 400
- `status` 為 `abnormal` 時，`abnormal_reason` 必填

**Response 200：**
```json
{
  "message": "狀態更新成功",
  "parcel": { "...to_dict()" : "..." }
}
```

---

#### 5.5 確認住戶領取（簽名）
```
POST /admin/parcels/<parcel_id>/pickup
```
**權限：** `@admin_required`

**適用時機：** 包裹狀態為 `pending` 或 `overdue`，住戶親自到場領取。

**Request Body：**
```json
{
  "signature_data": "data:image/png;base64,iVBORw0KGgoAAAANS..."
}
```

**驗證規則：**
- 只允許對 `pending` 或 `overdue` 狀態的包裹操作，其他狀態回 400
- `signature_data` 必填，非空字串

**Response 200：**
```json
{
  "message": "領取確認成功",
  "parcel": {
    "id": 1,
    "parcel_code": "PCL-202608001",
    "status": "picked_up",
    "picked_up_at": "2026-08-14T14:32:00+00:00"
  }
}
```

---

#### 5.6 搜尋住戶（登記包裹表單用）
```
GET /admin/parcels/residents/search?unit_code=A-12F
```
**權限：** `@admin_required`

**說明：** 登記包裹時，輸入 unit_code 自動帶入住戶姓名與 resident_id。

**Response 200：**
```json
{
  "residents": [
    { "id": 10, "name": "王小明", "unit_code": "A-12F" }
  ]
}
```

---

### 住戶端

#### 5.7 取得我的包裹列表
```
GET /resident/parcels
```
**權限：** `@jwt_required()` + `user_type == resident`

**Query Params：**
| 參數 | 說明 |
|------|------|
| `status` | `pending` / `overdue` / `closed`（picked_up+returned+abnormal） |

**Response 200：**
```json
{
  "parcels": [
    {
      "id": 1,
      "parcel_code": "PCL-202608001",
      "logistics_company": "黑貓宅急便",
      "size": "medium",
      "quantity": 3,
      "storage_location": "大廳置物櫃 B3",
      "arrived_at": "2026-08-03T10:21:00+00:00",
      "status": "pending",
      "days_waiting": 5,
      "days_remaining": 2,
      "overdue_days": null
    }
  ]
}
```

> `days_remaining`：距逾期剩餘天數（7 - days_waiting），逾期後為 null

---

#### 5.8 取得包裹詳情（住戶）
```
GET /resident/parcels/<parcel_id>
```
**權限：** `@jwt_required()` + 只能讀取自己 `resident_id` 的包裹

**Response 200：**
```json
{
  "id": 1,
  "parcel_code": "PCL-202608001",
  "logistics_company": "黑貓宅急便",
  "size": "medium",
  "quantity": 3,
  "storage_location": "大廳置物櫃 B3",
  "notes": null,
  "arrived_at": "2026-08-03T10:21:00+00:00",
  "status": "pending",
  "days_waiting": 5,
  "days_remaining": 2,
  "overdue_days": null,
  "abnormal_reason": null,
  "picked_up_at": null,
  "created_at": "2026-08-03T10:21:00+00:00"
}
```

---

## 六、前端顯示邏輯（供 API Agent 參考）

### 管理員列表 Badge
| 狀態 | Badge 文字 | 顏色 |
|------|-----------|------|
| pending | 待領取 | 藍色 |
| overdue | 已逾期 X天 | 紅色 |
| picked_up | 已領取 | 綠色 |
| returned | 已退回 | 灰色 |
| abnormal | 異常 | 橘色 |

### 列表頁籤（管理員與住戶相同）
```
[ 全部 ] [ 待領取 ] [ 已逾期 ] [ 已結案 ]
```
- `status=closed` 參數 → 撈 `picked_up` + `returned` + `abnormal`

### 逾期包裹詳情頁狀態選項（管理員）
```
更改包裹狀態
● 已逾期          ← 預設選中（維持現狀）
○ 已退回物流      → 點「更新狀態」→ returned → 結案
○ 異常            → 點「更新狀態」→ abnormal → 結案（需填說明）
○ 住戶領取        → 按鈕改為「領取」→ 進入簽名流程 → picked_up → 結案
```

### 住戶詳情頁 Banner 條件
| 條件 | Banner 樣式 |
|------|------------|
| pending，days_remaining ≤ 3 | 黃色：請盡快領取，剩 X 天 |
| overdue | 紅色：包裹已逾期，請盡快聯繫管理室 |
| returned | 灰色：此包裹已退回物流，請自行聯繫物流商 |
| abnormal | 橘色：包裹狀態異常，請聯繫管理室 |

---

## 七、Blueprint 註冊（供 API Agent 參考）

```python
# app/__init__.py 新增：
from .routes.admin_parcel import admin_parcel_bp
from .routes.resident_parcel import resident_parcel_bp

app.register_blueprint(admin_parcel_bp,    url_prefix='/admin/parcels')
app.register_blueprint(resident_parcel_bp, url_prefix='/resident/parcels')
```

---

## 八、注意事項

1. **簽名圖片大小**：`signature_data` 以 base64 字串存 DB，建議前端壓縮至 200KB 以內再送出。
2. **逾期自動轉換**：不需背景排程，API 列表與詳情查詢時，對 `pending` 包裹比對 `arrived_at + 7天`，若逾期則即時 UPDATE 狀態為 `overdue` 再回傳。
3. **資料隔離**：所有查詢必須加 `organization_id` 過濾，住戶只能讀取自己 `resident_id` 的包裹。

---

## 九、開發順序

```
1. Model Agent   → app/models/parcel.py + migration
2. API Agent A   → app/routes/admin_parcel.py
3. API Agent B   → app/routes/resident_parcel.py（可與 API Agent A 並行）
4. Reviewer Agent → 審查權限隔離、input validation、log 完整性
```
