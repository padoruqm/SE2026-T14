# Hướng dẫn demo và lời thoại (S4-Q4, #43)

Tài liệu cho người trình bày demo Point Cloud Explorer: chuẩn bị gì, bấm gì theo thứ tự nào, nói gì, và làm gì khi có sự cố. Kịch bản đi theo luồng MVP **Upload → Viewer → Measure → Crop → mở kết quả → Export**.

Kịch bản viết theo những gì đang có trên `dev`. Phần nào chưa có trên `dev` được đánh dấu **[chưa có]** ở bảng [Phạm vi](#phạm-vi). Trước buổi demo, cập nhật bảng đó và bỏ hoặc thêm bước tương ứng.

## Phạm vi

| Phần | Trạng thái trên `dev` | Trong demo |
|---|---|---|
| Upload LAS/LAZ, convert, theo dõi tiến độ | Có | Bước 1–2 |
| Viewer: xoay/pan/zoom, Reset view, Point size, Color | Có | Bước 3 |
| Metadata: file, số điểm, CRS, bounds | Có | Bước 3 |
| Measure: tọa độ, khoảng cách | Có | Bước 4 |
| Chọn vùng crop, gửi crop, theo dõi job | Có | Bước 5 |
| Mở kết quả crop trong viewer (#29) | Có link; bản sửa xoá vùng/phép đo cũ ở PR #98 | Bước 6 |
| Download API (#37) | Có | Bước 7 (qua URL) |
| Download UI (#38) | **[chưa có]**: PR #97 đã merge vào `feat/37-download-api`, chưa vào `dev` | Bước 7 nếu đã vào `dev` |
| Filter (S4-D1, S4-D2, S4-P1, S4-Q1, S4-Q2) | **[chưa có]** | Chỉ nhắc ở phần kết |
| Số đo FPS trên máy demo (S4-Q3) | **[chưa có]** | Không nêu con số nào chưa đo |

## Chuẩn bị

### Một ngày trước

1. **Máy demo.** Dùng đúng máy sẽ trình bày. Cần Docker Desktop/Engine có Compose ≥ 2.17 và một trình duyệt có WebGL (Chrome, Edge hoặc Firefox bản mới; bật hardware acceleration).
2. **Mã nguồn.** Checkout commit sẽ demo và ghi lại hash vào [Bản ghi](#bản-ghi). Không demo từ nhánh đang sửa dở.
3. **Build và smoke test** (lần build đầu trên Apple Silicon chậm vì backend chạy giả lập `linux/amd64`):

   ```bash
   docker compose up --build -d
   ./scripts/smoke-test.sh        # phải pass hết; dừng lại sửa nếu có FAIL
   ```

4. **Dữ liệu demo.** Chuẩn bị sẵn trong một thư mục dễ tìm:
   - **Dataset chính:** một file LAS/LAZ có hình dạng nhìn ra được (địa hình, nhà, cây), có CRS, **dưới 100 MB** (giới hạn mặc định `APP_MAX_UPLOAD_BYTES`). Upload và convert thử trước một lần để biết mất bao lâu trên máy này.
     - Chọn CRS **mét** (ví dụ UTM) thì Measure hiển thị `m`. Bộ mẫu Autzen của PDAL (đã dùng khi sửa CRS ở #95) dùng **feet**, nên panel hiện `units`. Nếu dùng Autzen, nói rõ điều này (xem lời thoại bước 4).
   - **File dự phòng:** `data/sample/demo.las` từ `python scripts/generate-sample-las.py` (5 điểm, EPSG:32648). Rất nhỏ, chỉ để chứng minh luồng chạy khi dataset chính có vấn đề.
   - **File sai định dạng:** một file `.txt` bất kỳ, để cho thấy lỗi upload.
5. **Chạy thử toàn bộ kịch bản một lần** và ghi lại ở [Bản ghi](#bản-ghi): thời gian convert, thời gian crop, vùng crop đã dùng (sáu giá trị Min/Max), ID của dataset đã convert sẵn.

### 30 phút trước

1. `docker compose up -d`, mở `http://localhost:5173`. Kiểm tra `http://localhost:8000/health`.
2. **Convert sẵn một bản dataset chính** và giữ tab `/viewer/<id>` của nó. Nếu convert lúc demo chậm hoặc lỗi thì chuyển sang tab này.
3. Mở sẵn các tab: `/upload`, `/viewer/<id đã convert sẵn>`, và `http://localhost:8000/docs` (Swagger, để dự phòng).
4. Tắt thông báo hệ thống, phóng to trình duyệt (Ctrl/Cmd +) cho người xem đọc được panel, đóng DevTools.
5. Ghi sẵn ra giấy: ID dataset, sáu giá trị vùng crop đã thử, đường dẫn file.

## Kịch bản

Thời lượng dự kiến khoảng 8–10 phút, chưa tính hỏi đáp. Mỗi bước gồm: **Làm** (thao tác), **Nói** (lời thoại gợi ý, không cần đọc nguyên văn) và **Phải thấy** (dấu hiệu bước đã chạy đúng; nếu không thấy thì xem [Sự cố](#sự-cố-và-cách-xử-lý)).

### 0. Mở đầu (~1 phút)

**Làm:** Mở tab `/upload`.

**Nói:**
> Nhóm em làm Point Cloud Explorer: một ứng dụng web để xem và xử lý đám mây điểm LiDAR ngay trên trình duyệt, không cần cài phần mềm GIS. Luồng chính là tải file LAS/LAZ lên, xem 3D, đo đạc, cắt vùng quan tâm thành một dataset mới và tải kết quả về. Frontend là Vue 3, viewer dùng Potree; backend là FastAPI, xử lý bằng PotreeConverter và PDAL, tất cả chạy bằng Docker Compose.

### 1. Upload và kiểm tra file (~1 phút)

**Làm:**
1. Chọn file `.txt`.
2. Chọn dataset chính, bấm **Upload**.

**Nói:**
> Trước hết, nếu chọn nhầm file không phải point cloud thì ứng dụng báo ngay, chưa gửi gì lên server. Server cũng kiểm tra lại phần mở rộng và chữ ký `LASF` ở đầu file, nên đổi tên file cũng không lọt qua được.
>
> Giờ em tải file thật lên.

**Phải thấy:** với file `.txt` có thông báo *Only .las and .laz files are supported.* và nút Upload bị khoá. Với file thật, nút chuyển sang *Uploading…* rồi *Converting…*.

### 2. Convert cho viewer (~1 phút, tuỳ kích thước file)

**Nói (trong lúc chờ):**
> Sau khi upload, backend tạo một job nền chạy PotreeConverter để chia point cloud thành octree. Nhờ vậy trình duyệt chỉ tải phần đang nhìn thấy chứ không tải cả file. Thanh tiến độ ở đây là tiến độ thật do converter báo về, giao diện poll trạng thái job.

**Phải thấy:** *Conversion queued…*, *Conversion in progress…* kèm phần trăm, rồi *Conversion complete for &lt;tên file&gt; (ID: pc_…).*

**Làm:** Hiện trang upload chưa có link sang viewer. Copy ID và mở `http://localhost:5173/viewer/<ID>`. Nếu convert quá lâu, nói *"Để tiết kiệm thời gian, em mở bản đã convert sẵn từ trước"* rồi chuyển sang tab đã chuẩn bị.

### 3. Xem 3D và metadata (~1,5 phút)

**Làm:**
1. Kéo chuột trái để xoay, chuột phải để pan, lăn chuột để zoom; bấm **Reset view**.
2. Tăng **Point size**; đổi **Color** sang **Elevation** (và **RGB**/**Intensity** nếu file có các trường này).
3. Cuộn xuống panel **Metadata**.

**Nói:**
> Đây là viewer Potree nhúng trong Vue. Xoay, pan, zoom như các phần mềm 3D; Reset view đưa camera về toàn cảnh. Đổi kích thước điểm và chế độ màu chỉ thay đổi cách vẽ, không xử lý lại dữ liệu, nên phản hồi ngay. Màu theo độ cao giúp thấy địa hình rõ hơn.
>
> Panel Metadata đọc trực tiếp từ header của file LAS: tên file, số điểm, hệ toạ độ (CRS) và khung bao. CRS được đọc từ GeoTIFF key hoặc WKT trong file. Nếu file không khai báo mã EPSG thì ứng dụng ghi "Not available", chứ không đoán.

**Phải thấy:** point cloud hiện ra và vừa khung hình, không trắng màn hình; đổi màu và kích thước có tác dụng ngay; Metadata có số điểm, CRS và bảng bounds.

### 4. Measure (~1,5 phút)

**Làm:**
1. Bấm **Measure**, click một điểm: panel hiện X/Y/Z.
2. Click điểm thứ hai: panel hiện Distance, Horizontal, Vertical; viewer vẽ đường nối và nhãn.
3. Bấm **Clear measurement**, chọn **Keep**, rồi làm lại và chọn **Delete**.
4. Bấm **Stop measuring**.

**Nói:**
> Công cụ đo cho toạ độ thật của điểm trong hệ toạ độ của dữ liệu, chứ không phải toạ độ nội bộ của viewer. Nhóm đã kiểm chứng phép đổi toạ độ này trong spike riêng. Với hai điểm thì có khoảng cách thẳng, phần ngang và phần chênh cao. Đơn vị lấy theo CRS: hệ UTM thì là mét.
>
> *(Nếu dataset dùng feet hoặc không rõ CRS)* Ở đây hiện "units" vì file này dùng đơn vị feet, mà ứng dụng chỉ ghi "m" khi chắc chắn là mét. Ứng dụng không mặc định coi mọi thứ là mét.
>
> Xoá phép đo luôn hỏi lại. Công cụ này chỉ đọc, không gửi request ghi nào và không đổi dữ liệu.

**Phải thấy:** tọa độ là số lớn đúng hệ toạ độ (ví dụ UTM hàng trăm nghìn/triệu mét), không phải số quanh 0; khoảng cách hợp lý so với kích thước vật thể.

### 5. Chọn vùng và crop (~2 phút)

**Làm:**
1. Trong panel **Crop region**, bấm **Pick region**, click hai góc đối diện của một vùng dễ nhận ra (một toà nhà, một khúc đường). Nếu click khó trúng, gõ sáu giá trị đã ghi sẵn.
2. Chỉ cho người xem hộp crop vẽ trên viewer và sáu giá trị trong panel.
3. Ở panel **Crop**, giữ **LAZ (compressed)**, bấm **Crop point cloud**.

**Nói:**
> Để lấy riêng một vùng, em click hai góc đối diện. Ứng dụng vẽ hộp crop trong không gian 3D, với chiều cao lấy theo toàn bộ dải độ cao của dữ liệu và có thể sửa tay. Vùng chọn được kiểm tra trước khi gửi: không có diện tích hoặc nằm ngoài dữ liệu thì không gửi được. Nếu vùng tràn ra ngoài thì được cắt lại cho vừa point cloud.
>
> Khi gửi, backend dùng PDAL cắt file gốc, rồi convert phần đã cắt cho viewer. Kết quả là một dataset mới; file gốc không bị thay đổi. Server cũng kiểm tra lại vùng crop với cùng quy tắc như giao diện.

**Phải thấy:** *Crop queued…*, *Cropping… N%*, rồi *Crop complete. The original point cloud is unchanged.* cùng link **Open the cropped point cloud**.

**Có thể thêm (nếu còn thời gian):** gõ một vùng nằm ngoài dữ liệu để thấy *The region does not overlap the point cloud.* và nút Crop bị khoá.

### 6. Mở kết quả crop (~1 phút)

**Làm:** Bấm **Open the cropped point cloud**. Mở panel **Metadata**.

**Nói:**
> Kết quả mở ra như một point cloud bình thường, với ID riêng. Tên file là tên gốc thêm hậu tố `-crop`, số điểm và khung bao được đọc lại từ chính file đã cắt, nên nhỏ hơn bản gốc. Có thể đo, crop tiếp hoặc tải về giống như file upload.

**Phải thấy:** viewer chỉ còn vùng đã chọn; Metadata có tên `…-crop.laz`, số điểm ít hơn bản gốc, bounds khớp vùng đã chọn. Nếu PR #98 đã vào `dev`: panel có dòng **Cropped from** link về bản gốc, và hộp crop cùng phép đo cũ không còn trên màn hình. Nếu chưa vào `dev` thì hộp crop cũ có thể vẫn hiện: bấm **Clear** trước khi nói tiếp.

### 7. Export (~0,5 phút)

**Làm:**
- Nếu Download UI (#38) đã vào `dev`: trong panel Metadata của kết quả crop, bấm **Download LAS/LAZ**.
- Nếu chưa: mở `http://localhost:5173/api/pointcloud/<ID kết quả>/download` trong tab mới.

**Nói:**
> File đã cắt được giữ nguyên dạng LAS/LAZ nên tải về và mở được bằng các công cụ khác như PDAL hay CloudCompare. Chỉ dataset đã sẵn sàng mới tải được; nếu chưa xong, server trả lỗi rõ ràng thay vì một file hỏng.

**Phải thấy:** trình duyệt tải về `<tên gốc>-crop.laz`.

### 8. Kết (~0,5 phút)

**Nói:**
> Tóm lại, luồng chính chạy đầu cuối: upload, xem 3D, đo, cắt thành dataset mới và tải về, tất cả trên trình duyệt với một lệnh `docker compose up`. Phần tiếp theo nhóm đang làm là bộ lọc theo độ cao, phân lớp và nhiễu, chạy qua cùng cơ chế job như crop, và tối ưu hiệu năng viewer trên máy demo.

Không nêu con số hiệu năng (FPS, số điểm tối đa) nếu S4-Q3 chưa đo và ghi lại.

## Sự cố và cách xử lý

| Sự cố | Cách xử lý ngay | Nguyên nhân thường gặp |
|---|---|---|
| Convert quá lâu | Nói câu chuyển tiếp ở bước 2, mở tab dataset đã convert sẵn | File lớn; backend chạy giả lập amd64 trên Apple Silicon |
| Job convert `failed` | Mở tab đã convert sẵn; sau demo xem `docker compose logs backend` | Converter lỗi với file đó |
| Viewer trắng hoặc báo *3D view is not available* | Bật hardware acceleration hoặc đổi trình duyệt; dự phòng: chiếu ảnh/GIF quay sẵn | WebGL bị tắt |
| `/potree/...` lỗi, viewer không tải | `docker compose up --build frontend` (trước demo, không làm giữa chừng) | Image frontend thiếu Potree |
| Upload báo file quá lớn (413) | Dùng dataset nhỏ hơn | Vượt `APP_MAX_UPLOAD_BYTES` (mặc định 100 MB) |
| Crop báo *The selected region contains no points* | Chọn vùng có điểm (dùng sáu giá trị đã ghi sẵn) | Vùng nằm giữa các điểm hoặc trong khoảng trống |
| Click Pick region khó trúng điểm | Gõ sáu giá trị đã ghi sẵn | Click vào chỗ không có điểm |
| Backend restart giữa chừng | Dataset đã convert vẫn còn; job đang chạy thì mất, phải gửi lại | Job lưu trong bộ nhớ (giới hạn MVP) |
| Mọi thứ hỏng | Chiếu video quay lại buổi chạy thử | |

**Nên quay sẵn** một video toàn bộ kịch bản trong buổi chạy thử, dùng làm phương án cuối.

## Câu hỏi có thể gặp

- **Dữ liệu lớn thì sao?** Viewer chỉ tải phần octree đang nhìn thấy nên không phải tải cả file. Giới hạn upload hiện tại là 100 MB (cấu hình được). Chưa có số đo hiệu năng chính thức trên máy demo; đó là việc của S4-Q3.
- **Có sửa file gốc không?** Không. Crop luôn tạo dataset mới (`sourceId` trỏ về bản gốc); Measure chỉ đọc.
- **Tọa độ có đúng không?** Tọa độ là toạ độ world của dữ liệu, đã kiểm chứng ở spike #25 và test E2E với fixture UTM.
- **Sao không có mét với file này?** Ứng dụng chỉ ghi `m` khi CRS chắc chắn dùng mét; CRS dùng feet hoặc không rõ thì ghi `units`, CRS địa lý thì không tính khoảng cách thẳng.
- **Lưu trữ ở đâu?** Filesystem trong Docker volume `point-cloud-data` (MVP). Job nằm trong bộ nhớ nên mất khi restart backend; dataset đã xong thì vẫn còn.

## Sau demo

- `docker compose down` (thêm `-v` chỉ khi muốn xoá cả dữ liệu đã upload).
- Ghi một khối vào [Bản ghi](#bản-ghi), mở issue cho lỗi phát hiện được.

## Bản ghi

Mỗi lần chạy thử hoặc demo thật, thêm một khối theo mẫu:

```text
### <YYYY-MM-DD> <chạy thử | demo>
- Người trình bày:
- Máy / OS / Docker:
- Trình duyệt + phiên bản:
- Commit:
- Dataset chính (file, số điểm, CRS, kích thước):
- Thời gian convert / crop:
- Vùng crop đã dùng (minX, maxX, minY, maxY, minZ, maxZ):
- Bước lỗi hoặc phải dùng dự phòng:
- Video/ảnh:
```

Chưa có bản ghi.
