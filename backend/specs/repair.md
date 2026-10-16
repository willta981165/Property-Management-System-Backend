# Repair Spec（報修申請）

## Requirement: 住戶建立報修單
`POST /api/resident/repairs`（需 resident JWT）
- 成功 → 201

## Requirement: 住戶取得報修單列表
`GET /api/resident/repairs`（需 resident JWT）
- 成功 → 200

## Requirement: 管理員取得報修單列表
`GET /api/admin/repairs`（需 admin JWT）
- 支援 status、category_id 篩選

## Requirement: 管理員更新報修單
`PATCH /api/admin/repairs/:id`（需 admin JWT）
- 可更新 status、admin_reply
- 狀態變為 in_progress 或 completed 時觸發 repair_updated 通知

## Requirement: 維修類別 CRUD
`GET/POST /api/admin/repair-categories`
`DELETE /api/admin/repair-categories/:id`（需 admin JWT）

---

## Invariant: 狀態流
pending → in_progress → completed

## Invariant: 通知觸發
僅 pending→in_progress 或 pending/in_progress→completed 觸發通知，狀態未變則不觸發
