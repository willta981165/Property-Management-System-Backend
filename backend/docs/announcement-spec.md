# 公告系統功能 Spec（布告欄）

> 產出日期：2026-09-14  
> 由 Planner Agent 根據 UIUX 設計圖與產品討論產出  
> Model Agent 與 API Agent 開發前必須完整閱讀此文件與 CLAUDE.md

---

## 一、功能概述

管理員可在後台發布、編輯、刪除社區公告，住戶可在 App 瀏覽公告列表並查看詳情。公告支援類別標籤、置頂、有效期限、附件（PDF / 文件等），住戶點擊公告後系統自動標記已讀。

---

## 二、使用者角色

| 角色 | 可執行操作 |
|------|-----------|
| 管理員 (Admin) | 建立公告、編輯公告、刪除公告、上傳附件、管理公告類別 |
| 住戶 (Resident) | 瀏覽公告列表（依類別篩選）、查看公告詳情、下載附件 |

---

## 三、資料庫設計

### 3.1 Model：`AnnouncementCategory`（公告類別）
**檔案：** `app/models/announcement.py`

> MVP 設計：由管理員手動建立類別，不使用 # 關鍵字自動產生。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer, PK | 主鍵 |
| `organization_id` | Integer, FK → organizations.id | 建案隔離，必填 |
| `name` | String(30) | 類別名稱（如：維修保養、停水電、一般事務） |
| `color` | String(20) | 顯示顏色標籤，接受值：`green`、`orange`、`red`、`blue`、`gray` |
| `created_at` | DateTime | 建立時間（UTC） |
| `updated_at` | DateTime | 更新時間（UTC） |

---

### 3.2 Model：`Announcement`（公告）
**檔案：** `app/models/announcement.py`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer, PK | 主鍵 |
| `organization_id` | Integer, FK → organizations.id | 建案隔離，必填 |
| `category_id` | Integer, FK → announcement_categories.id, nullable | 公告類別 |
| `title` | String(50) | 公告標題，必填 |
| `content` | Text | 公告內容，必填 |
| `is_pinned` | Boolean, default=False | 是否置頂 |
| `expires_at` | DateTime(timezone=True), nullable | 有效截止時間（Optional），到期後住戶不可見 |
| `created_by_admin_id` | Integer, FK → admins.id, nullable | 發布管理員 |
| `created_at` | DateTime | 建立時間（UTC） |
| `updated_at` | DateTime | 更新時間（UTC） |

**Relationship：**
- `category` → `AnnouncementCategory`
- `attachments` → `AnnouncementAttachment`（one-to-many）
- `reads` → `AnnouncementRead`（one-to-many）

---

### 3.3 Model：`AnnouncementAttachment`（附件）
**檔案：** `app/models/announcement.py`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer, PK | 主鍵 |
| `announcement_id` | Integer, FK → announcements.id | 所屬公告 |
| `organization_id` | Integer, FK → organizations.id | 建案隔離 |
| `original_filename` | String(255) | 使用者上傳時的原始檔名 |
| `stored_filename` | String(255) | 伺服器端儲存的檔名（UUID 命名，防衝突） |
| `file_path` | String(512) | 檔案在伺服器上的絕對路徑 |
| `mime_type` | String(100) | MIME 類型（如 `application/pdf`） |
| `file_size` | Integer | 檔案大小（bytes） |
| `created_at` | DateTime | 建立時間（UTC） |

**檔案儲存路徑：** `uploads/announcements/{announcement_id}/{stored_filename}`  
（使用 Docker Volume 掛載，Nginx 不直接 serve — 統一走 API 下載端點）

---

### 3.4 Model：`AnnouncementRead`（住戶已讀記錄）
**檔案：** `app/models/announcement_read.py`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | Integer, PK | 主鍵 |
| `announcement_id` | Integer, FK → announcements.id | 公告 |
| `resident_id` | Integer, FK → residents.id | 住戶 |
| `organization_id` | Integer, FK → organizations.id | 建案隔離 |
| `read_at` | DateTime | 已讀時間（UTC） |

**唯一約束：** `UniqueConstraint('announcement_id', 'resident_id')` — 每個住戶對每則公告只記錄一筆。

---

## 四、公告狀態邏輯

```
發布後（無期限）→ 一直有效，直到管理員手動刪除
發布後（有期限）→ expires_at 到期後，住戶不可見（管理員仍可見）
               → 管理員列表顯示 is_expired: true
```

**到期處理方式：Lazy filter**（API 查詢時判斷，不需背景排程）
- 住戶端查詢：`WHERE (expires_at IS NULL OR expires_at > NOW())`
- 管理員端：回傳所有公告，並在 `to_dict()` 加上 `is_expired` 欄位

**排序規則（住戶端 & 管理員端列表）：**
1. `is_pinned DESC`（置頂優先）
2. `created_at DESC`（最新優先）

---

## 五、API Endpoints

### 管理員端（prefix: `/admin/announcements`）

#### 5.1 取得公告列表
```
GET /admin/announcements
```
**權限：** `@admin_required`

**Query Params：**
| 參數 | 說明 |
|------|------|
| `category_id` | 篩選特定類別 |
| `status` | `active`（有效）/ `expired`（已到期）/ 留空=全部 |

**Response 200：**
```json
{
  "total": 8,
  "announcements": [
    {
      "id": 1,
      "title": "9/15 全社區水塔年度高壓清洗作業通知",
      "content_preview": "為維護社區用水衛生與用水安全，我們於 9/15...",
      "category": { "id": 1, "name": "維修保養", "color": "green" },
      "is_pinned": true,
      "is_expired": false,
      "expires_at": "2026-09-16T00:00:00+00:00",
      "attachment_count": 1,
      "created_at": "2026-09-10T09:00:00+00:00",
      "updated_at": "2026-09-10T09:00:00+00:00"
    }
  ]
}
```

> `content_preview`：content 前 80 字（API 層截取）  
> `attachment_count`：len(attachments)

---

#### 5.2 新增公告
```
POST /admin/announcements
Content-Type: application/json
```
**權限：** `@admin_required`

**Request Body：**
```json
{
  "title": "9/15 全社區水塔年度高壓清洗作業通知",
  "content": "為維護社區用水衛生...",
  "category_id": 1,
  "is_pinned": true,
  "expires_at": "2026-09-16"
}
```

**驗證規則：**
- `title`：必填，1~50 字元
- `content`：必填，非空字串
- `category_id`：選填，若提供必須屬於同一 `organization_id`
- `is_pinned`：選填，Boolean，預設 false
- `expires_at`：選填，格式 `YYYY-MM-DD`，不得早於今天

**Response 201：**
```json
{
  "message": "公告發布成功",
  "announcement": { "id": 1, "...to_dict()": "..." }
}
```

---

#### 5.3 取得公告詳情（管理員）
```
GET /admin/announcements/<announcement_id>
```
**權限：** `@admin_required`

**Response 200：**
```json
{
  "id": 1,
  "title": "9/15 全社區水塔年度高壓清洗作業通知",
  "content": "完整公告內容...",
  "category": { "id": 1, "name": "維修保養", "color": "green" },
  "is_pinned": true,
  "is_expired": false,
  "expires_at": "2026-09-16T00:00:00+00:00",
  "attachments": [
    {
      "id": 1,
      "original_filename": "停水通知.pdf",
      "mime_type": "application/pdf",
      "file_size": 204800
    }
  ],
  "read_count": 12,
  "created_by_admin_id": 3,
  "created_at": "2026-09-10T09:00:00+00:00",
  "updated_at": "2026-09-10T09:00:00+00:00"
}
```

---

#### 5.4 編輯公告
```
PUT /admin/announcements/<announcement_id>
Content-Type: application/json
```
**權限：** `@admin_required`

**Request Body：**（所有欄位皆為選填，只更新有提供的欄位）
```json
{
  "title": "更新後的標題",
  "content": "更新後的內容",
  "category_id": 2,
  "is_pinned": false,
  "expires_at": "2026-09-20"
}
```

**驗證規則：**
- 各欄位規則同新增（5.2）
- `expires_at` 傳 `null` 代表移除有效期限（清空為無限期）

**Response 200：**
```json
{
  "message": "公告更新成功",
  "announcement": { "...to_dict()": "..." }
}
```

---

#### 5.5 刪除公告
```
DELETE /admin/announcements/<announcement_id>
```
**權限：** `@admin_required`

**說明：** 刪除公告時，同時刪除對應的附件實體檔案（os.remove）與已讀記錄（CASCADE 或手動刪除）。

**Response 200：**
```json
{
  "message": "公告已刪除"
}
```

---

#### 5.6 上傳附件
```
POST /admin/announcements/<announcement_id>/attachments
Content-Type: multipart/form-data
```
**權限：** `@admin_required`

**Form Data：**
| 欄位 | 說明 |
|------|------|
| `file` | 上傳的檔案（單檔） |

**伺服器端驗證：**
- 最大檔案大小：10 MB（`MAX_CONTENT_LENGTH = 10 * 1024 * 1024`）
- 允許的 MIME 類型：
  - `application/pdf`
  - `application/msword`、`application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - `application/vnd.ms-excel`、`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - `image/jpeg`、`image/png`
  - `text/plain`
- 儲存為 `{uuid4()}.{副檔名}` 至 `uploads/announcements/{announcement_id}/`

> **前端行為（後端無需處理）：** 前端使用 `<input type="file">` 觸發手機原生文件選取器，後端只接收 multipart/form-data。

**Response 201：**
```json
{
  "message": "附件上傳成功",
  "attachment": {
    "id": 1,
    "original_filename": "停水通知.pdf",
    "mime_type": "application/pdf",
    "file_size": 204800
  }
}
```

---

#### 5.7 刪除附件
```
DELETE /admin/announcements/<announcement_id>/attachments/<attachment_id>
```
**權限：** `@admin_required`

**說明：** 從 DB 刪除記錄並從 filesystem 移除實體檔案（`os.remove(file_path)`，捕捉 FileNotFoundError）。

**Response 200：**
```json
{
  "message": "附件已移除"
}
```

---

#### 5.8 取得公告類別列表
```
GET /admin/announcement-categories
```
**權限：** `@admin_required`

**Response 200：**
```json
{
  "categories": [
    { "id": 1, "name": "維修保養", "color": "green" },
    { "id": 2, "name": "停水電",   "color": "orange" },
    { "id": 3, "name": "一般事務", "color": "gray" }
  ]
}
```

---

#### 5.9 新增公告類別
```
POST /admin/announcement-categories
```
**權限：** `@admin_required`

**Request Body：**
```json
{
  "name": "活動通知",
  "color": "blue"
}
```

**驗證規則：**
- `name`：必填，1~30 字元，同一 org 內不可重複
- `color`：必填，值只接受 `green`、`orange`、`red`、`blue`、`gray`

**Response 201：**
```json
{
  "message": "類別新增成功",
  "category": { "id": 4, "name": "活動通知", "color": "blue" }
}
```

---

#### 5.10 刪除公告類別
```
DELETE /admin/announcement-categories/<category_id>
```
**權限：** `@admin_required`

**驗證：** 若仍有公告使用此類別，回 400（需先移除或重新分類公告後才能刪除類別）。

**Response 200：**
```json
{
  "message": "類別已刪除"
}
```

---

### 住戶端（prefix: `/resident/announcements`）

#### 5.11 取得社區公告列表
```
GET /resident/announcements
```
**權限：** `@jwt_required()` + `user_type == resident`

**說明：** 自動過濾已到期公告（`expires_at IS NULL OR expires_at > NOW()`）。

**Query Params：**
| 參數 | 說明 |
|------|------|
| `category_id` | 篩選特定類別 |

**Response 200：**
```json
{
  "categories": [
    { "id": 1, "name": "維修保養", "color": "green" },
    { "id": 2, "name": "停水電",   "color": "orange" }
  ],
  "announcements": [
    {
      "id": 1,
      "title": "9/15 全社區水塔年度高壓清洗作業通知",
      "content_preview": "為維護社區用水衛生與用水安全...",
      "category": { "id": 1, "name": "維修保養", "color": "green" },
      "is_pinned": true,
      "has_attachment": true,
      "is_read": false,
      "created_at": "2026-09-10T09:00:00+00:00"
    }
  ]
}
```

> `is_read`：查詢 `AnnouncementRead` 是否存在對應 `resident_id` 記錄  
> `has_attachment`：`len(attachments) > 0`

---

#### 5.12 取得公告詳情（住戶）
```
GET /resident/announcements/<announcement_id>
```
**權限：** `@jwt_required()` + `user_type == resident`

**說明：**
- 住戶只能查看有效公告（到期公告回 404）
- 第一次查看時，自動建立 `AnnouncementRead` 記錄（先查後插，避免重複）

**Response 200：**
```json
{
  "id": 1,
  "title": "9/15 全社區水塔年度高壓清洗作業通知",
  "content": "完整公告內容...",
  "category": { "id": 1, "name": "維修保養", "color": "green" },
  "is_pinned": true,
  "attachments": [
    {
      "id": 1,
      "original_filename": "停水通知.pdf",
      "mime_type": "application/pdf",
      "file_size": 204800
    }
  ],
  "created_at": "2026-09-10T09:00:00+00:00",
  "updated_at": "2026-09-10T09:00:00+00:00"
}
```

---

#### 5.13 下載附件（住戶）
```
GET /resident/announcements/<announcement_id>/attachments/<attachment_id>/download
```
**權限：** `@jwt_required()` + `user_type == resident`

**說明：**
- 驗證 attachment 屬於該公告且屬於同一 `organization_id`
- 驗證公告未到期（到期公告回 404）
- 使用 `flask.send_file()` 回傳實體檔案
- Header：`Content-Disposition: attachment; filename="{original_filename}"`

---

## 六、Blueprint 註冊

```python
# app/__init__.py 新增：
from .routes.admin_announcement import admin_announcement_bp, admin_announcement_category_bp
from .routes.resident_announcement import resident_announcement_bp

app.register_blueprint(admin_announcement_bp,          url_prefix='/admin/announcements')
app.register_blueprint(admin_announcement_category_bp, url_prefix='/admin/announcement-categories')
app.register_blueprint(resident_announcement_bp,       url_prefix='/resident/announcements')
```

---

## 七、檔案儲存規範

```
backend/
└── uploads/
    └── announcements/
        └── {announcement_id}/
            └── {uuid4()}.{ext}    ← 伺服器儲存檔名
```

**Docker Compose 需新增 Volume 掛載：**
```yaml
volumes:
  - ./uploads:/app/uploads
```

**Flask config.py 新增設定：**
```python
import os
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads', 'announcements')
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'image/jpeg',
    'image/png',
    'text/plain',
}
```

---

## 八、`to_dict()` 格式說明

### AnnouncementCategory
```python
def to_dict(self):
    return {
        'id': self.id,
        'name': self.name,
        'color': self.color,
    }
```

### Announcement
```python
def to_dict(self, include_attachments=False, read_count=None):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    data = {
        'id': self.id,
        'title': self.title,
        'content': self.content,
        'category': self.category.to_dict() if self.category else None,
        'is_pinned': self.is_pinned,
        'is_expired': bool(self.expires_at and self.expires_at < now),
        'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        'created_by_admin_id': self.created_by_admin_id,
        'created_at': self.created_at.isoformat(),
        'updated_at': self.updated_at.isoformat(),
    }
    if include_attachments:
        data['attachments'] = [a.to_dict() for a in self.attachments]
        data['attachment_count'] = len(self.attachments)
    if read_count is not None:
        data['read_count'] = read_count
    return data
```

### AnnouncementAttachment
```python
def to_dict(self):
    return {
        'id': self.id,
        'original_filename': self.original_filename,
        'mime_type': self.mime_type,
        'file_size': self.file_size,
    }
```

---

## 九、注意事項

1. **資料隔離：** 所有查詢必須加 `organization_id` 過濾，住戶只能存取同一建案的公告。
2. **到期判斷：** API 層即時判斷，採 lazy filter，不需背景排程。
3. **附件安全：** 不以 Nginx 直接 serve uploads 目錄，統一走 API 下載端點確保身份驗證。
4. **刪除公告時：** 需一併從 filesystem 刪除附件實體檔案，避免孤兒檔案（`os.remove`，捕捉 `FileNotFoundError`）。
5. **前端附件選取：** 前端以 `<input type="file">` 觸發手機原生文件選取器，後端只需接收 multipart/form-data，無需處理此行為。
6. **類別刪除防護：** 若有公告仍在使用該類別，拒絕刪除並回 400。
7. **已讀記錄：** 住戶查看詳情時，先查詢是否已有記錄，若無則 insert，避免 unique constraint 衝突。

---

## 十、開發順序（多 Agent 並行）

```
Step 1  Model Agent
        → app/models/announcement.py
          （含 AnnouncementCategory、Announcement、AnnouncementAttachment）
        → app/models/announcement_read.py
          （AnnouncementRead）
        → flask db migrate -m "add announcement tables"
        → flask db upgrade

Step 2A  API Agent A（管理員端，依賴 Step 1）
        → app/routes/admin_announcement.py
        → 負責：公告 CRUD（5.1~5.5）+ 附件上傳/刪除（5.6~5.7）+ 類別管理（5.8~5.10）

Step 2B  API Agent B（住戶端，依賴 Step 1，可與 Step 2A 並行）
        → app/routes/resident_announcement.py
        → 負責：公告列表（5.11）+ 詳情含自動已讀（5.12）+ 附件下載（5.13）

Step 3  Reviewer Agent
        → 審查 organization_id 隔離、input validation、日誌、附件路徑安全性
```
