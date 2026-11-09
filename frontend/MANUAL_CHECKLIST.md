# Checklist thủ công cho viewer và Measure (S2-Q3, #17)

Chạy trước mỗi release và khi review PR đổi viewer (#15, #19, #29). Mỗi lần chạy ghi một khối "Bản ghi" ở cuối file: ngày, máy, trình duyệt, dataset, kết quả từng mục, ảnh/GIF.

## Chuẩn bị

```bash
python scripts/generate-sample-las.py        # data/sample/demo.las (5 điểm, EPSG:32648)
./scripts/fetch-potree.sh                    # Potree vào frontend/public/potree
docker compose up --build                    # hoặc make dev + npm run dev
```

Upload LAS, bấm convert, chờ job `succeeded`, mở `/viewer/<id>`. Để đo khoảng cách có ý nghĩa nên dùng lưới nhiều điểm (xem PR #81: lưới 40.000 điểm, UTM); `demo.las` chỉ có 5 điểm.

Ký hiệu: ✅ đã kiểm chứng (nêu cách), ⬜ chưa chạy, cần người chạy trên trình duyệt có WebGL.

## A. Checklist viewer (hướng dẫn mục 10)

| # | Mục | Kết quả |
|---|---|---|
| A1 | WebGL capability check không báo lỗi trên máy demo | ⬜ |
| A2 | Dataset mẫu xuất hiện, fit-to-screen đúng, không trắng màn hình | ⬜ |
| A3 | Xoay, zoom, pan hoạt động; reset view hoạt động | ⬜ |
| A4 | Point size và color mode đổi được, không convert lại | ⬜ |
| A5 | Resize cửa sổ không méo canvas hay mất controls | ⬜ |
| A6 | Measure distance và world coordinates cho kết quả hợp lý | ⬜ (xem phần B) |
| A7 | Crop selection khớp vùng hiển thị; kết quả mở lại được | ⬜ chưa áp dụng (crop chưa có) |
| A8 | Loading, empty, lỗi xử lý có thông báo rõ | ⬜ |
| A9 | Chuyển dataset/route 3 lần: không canvas trùng, không listener trùng | ⬜ (phần listener có unit test, xem B4) |

## B. Checklist riêng cho Measure (#19)

| # | Mục | Cách kiểm | Kết quả |
|---|---|---|---|
| B1 | Chọn 2 điểm → khoảng cách theo đơn vị dataset, không giả định mét | Trình duyệt: đo, so với giá trị tính tay. Unit: `units.spec.ts` (`m` cho UTM/3857/4978, `units` cho CRS lạ, từ chối khoảng cách cho CRS địa lý) | Unit ✅ (PR #81 head: 169 test pass). Trình duyệt ⬜ |
| B2 | Chọn 1 điểm → X/Y/Z world, so với giá trị biết trước | Trình duyệt, so với `pdal info` hoặc fixture sinh bởi `generate-sample-las.py` (**CẦN XÁC MINH** công cụ kiểm tra) | ⬜ |
| B3 | Xoá phép đo có xác nhận; dữ liệu nguồn không đổi (reload vẫn như cũ) | Unit: `useMeasure.spec.ts`, `MeasurePanel.spec.ts`. Trình duyệt: Delete/Keep, reload, xem Network chỉ có GET | Unit ✅. Trình duyệt ⬜ |
| B4 | Tắt tool/đổi dataset không để lại annotation hoặc listener | Unit: `potreeMeasure.spec.ts` (gỡ listener khi disable và dispose). Trình duyệt: bật/tắt 3 lần, đổi dataset 3 lần | Unit ✅. Trình duyệt ⬜ |
| B5 | Công thức khoảng cách có unit test với giá trị tính tay | `measurement` (từ #73) và `projection.spec.ts`; tác giả ghi dx=24, dy=16, dz=2.401 → 28.944 | ✅ (đã đọc test, pass) |

## C. Điều đã kiểm chứng trong review PR #81

- Lint, typecheck, `npm test` (169 test) pass trên PR #81 gộp với `dev`, ngày 2026-11-06.
- Review code: chọn điểm chỉ khi click (kéo chuột bị bỏ qua), chiếu điểm bằng double, trạng thái tối đa hai điểm, từ chối khoảng cách cho CRS địa lý.
- Kết quả kiểm tra trên trình duyệt thật (Potree 1.8.2, lưới UTM 40.000 điểm) là do tác giả báo trong mô tả PR #81, chưa được lặp lại độc lập ở đây.

## D. Mẫu bản ghi

```text
### Bản ghi <YYYY-MM-DD>
- Máy / OS:
- Trình duyệt + phiên bản:
- Dataset (file, số điểm, CRS):
- Commit / PR:
- Kết quả: A1 ✅/❌ ... B5 ✅/❌ (ghi giá trị đo và giá trị tính tay)
- Ảnh/GIF:
- Lỗi phát hiện (link issue):
```

## Bản ghi

Chưa có bản ghi chạy thủ công.
