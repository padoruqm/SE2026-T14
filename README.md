# SE2026-T14 — Point Cloud Explorer

MVP đi theo luồng Upload → 3D Viewer → Measure → Crop → Export; Filter cơ bản là P1.

## Công nghệ 

- Frontend: Vue 3 + TypeScript + Vite.
- Viewer: Potree/Three.js.
- Backend: Python + FastAPI.
- Processing: PDAL + PotreeConverter.
- Runtime: Docker Compose; storage filesystem ở MVP.

Việc tích hợp viewer Potree/Vite, PDAL và hỗ trợ LAZ vẫn cần spike; không xem đó là cam kết về khả năng hoặc phiên bản đã kiểm chứng.

## Trạng thái repository

Backend có nền tảng upload và adapter xử lý LAS qua PotreeConverter. API `POST /api/pointcloud/{id}/convert` chạy adapter này qua job nền; frontend vẫn là Vue 3 shell có route upload và viewer rỗng.

## Chạy bằng Docker Compose

Cần Docker Engine với Docker Compose plugin. Từ thư mục gốc repository:

```bash
docker compose up --build
```

Mở frontend tại `http://localhost:5173`; health endpoint backend là `http://localhost:8000/health`. Frontend chuyển tiếp `/api/` tới backend, nên không cần đặt URL backend trong trình duyệt. Upload được lưu trong named volume `point-cloud-data`; dừng dịch vụ bằng `docker compose down`. Các cổng và giới hạn upload có thể đổi qua biến môi trường `FRONTEND_PORT`, `BACKEND_PORT` và `APP_MAX_UPLOAD_BYTES`; không cần tạo hoặc commit `.env`.

Backend image có binary Linux chính thức PotreeConverter 2.1.1, được pin bằng SHA-256 và gọi qua processing adapter. Test chuyển đổi LAS dùng fixture nhỏ tự sinh; hỗ trợ LAZ vẫn chờ spike #14.

Compose build backend image có PotreeConverter 2.1.1, và API convert gọi adapter qua job nền. PDAL chưa được cài. Spike #14 đã xác nhận riêng converter trên Linux đọc được LAZ: container dùng Dockerfile converter đã chuyển đổi fixture `simple.laz` (1.065 điểm, SHA-256 `87ac5d2e8edb6cd3c63f1dd1b982d76b1b3c23ca634658ac6c658e1a70e73e71`) và tạo `metadata.json`. Đây là xác minh khả năng đọc LAZ của converter, không phải xác nhận luồng upload → conversion với LAZ; adapter hiện vẫn chỉ nhận LAS. PotreeConverter cũng không nén output thành LAZ.

PDAL cần được xử lý riêng.

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

Sau khi upload, gọi `POST /api/pointcloud/{id}/convert` để tạo job convert (`202`, trả `Job` ở trạng thái `queued`) rồi poll `GET /api/job/{id}` tới khi `state` là `succeeded` hoặc `failed`. Job chạy nền trong tiến trình backend và lưu trong bộ nhớ nên mất khi restart; job cũng không bị xoá nên bộ nhớ tăng dần (chấp nhận được ở MVP). Kết quả ghi vào `<APP_STORAGE_ROOT>/converted/<id>/`. Gọi lại convert khi đã có kết quả hoặc job đang chạy trả `409 CONFLICT`, trừ khi gửi `{"force": true}`.

Converter là PotreeConverter chạy qua `PotreeConverterProcessor`; mặc định dùng `POTREE_CONVERTER_PATH` (đã đặt trong image), có thể ghi đè bằng `APP_POTREE_CONVERTER_PATH`; dùng `APP_JOB_TIMEOUT_SECONDS` (mặc định 600) và `APP_JOB_WORKERS` (mặc định 1) để chỉnh timeout và số job chạy song song. Lỗi của chính converter (crash, timeout, thiếu binary) kết thúc job `failed` với `INTERNAL_ERROR`; file đầu vào bị từ chối kết thúc với `INVALID_POINT_CLOUD`.

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

## Spike #6: Potree trong Vue/Vite

**Kết luận: tiếp tục với Potree 1.8.2.** Adapter mount/dispose chạy được trong Vite dev và production build. Viewer render được cả output PotreeConverter 2.x (`metadata.json`) lẫn định dạng 1.x (`cloud.js`).

- **Ref Potree:** release chính thức [1.8.2](https://github.com/potree/potree/releases/tag/1.8.2), file `Potree_1.8.2.zip`, SHA-256 `c140a8bce0ce129de762fbc0fd3ba7c21120ffd36d423dd2755abb39f32aebe5`.
- **Cách build:** Potree không có package npm chính thức. `potree.js` là classic script: nó gán `window.Potree` và tìm `workers/` qua `document.currentScript`, nên không bundle bằng Vite được. Chạy `./scripts/fetch-potree.sh` từ thư mục gốc. Script tải release đã pin checksum và copy phần cần thiết (khoảng 22 MB) vào `frontend/public/potree/`. Thư mục này nằm trong `.gitignore` và ESLint bỏ qua nó. Vite phục vụ thư mục này ở `/potree/` khi dev và copy nguyên vào `dist/` khi build. `potree.js` cần các global jQuery, BinaryHeap, TWEEN và proj4. Bản release có sẵn các thư viện này, và script copy chúng vào `public/potree/libs/`.
- **Adapter:** `frontend/src/features/viewer/potreeViewer.ts`.
  - `loadPotree()` chèn các script theo đúng thứ tự, mỗi script chỉ một lần.
  - `mountPotreeViewer(element, url)` tạo `Potree.Viewer` trong `element`, nạp point cloud rồi `fitToScreen()`.
  - `dispose()` dừng render loop (`setAnimationLoop(null)`), gọi `dispose()` và `forceContextLoss()` trên renderer, rồi xoá DOM mà Potree đã thêm vào. Potree 1.8.2 không tự có bước dispose này. Nếu point cloud nạp xong sau khi đã dispose thì adapter bỏ qua.
  - Component Vue gọi mount trong `onMounted` và gọi dispose trong `onBeforeUnmount`. Việc gắn adapter vào `ViewerPage` thuộc #15 (S2-Q1).
- **Bằng chứng:**
  - Ba unit test cho adapter (`__tests__/potreeViewer.spec.ts`).
  - Chạy thử trên Chromium 131 headless (Playwright, WebGL qua SwiftShader), nạp hai nguồn:
    - Mẫu `lion_takanawa` (định dạng 1.x) có trong release.
    - Output PotreeConverter 2.1.1 Linux của một file LAS 135 KB.
  - Cả hai đều render ra point cloud sau khoảng 4 giây.
  - Sau 6 lần mount/dispose: không còn canvas nào, 6/6 WebGL context của viewer đã bị huỷ, không còn `requestAnimationFrame` nào chạy, script Potree chỉ được nạp một lần và console không có lỗi.
- **Hạn chế cần xử lý ở các task sau:**
  - `Potree.loadPointCloud` không reject khi URL sai (chỉ `console.error`), nên phía gọi cần timeout hoặc kiểm tra URL trước.
  - Potree dựa vào global (`window.Potree`, `$`).
  - `frontend/Dockerfile` chưa chạy `fetch-potree.sh`. Cần thêm bước này khi viewer được dùng trong Compose.
- **Khi nào đổi hướng:** nếu sau này phải bỏ global hoặc Potree 1.8.2 gặp lỗi không sửa được thì cân nhắc [`potree-core`](https://www.npmjs.com/package/potree-core) (ESM, bundle được bằng Vite). Đổi lại, nhóm phải tự làm công cụ đo và cắt mà Potree 1.8.2 đã có sẵn cho S2/S3.

## Điều khiển viewer (S2-Q1)

Trang `/viewer/:id` mount viewer Potree qua `ViewerCanvas.vue` và có thanh điều khiển `ViewerControls.vue`:

- Camera: kéo chuột trái để xoay, chuột phải để pan, lăn chuột để zoom (orbit controls mặc định của Potree); nút **Reset view** đưa camera về toàn bộ point cloud.
- **Point size** và **Color** (RGB, Elevation, Intensity) chỉ đổi material của point cloud đã nạp, không convert hay tải lại dữ liệu.
- Viewer nạp `/api/pointcloud/:id/viewer/metadata.json`; cần chạy `./scripts/fetch-potree.sh` một lần để có `frontend/public/potree/`.

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

## Cấu trúc

```text
frontend/     Vue 3 + TypeScript + Vite shell
backend/      FastAPI upload foundation
openapi/      OpenAPI contract (nguồn sự thật cho mock và client)
data/sample/  Chỉ dữ liệu mẫu nhỏ, đã được phép phân phối
scripts/      Validation, bootstrap và automation an toàn
.github/      Template và CI policy
```
