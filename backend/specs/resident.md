# Resident Spec（住戶管理）

## Requirement: 建立住戶
`POST /api/admin/residents`（需 admin JWT）
- 成功 → 201，回傳住戶資料
- unit_code 重複 → 409

## Requirement: 取得住戶列表
`GET /api/admin/residents`（需 admin JWT）
- 成功 → 200，支援 q（模糊搜尋 unit_code / name）

## Requirement: 更新住戶（含重設密碼）
`PATCH /api/admin/residents/:id`（需 admin JWT）
- 成功 → 200
- 可傳入 password 欄位重設密碼

## Requirement: 刪除住戶
`DELETE /api/admin/residents/:id`（需 admin JWT）
- 成功 → 200

---

## Invariant: 住戶帳號
- username 為登入帳號，全系統唯一
- 密碼以 bcrypt hash 儲存
- role 欄位：owner / tenant / other
