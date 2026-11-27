# Test Docker Compose trên bản clone sạch (S3-Q4, #30)

Mục tiêu: clone repo mới, `docker compose up`, chạy được smoke flow. Smoke flow nằm trong
[smoke-test.sh](smoke-test.sh) và đi qua nginx của frontend như trình
duyệt: health, upload, convert, file viewer, asset Potree, rồi PDAL trong container backend.

```bash
git clone <repo> && cd <repo> && git checkout dev
docker compose up --build -d
./scripts/smoke-test.sh          # thoát với mã khác 0 nếu có bước FAIL
docker compose down -v
```

## Bản ghi: 2026-11-23

- **Máy:** MacBook Apple Silicon (aarch64), macOS 14 (Darwin 23.6), Docker Desktop (engine 29.6.2), 7,75 GiB RAM cấp cho Docker.
- **Mã nguồn:** `git clone` mới từ `dev` tại `8538e8a`, không có `.env`, không sửa gì.
- **Dữ liệu:** `data/sample/demo.las` (5 điểm, EPSG:32648) sinh bởi `scripts/generate-sample-las.py`.

### Lần 1: `dev` như hiện có (`8538e8a`)

Stack lên bình thường (backend healthy, frontend chạy), nhưng smoke flow **không đạt**: 9 bước pass, 4 bước fail.

| Bước | Kết quả |
|---|---|
| health, frontend, upload, metadata, start conversion, 404, PDAL trong container, crop bằng PDAL (LAS và LAZ) | PASS |
| `/potree/potree.js` | Trả `index.html`: image frontend không có Potree (nginx trả 200 cho mọi đường dẫn lạ). Viewer không tải được trong Compose |
| Job convert | `failed`: `rosetta error: failed to open elf at /lib64/ld-linux-x86-64.so.2`. PotreeConverter là binary x86-64, image backend lại được build ra arm64 |
| Point cloud `ready`, `metadata.json`, `octree.bin` | FAIL, hệ quả của lỗi convert |

### Sửa trong PR này

1. `frontend/Dockerfile`: thêm stage tải Potree bằng `scripts/fetch-potree.sh` (một nguồn pin phiên bản và SHA-256 duy nhất, truyền qua `additional_contexts` trong `compose.yaml`).
2. `compose.yaml`: `platform: linux/amd64` cho backend.

### Lần 2: với hai sửa trên

**13/13 bước pass.** Ngoài script, mở `/viewer/<id>` trong Chromium (WebGL phần mềm) với dataset vừa convert: canvas Potree hiện, vẽ 5 điểm, không có lỗi console.

## Giới hạn của lần chạy này

- Chạy trên máy dev, không phải VM mới: cache layer của Docker còn một phần (ví dụ image nền), nên **chưa đo được thời gian build từ máy hoàn toàn trống**.
- Chạy giả lập amd64 trên arm64; chưa chạy trên Linux amd64 thật (là môi trường mà Compose nhắm tới).
- API crop (#32) chưa có, nên phần crop chỉ kiểm tra `PdalCropProcessor` trực tiếp trong container, chưa phải luồng crop từ UI.
- Dataset mẫu chỉ có 5 điểm; chưa thử LAZ upload hay file lớn.
