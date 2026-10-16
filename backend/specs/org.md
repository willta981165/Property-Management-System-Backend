# Org Spec（社區組織）

## Requirement: 建立組織
`POST /api/org`
- 成功 → 201，回傳 org_id + 初始 admin 帳號

## Requirement: 取得組織資訊
`GET /api/org`（需 admin JWT）
- 成功 → 200，回傳組織名稱等基本資料

---

## Invariant: 隔離原則
- 所有資料皆以 org_id 做 tenant 隔離
- 跨 org_id 存取任何資源一律回傳 403 或 404
