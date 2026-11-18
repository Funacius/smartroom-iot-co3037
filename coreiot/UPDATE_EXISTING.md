# Cập nhật đúng dashboard đang dùng

Dashboard hiện tại: <https://app.coreiot.io/dashboards/all/0ca724e0-e352-11f1-8cd8-29dc599bec29>.

Không cần import lại hoặc tạo thêm dashboard. `scripts/update_coreiot_dashboard.py` đọc dashboard này qua REST API, sao lưu bản gốc, đổi hai nút `setFan` thành một Switch Control rồi lưu **cùng ID**. Biểu đồ, alarm, tên, quyền chia sẻ và các thiết lập khác được giữ lại. Script dừng nếu dashboard bị người khác lưu trong lúc chuẩn bị thay đổi.

## Chạy một lần trên máy bạn

Giữ gateway đang chạy. Mở một terminal VS Code khác ở gốc dự án:

```powershell
python scripts/update_coreiot_dashboard.py --apply --remember-session
```

Nếu dùng môi trường ảo, thay `python` bằng `.venv\Scripts\python`. Nhập email tài khoản CoreIOT và mật khẩu trong terminal; mật khẩu được nhập kín, không được ghi log hoặc lưu file. Đây là tài khoản đăng nhập web, **không phải access token của gateway**. Không gửi thông tin đăng nhập trong cuộc trò chuyện.

Sau khi thành công, tải lại tab dashboard hiện tại bằng Ctrl+R. URL và ID giữ nguyên. Backup và preview nằm trong `runtime/coreiot-backups/`; kết quả đã lưu/xác minh nằm ở `evidence/coreiot_switch_update.json`.

`--remember-session` là tùy chọn: nó lưu token phiên được Windows DPAPI mã hóa cho tài khoản Windows hiện tại, trong `runtime/coreiot-user-session.dpapi` (đã loại khỏi Git). Không lưu mật khẩu tài khoản. Nhờ phiên này, các lần cập nhật tiếp theo có thể chạy trực tiếp trên máy bằng:

```powershell
python scripts/update_coreiot_dashboard.py --apply --non-interactive
```

Chỉ dùng lệnh đó cho thay đổi dashboard đã được bạn yêu cầu. Khi phiên hết hạn hoặc bị thu hồi, chạy lại lệnh đăng nhập. Để bỏ phiên đã lưu:

```powershell
python scripts/update_coreiot_dashboard.py --forget-session
```

Nếu không muốn lưu phiên, bỏ `--remember-session`. Chạy không có `--apply` chỉ lấy dữ liệu và tạo preview/backup, không lưu lên cloud. Tài khoản dùng SSO/2FA có thể dùng `--jwt` để nhập kín **user JWT** hiện tại tại terminal, thay cho đăng nhập email/mật khẩu.

## Switch hoạt động thế nào

- Widget gốc: **Control widgets → Switch Control**.
- Target: lấy lại đúng target của hai nút `setFan` hiện có.
- Retrieve value using method: **Time series**, key **fan**.
- RPC set value method: **setFan**.
- Convert value function: `return value === true;`.
- Parse value function: `return data === true || data === "true" || data === 1;`.
- Timeout: 10000 ms.

Switch Control gốc gửi RPC một chiều khi gạt; trạng thái được đồng bộ lại từ telemetry `fan`. Vì vậy không cần thêm `getFan` vào gateway hoặc thay firmware. Đối chiếu nhật ký `command_applied` và telemetry để xác nhận node đã áp dụng; chỉ nhìn động tác gạt chưa đủ chứng minh điều khiển thành công.

Nếu muốn làm bằng giao diện web: **Edit mode → Add widget → Control widgets → Switch Control**, điền các mục trên, xóa hai nút cũ và Save ngay dashboard hiện tại. Không chọn chế độ lấy trạng thái bằng RPC `getValue`, vì gateway hiện chỉ hỗ trợ `setFan`.

## Phạm vi đã kiểm tra

Đã kiểm tra cục bộ: giữ ID/tên/widget khác, không thêm switch khi chạy lại, sao lưu, chặn ghi đè khi có thay đổi đồng thời, mã hóa/giải mã phiên Windows và không lộ thông tin đăng nhập trong lỗi HTTP. Chưa gọi API lưu dashboard thật trong phiên chuẩn bị vì chưa có phiên đăng nhập người dùng trên máy dành cho script này.

Tài liệu gốc: [REST API](https://thingsboard.io/docs/reference/rest-api/), [Switch Control implementation](https://github.com/thingsboard/thingsboard/blob/master/ui-ngx/src/app/modules/home/components/widget/lib/rpc/switch.component.ts).
