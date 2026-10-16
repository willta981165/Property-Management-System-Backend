# Announcement Spec（社區公告）

## Requirement: 管理員建立公告
`POST /api/admin/announcements`（需 admin JWT）
- 支援附件上傳（PDF/Word/Excel/圖片，上限 10MB）
- 成功 → 201

## Requirement: 管理員取得公告列表
`GET /api/admin/announcements`（需 admin JWT）

## Requirement: 管理員刪除公告
`DELETE /api/admin/announcements/:id`（需 admin JWT）

## Requirement: 住戶取得公告列表
`GET /api/resident/announcements`（需 resident JWT）
- 只回傳未過期公告

## Requirement: 住戶標記已讀
`POST /api/resident/announcements/:id/read`（需 resident JWT）
- 成功 → 200，寫入 announcement_reads 表

## Requirement: 附件下載
`GET /api/resident/announcements/:id/attachment`（需 resident JWT）
- 成功 → 回傳檔案串流

## Requirement: 公告類別 CRUD
`GET/POST /api/admin/announcement-categories`
`DELETE /api/admin/announcement-categories/:id`

---

## Invariant: 未讀計算
- announcement_reads 無該住戶記錄 且 公告未過期 → 計入 announcement_unread
