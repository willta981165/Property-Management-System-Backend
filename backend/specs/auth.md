# Auth Spec（認證）

## Requirement: 管理員登入
`POST /api/auth/admin/login`
- 成功 → 200，回傳 access_token + refresh_token
- 帳號或密碼錯誤 → 401

## Requirement: 住戶登入
`POST /api/auth/resident/login`
- 成功 → 200，回傳 access_token + refresh_token
- 帳號或密碼錯誤 → 401

## Requirement: Refresh Token
`POST /api/auth/refresh`（需 refresh JWT）
- 成功 → 200，回傳新 access_token

---

## Invariant: JWT Claims
- 管理員 token：`user_type=admin`、`org_id`、`admin_id`
- 住戶 token：`user_type=resident`、`org_id`、`resident_id`（sub）

## Invariant: 密碼儲存
- 使用 Flask-Bcrypt hash，資料庫中永不儲存明文
- 重設密碼由管理員透過 `PATCH /api/admin/residents/:id` 操作
