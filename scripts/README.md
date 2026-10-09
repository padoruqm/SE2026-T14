# Scripts

## Local commit hook

Sau khi cài `pre-commit` theo tài liệu chính thức phù hợp với máy của bạn, chạy tại root repository:

```bash
pre-commit install --hook-type commit-msg
git config commit.template .gitmessage
```

Hook dùng `validate-commit-msg.sh` để kiểm tra Conventional Commit trước khi tạo commit. CI kiểm tra lại subject của toàn bộ commit trong PR, nên hook không phải cơ chế bảo vệ duy nhất.

Không ghi phiên bản hoặc lệnh cài `pre-commit` trong repository vì chúng cần được xác minh ở môi trường thực tế trước khi chốt.

## GitHub automation

`github/create-labels-and-milestones.sh` chỉ in kế hoạch mặc định. Nó chỉ gọi GitHub API khi truyền `--apply`; không chạy script này trước khi nhóm duyệt rõ các thao tác remote.
