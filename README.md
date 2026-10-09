# SE2026-T14 — Point Cloud Explorer

Web app xử lý point cloud LAS/LAZ cho đồ án Công nghệ phần mềm. MVP đi theo luồng Upload → 3D Viewer → Measure → Crop → Export; Filter cơ bản là P1.

## Công nghệ định hướng

- Frontend: Vue 3 + TypeScript + Vite.
- Viewer: Potree/Three.js.
- Backend: Python + FastAPI.
- Processing: PDAL + PotreeConverter.
- Runtime: Docker Compose; storage filesystem ở MVP.

Việc tích hợp Potree/Vite, PDAL, PotreeConverter và LAZ vẫn phải được spike, không xem đây là cam kết về phiên bản công cụ.

## Trạng thái repository

Repository hiện chỉ có cấu trúc và quy ước phát triển. Mã ứng dụng, Dockerfile, dependency lockfile và lệnh chạy sẽ được thêm sau khi spike kỹ thuật được duyệt. Vì vậy các target `make dev`, `make test`, `make lint` hiện cố ý dừng với hướng dẫn thay vì báo pass giả.

## Làm việc với Git

1. Tạo issue có acceptance criteria và estimate.
2. Tạo branch ngắn hạn: `feat/<issue#>-<short-desc>`.
3. Cài hook local theo [hướng dẫn hook](scripts/README.md), rồi tạo commit Conventional Commit nhỏ.
4. Mở Draft PR sớm, tự review diff, chờ CI và một approval.

Tài liệu lập kế hoạch nội bộ được lưu ngoài repository, không được commit vào đây.

## Cấu trúc

```text
frontend/     Vue application (chưa scaffold)
backend/      FastAPI application (chưa scaffold)
data/sample/  Chỉ dữ liệu mẫu nhỏ, đã được phép phân phối
scripts/      Validation, bootstrap và automation an toàn
.github/      Template và CI policy
```

Chi tiết quy trình GitHub, kiến trúc và kế hoạch sprint thuộc bộ tài liệu nội bộ của nhóm.
