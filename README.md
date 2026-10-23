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

Backend có nền tảng nhỏ cho bước Upload: `POST /api/upload` nhận `multipart/form-data` chứa tệp LAS/LAZ, kiểm tra header LAS khi stream, lưu bằng dataset ID do server sinh và trả `pointCount`, `bounds`, `crs` đọc từ header (`crs` là `null` nếu file không khai báo mã EPSG). Frontend là Vue 3 shell có route upload và viewer rỗng. Conversion job và viewer sẽ được thêm sau khi spike kỹ thuật được duyệt.

## Chạy bằng Docker Compose

Cần Docker Engine với Docker Compose plugin. Từ thư mục gốc repository:

```bash
docker compose up --build
```

Mở frontend tại `http://localhost:5173`; health endpoint backend là `http://localhost:8000/health`. Frontend chuyển tiếp `/api/` tới backend, nên không cần đặt URL backend trong trình duyệt. Upload được lưu trong named volume `point-cloud-data`; dừng dịch vụ bằng `docker compose down`. Các cổng và giới hạn upload có thể đổi qua biến môi trường `FRONTEND_PORT`, `BACKEND_PORT` và `APP_MAX_UPLOAD_BYTES`; không cần tạo hoặc commit `.env`.

Compose hiện dựng frontend và backend của upload foundation. PDAL/PotreeConverter chưa được cài vào image: cách đóng gói và phiên bản cần được xác minh trong các spike xử lý tương ứng trước khi thêm vào runtime image.

## Chạy backend foundation

Yêu cầu Python 3.11 trở lên. Từ thư mục gốc repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e './backend[dev]'
make test
make dev
```

Thử upload một tệp mẫu:

```bash
curl --request POST http://127.0.0.1:8000/api/upload \
  --form 'file=@sample.las'
```

Phản hồi `201 Created` chứa point-cloud resource (`id`, `filename`, `status: "uploaded"`, `metadata`). Server kiểm tra phần mở rộng `.las`/`.laz` và chữ ký `LASF` ở đầu tệp.

Mọi lỗi dùng chung một schema:

```json
{"error": {"code": "INVALID_POINT_CLOUD", "message": "...", "requestId": "req_...", "details": {}}}
```

| Status | `error.code` | Khi nào |
|---|---|---|
| 413 | `FILE_TOO_LARGE` | Vượt `APP_MAX_UPLOAD_BYTES` |
| 415 | `UNSUPPORTED_FILE_TYPE` | Không phải `.las`/`.laz` |
| 422 | `INVALID_POINT_CLOUD` | Sai chữ ký LAS, tệp rỗng hoặc quá ngắn |
| 422 | `VALIDATION_ERROR` | Thiếu field `file` hoặc request sai định dạng |
| 500 | `INTERNAL_ERROR` | Lỗi không dự đoán; không lộ chi tiết nội bộ |

Có thể xem tài liệu tương tác tại `http://127.0.0.1:8000/docs`.

## Chạy frontend

Yêu cầu Node.js `^22.18.0` hoặc `>=24.12.0`. Từ thư mục `frontend/`:

```bash
npm install
npm run dev        # http://localhost:5173, route /upload và /viewer/:id
npm run lint
npm run typecheck
npm test
npm run build
```

Đặt `VITE_API_BASE_URL` (xem `.env.example`) để trỏ tới backend; mặc định `http://127.0.0.1:8000`.

## API contract và mock

`openapi/openapi.yaml` là nguồn sự thật cho API (upload, metadata, convert, job và schema lỗi dùng chung). Mock server và client TypeScript đều được sinh từ file này. Từ thư mục `frontend/`:

```bash
npm run mock          # mock server http://127.0.0.1:4010, trả về các example trong spec
npm run lint:openapi  # kiểm tra spec hợp lệ
npm run api:generate  # sinh lại client vào src/api/generated (không sửa tay)
```

Muốn xem response lỗi từ mock, gửi header `Prefer: code=404` (hoặc mã khác có trong spec). Đổi API thì sửa spec trước, chạy `api:generate` và commit cả file sinh ra; test backend sẽ báo lỗi nếu route upload lệch khỏi spec.

## Làm việc với Git

1. Tạo issue có acceptance criteria và estimate.
2. Tạo branch ngắn hạn: `feat/<issue#>-<short-desc>`.
3. Cài hook local theo [hướng dẫn hook](scripts/README.md), rồi tạo commit Conventional Commit nhỏ.
4. Mở Draft PR sớm, tự review diff, chờ CI và một approval.

Tài liệu lập kế hoạch nội bộ được lưu ngoài repository, không được commit vào đây.

## Cấu trúc

```text
frontend/     Vue 3 + TypeScript + Vite shell
backend/      FastAPI upload foundation
openapi/      OpenAPI contract (nguồn sự thật cho mock và client)
data/sample/  Chỉ dữ liệu mẫu nhỏ, đã được phép phân phối
scripts/      Validation, bootstrap và automation an toàn
.github/      Template và CI policy
```

Chi tiết quy trình GitHub, kiến trúc và kế hoạch sprint thuộc bộ tài liệu nội bộ của nhóm.
