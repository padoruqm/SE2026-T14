# VT-057 – Runtime upload limit (Hoàng Minh Quang, 23001917)

Change request: đổi một cấu hình nghiệp vụ (giới hạn upload) mà không sửa mã nguồn.

- `GET /api/config` → `{"maxUploadBytes": <số byte đang dùng>}`
- `PUT /api/admin/config` với header `X-Admin-Token: $APP_ADMIN_TOKEN` và body `{"maxUploadBytes": n}`, với `1 ≤ n ≤ 1073741824`.
  Thiếu token trả 401, sai token trả 403. Nếu không đặt `APP_ADMIN_TOKEN` thì mọi request đều bị từ chối.
  Giá trị chỉ lưu trong bộ nhớ, khởi động lại sẽ quay về `APP_MAX_UPLOAD_BYTES`.

## Cài đặt (một lần)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "backend[dev]"
```

## Chạy test

```bash
make test                                                          # toàn bộ backend
cd backend/tests && PYTHONPATH=.. python3 -m unittest test_runtime_config_api -v   # chỉ VT-057
```

## Kiểm chứng thêm (chạy từ thư mục gốc repo)

```bash
PYTHONPATH=backend:backend/tests python3 qa/vt057/flaky_check.py   # 30 vòng, thứ tự ngẫu nhiên
PYTHONPATH=backend:backend/tests python3 qa/vt057/load_test.py 3   # 80 tác vụ đồng thời, p95 ≤ 2.5 s
```

Đo coverage là tùy chọn. Công cụ `coverage` không được thêm vào dependency của dự án:
`pip install coverage && PYTHONPATH=backend python3 -m coverage run --branch --source=backend/app -m unittest discover -s backend/tests && python3 -m coverage report`

## Mutation (chỉ dùng tạm, không nằm trong nhánh nộp bài)

```bash
git apply qa/vt057/evidence/03-mutation.diff && make test    # phải có test FAIL
git apply -R qa/vt057/evidence/03-mutation.diff              # gỡ mutation
```

Log của từng bước nằm trong `qa/vt057/evidence/`: red, green, mutation, coverage, flaky và load.
