# 社區管理系統 — Backend CLAUDE.md

> 每個新視窗的 Agent 請先完整閱讀此檔案，再開始任何開發工作。

---

## 專案概覽

**類型：** 社區管理平台後端 API  
**框架：** Flask 3.0.3 + PostgreSQL + Docker  
**認證：** JWT（Access Token + Refresh Token）  
**文件：** Flasgger（Swagger UI）  
**部署：** Gunicorn + Nginx + Docker Compose  

---

## 目錄結構

```
backend/
├── app/
│   ├── __init__.py          # App factory, blueprint 註冊
│   ├── config.py            # 環境設定
│   ├── extensions.py        # db, jwt, bcrypt, cors 初始化
│   ├── models/              # SQLAlchemy ORM Models
│   ├── routes/              # Blueprint 路由
│   └── utils/
│       ├── decorators.py    # admin_required decorator
│       └── logger.py        # app_logger
├── migrations/              # Flask-Migrate 遷移檔
├── nginx/                   # Nginx 設定
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── run.py
```

---

## 已完成功能

### ✅ 認證系統（Auth）
- **檔案：** `app/routes/auth.py`
- POST `/admin/register` — 管理員註冊（需 org_code）
- POST `/login` — 管理員與住戶共用登入（by org_code + identifier）
- POST `/refresh` — Refresh Token 換 Access Token
- GET `/me` — 取得當前登入使用者資料
- PUT `/change-password` — 修改密碼（Admin 最少 8 碼，Resident 最少 6 碼）
- JWT claims 包含：`role`, `user_type`（admin/resident）, `org_id`

### ✅ 組織管理（Organization）
- **檔案：** `app/models/organization.py`, `app/routes/org.py`
- 每個 Organization 有唯一 `org_code`（大寫）
- 所有資料皆以 `organization_id` 隔離，不同建案資料互不可見

### ✅ 管理員管理（Admin）
- **檔案：** `app/models/admin.py`, `app/routes/admin.py`
- 員工編號格式：`ID-0000`
- 權限：透過 `admin_required` decorator 驗證

### ✅ 住戶管理（Resident）
- **檔案：** `app/models/resident.py`
- 角色：`resident`（住戶）/ `family`（家屬）
- 識別：`unit_code`（戶號）或手機號碼登入
- 同一建案內 unit_code、phone、email 皆唯一

### ✅ 公設管理（Facility）
- **檔案：** `app/models/facility.py`, `app/models/facility_slot.py`
- **管理員路由：** `app/routes/admin_facility.py`
- 公設可自訂時間區段（FacilitySlot），每個區段有 `sort_order`
- 欄位：name, icon, max_capacity, rules, sort_order, current_occupancy

### ✅ 預約系統（Booking）
- **檔案：** `app/models/booking.py`, `app/models/booking_checkin_log.py`
- **住戶路由：** `app/routes/resident_booking.py`
- **管理員路由：** `app/routes/admin_booking.py`
- 狀態流程：`confirmed` → `checked_in` → `departed` / `cancelled`
- 以 `slot_id` 關聯時間區段，以 `booking_date` 記錄日期
- 欄位：num_people, notes, cancelled_by_admin, checked_in_at, departed_at

### ✅ QR Code 系統（QR Check-in/Departure）
- **檔案：** `app/models/qr_action_token.py`, `app/models/qr_verification.py`
- **住戶路由：** `app/routes/resident_qr.py`
- **管理員路由：** `app/routes/admin_qr.py`
- Token TTL：45 秒；驗證後確認 TTL：180 秒
- Token 以 SHA-256 hash 儲存，不存明文
- Purpose prefix：`fci_`（facility_checkin）、`fdp_`（facility_departure）

### ✅ 報修系統（Repair Ticket）
- **檔案：** `app/models/repair_ticket.py`, `app/models/repair_category.py`
- **住戶路由：** `app/routes/resident_repair.py`
- **管理員路由：** `app/routes/admin_repair.py`
- 狀態：`pending` → `in_progress` → `completed`
- 工單編號格式：`REQ-YYYYMM{id:04d}`
- 管理員可回覆、設定維修預約日期與時段
- 支援維修類別（RepairCategory）分類查詢

### ✅ 日誌系統（Logging）
- **檔案：** `app/utils/logger.py`
- 所有認證事件（登入、註冊、改密）皆記錄 IP、user_id、org_id
- 不記錄任何密碼或敏感個資

---

## 待開發功能

### 🔲 包裹管理（Parcel）
- **Spec：** 開發前由 Planner Agent 讀 UIUX 圖後產出 `docs/parcel-spec.md`
- 功能範圍：管理員登記包裹到達、住戶查詢包裹、住戶領取後標記完成
- 預計新增：`app/models/parcel.py`、`app/routes/admin_parcel.py`、`app/routes/resident_parcel.py`

### 🔲 公告系統（Announcement）
- 管理員發布公告、住戶查閱
- 支援置頂、已讀狀態追蹤

### 🔲 訪客門禁（Visitor Access）
- 住戶邀請訪客、產生臨時通行 QR
- 管理員查閱訪客紀錄

### 🔲 費用管理（Billing）
- 管理費、停車費帳單
- 繳費紀錄查詢

---

## 開發規範

### 1. 資料隔離原則
- **所有查詢必須加上 `organization_id` 過濾。**
- 住戶只能存取自己 `resident_id` 的資料。
- 跨 org 存取視為嚴重安全漏洞。

### 2. 新增 Route 的標準結構

```python
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models.xxx import Xxx
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

xxx_bp = Blueprint('xxx', __name__)

@xxx_bp.route('/xxx', methods=['GET'])
@admin_required          # 或 @jwt_required() + 手動驗 user_type
def list_xxx():
    """
    功能說明
    ---
    tags:
      - Admin - Xxx
    ...
    """
    items = Xxx.query.filter_by(organization_id=g.org_id).all()
    return jsonify({'items': [i.to_dict() for i in items]}), 200
```

### 3. Blueprint 註冊
新增 route 後必須在 `app/__init__.py` 中 import 並 `register_blueprint`，加上 `url_prefix`。

### 4. Model 標準欄位
每個 Model 必須包含：
- `id`（Integer primary key）
- `organization_id`（FK → organizations.id）
- `created_at`（DateTime，使用 `lambda: datetime.now(timezone.utc)`）
- `updated_at`（DateTime，同上 + `onupdate`）
- `to_dict()` 方法，返回 JSON-serializable dict

### 5. Enum 狀態
使用 Python `enum.Enum`，欄位宣告用 `db.Enum(MyEnum)`，`to_dict()` 回傳 `.value`（字串）。

### 6. 錯誤回傳格式
```python
return jsonify({'error': '錯誤說明'}), 4xx
return jsonify({'message': '成功說明', 'data': ...}), 2xx
```

### 7. 時間規範
- 所有 DateTime 欄位使用 UTC：`lambda: datetime.now(timezone.utc)`
- `to_dict()` 中用 `.isoformat()` 序列化
- **禁止使用 `datetime.utcnow()`（已棄用）**

### 8. Migration
新增或修改 Model 後執行：
```bash
flask db migrate -m "描述"
flask db upgrade
```

### 9. 日誌規範
```python
app_logger.info(f"[MODULE] Action | key1=val1 | key2=val2")
app_logger.warning(f"[MODULE] Warning | reason=xxx")
```
禁止在 log 中記錄密碼、token 明文、或完整個人資料（僅記錄 id）。

### 10. 安全
- 所有管理員 API 必須套用 `@admin_required`
- 住戶 API 用 `@jwt_required()` 後從 JWT claims 取 `org_id`，再過濾資料
- Input validation：必填欄位缺失回 400，型別錯誤回 400

---

## 技術堆疊速查

| 項目 | 版本 |
|------|------|
| Flask | 3.0.3 |
| Flask-SQLAlchemy | 3.1.1 |
| Flask-Migrate | 4.0.7 |
| Flask-JWT-Extended | 4.6.0 |
| Flask-Bcrypt | 1.0.1 |
| Flasgger（Swagger） | 0.9.7.1 |
| 資料庫 | PostgreSQL（psycopg2-binary） |
| 容器 | Docker + Docker Compose |
| 反向代理 | Nginx |
| WSGI | Gunicorn |

---

## 多 Agent 開發指引

| Agent 角色 | 負責範圍 |
|-----------|---------|
| **Planner Agent** | 讀 UIUX 圖 → 產出 `docs/{feature}-spec.md` |
| **Model Agent** | `app/models/` — 參考現有 model 風格新增 |
| **API Agent** | `app/routes/` — 參考 `resident_booking.py` 或 `admin_repair.py` |
| **Reviewer Agent** | 審查權限隔離、Input validation、日誌是否完整 |

**跨 Agent 共享方式：**
1. 功能 Spec 寫入 `docs/{feature}-spec.md`
2. 所有 Agent 開始前先讀此 `CLAUDE.md` + 對應 spec 檔案
3. Model 完成後，API Agent 才開始（有依賴關係時循序進行）
