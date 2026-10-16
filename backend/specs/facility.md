# Facility Spec（公設管理）

## Requirement: 取得公設列表
`GET /api/admin/facilities`（需 admin JWT）
- 成功 → 200，依 sort_order 排序

## Requirement: 建立公設
`POST /api/admin/facilities`（需 admin JWT）
- 成功 → 201

## Requirement: 更新公設
`PATCH /api/admin/facilities/:id`（需 admin JWT）
- 成功 → 200

## Requirement: 取得時段列表
`GET /api/admin/facilities/:id/slots`（需 admin JWT）
- 成功 → 200，回傳該公設所有時段

## Requirement: 建立時段
`POST /api/admin/facilities/:id/slots`（需 admin JWT）
- 成功 → 201

---

## Invariant: 容量管理
- max_capacity：單時段最大人數上限
- current_occupancy：即時在場人數（報到 +、離場 -）
