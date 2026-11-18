# Thiết lập CoreIOT theo thứ tự (T11, T12, T13, T15)

Các JSON ở đây đã được chuẩn bị cục bộ; **chưa import hoặc xác minh trên tài khoản CoreIOT**.
Gateway dùng MQTT Gateway API theo tài liệu ThingsBoard; cần xác nhận CoreIOT của lớp hỗ trợ cùng API và phiên bản widget.
Không cần gửi mật khẩu đăng nhập hay token cho người khác. Bạn tự nhập token vào terminal trên máy mình.

## 1. Tạo gateway và child device — T08, T15

1. Đăng nhập CoreIOT do lớp cung cấp. Mở **Entities → Devices** (tên menu có thể khác theo phiên bản).
2. Tạo thiết bị `smartroom-pc-gateway`, bật **Is gateway**. Nếu có lựa chọn **Overwrite activity time**, giữ thiết lập mặc định của lớp.
3. Lấy **Access token của gateway**, không phải token child device.
4. Copy `gateway/config.example.json` thành `runtime/config.json`. Điền `mqtt_host` là **hostname MQTT của CoreIOT**, không kèm `https://` hoặc đường dẫn. Điền cổng MQTT/TLS theo server lớp; mặc định 8883 và `mqtt_tls: true`.
5. Trong PowerShell tại gốc dự án, nhập kín token rồi chạy:

```powershell
$secret = Read-Host 'Gateway access token' -AsSecureString
$env:COREIOT_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
python -m gateway.main --config runtime/config.json --cloud
```

6. Gateway gửi `v1/gateway/connect` cho child `room-node-01`, sau đó gửi `v1/gateway/telemetry`. Nếu server không tự tạo child, tạo thủ công tên **chính xác** `room-node-01`, loại `SmartRoom`, rồi kiểm tra quan hệ với gateway.
7. Tại child → Latest telemetry, phải có `temperature`, `humidity`, `fan`, `seq`, `boot`, `anomaly`, `anomaly_score`, `data_source`.
8. Chụp ảnh gateway và child; lưu vào `evidence/hardware/`. Nếu có ngắt mạng, outbox SQLite tăng và phát lại sau PUBACK. PUBACK không chứng minh RuleChain đã xử lý xong.

Có thể thử kết nối cloud với `--simulate --cloud` trước khi mang board tới lớp. Dữ liệu này luôn có `data_source=simulation`; không dùng làm bằng chứng cảm biến thật.

## 2. Dashboard từ template — T11

Nguồn tái sử dụng: template **Thermostats** chính thức của ThingsBoard, Apache-2.0;
`templates/thermostats.upstream.json` giữ bản gốc và `templates/PROVENANCE.json` ghi commit/URL/hash.
`make_dashboard.py` giữ widget nhiệt độ, độ ẩm và alarm; thay alias, bỏ map/form quản trị không dùng.

1. Mở Dashboards → Import → `coreiot/smartroom_dashboard.json`.
2. Mở Entity aliases, kiểm tra alias `SmartRoom sensor` tìm được **room-node-01**. Nếu phiên bản không hỗ trợ filter `deviceName`, chọn **Single entity → Device → room-node-01** rồi Save.
3. Kiểm tra hai biểu đồ và alarm table. Nếu thiếu widget `system.time_series_chart` ở phiên bản cũ, thêm widget Time series chart có sẵn và gắn hai key tương ứng. Đây là bước tương thích cần xác minh trên CoreIOT thực tế.
4. Thêm widget **Control → RPC button/switch**. Chọn child `room-node-01`, method `setFan`, params **boolean** `true`/`false`, two-way RPC, timeout 10000 ms. Không truyền chuỗi `"true"` hay object `{value:true}`.
5. Với switch có hàm chuyển đổi params, dùng `return value;`. Nếu switch cần get-state method chưa có, dùng hai RPC button Bật/Tắt và widget hiển thị telemetry `fan` để xem trạng thái.
6. Thử quạt thật. Gateway chỉ trả `success:true` sau ACK node; không có ACK sẽ hết hạn sau 5 giây. Firmware tự tắt đầu ra sau lease 30 giây và telemetry cập nhật lại.
7. Export dashboard **từ tài khoản thực** vào `evidence/hardware/coreiot_dashboard.verified.json`, chụp ảnh và ghi timestamp demo.

## 3. RuleChain — T12

Import `coreiot/smartroom_rulechain.json` vào Rule chains. Đặt `root=false`; giữ nguyên root chain của tài khoản.
Từ nhánh **Post telemetry** của root (hoặc chain của Device Profile), thêm node **Rule Chain** gọi `SmartRoom alarms`.
Chỉ gắn với Device Profile/thiết bị của dự án để không tác động dữ liệu thiết bị khác.

Nếu JSON khác schema của phiên bản CoreIOT, dựng bằng giao diện với cùng các node sau:

1. **Message Type Switch**: chỉ `Post telemetry` vào Save Timeseries.
2. **Save Timeseries**: lưu dữ liệu; Success → Script Filter `High or anomaly`.
3. **Script Filter** chạy JavaScript trong `rulechain/smartroom_filter.js`.
4. Nhánh True → **Create alarm**, type `SmartRoom Environment`, severity `MAJOR`, originator là child device, propagate=false.
5. Nhánh False → Script Filter dùng `rulechain/smartroom_clear.js`; True → **Clear alarm** cùng type.
6. Alarm details chứa temperature, humidity, anomaly và data_source. Giá trị trong vùng 30–32 °C hoặc 75–80 %RH giữ trạng thái cảnh báo trước đó.

Thử giá trị nóng → vùng trung gian → bình thường; alarm phải tạo → giữ → clear. Lưu ảnh chain và alarm thực tế.

## 4. Notification — T13

Alarm xuất hiện trong bảng **chưa đồng nghĩa** đã gửi notification.

1. Mở Notification Center (nếu tài khoản có), tạo Recipient là user của nhóm.
2. Tạo template `SmartRoom environment warning`, nội dung chứa thiết bị, mức cảnh báo và thời gian. Chọn In-app; thêm email nếu server lớp đã cấu hình SMTP.
3. Tạo Notification rule với trigger **Alarm created**, lọc alarm type `SmartRoom Environment`, severity `MAJOR`, gắn template và recipient.
4. Nếu server không có Notification Center, từ đầu ra **Created** của Create alarm dùng node Send email; cần SMTP hợp lệ do người quản trị lớp cấp. Không tự nhận T13 khi chưa nhận được thông báo thật.
5. Tạo một alarm mới và chụp **thông báo đã nhận**. Tránh gửi lặp mỗi chu kỳ 2 giây: trigger theo alarm mới, không theo mọi bản tin nóng.

## 5. Minh chứng phải bổ sung trước nộp

- Ảnh mạch, Serial log từ hai node, GPIO/pinout đã xác nhận.
- Ảnh web server tại `192.168.4.1` và điều khiển thực tế (PC gateway đang chạy).
- Ảnh CoreIOT gateway-child, telemetry, template dashboard/RPC, RuleChain, alarm và notification.
- CSV đo độ trễ thực tế và video 5–10 phút. `docs/DEMO.md` là kịch bản, chưa phải video đã quay.
- Đổi mã nhóm trong `report/metadata.json`, cập nhật video/dashboard URL, chạy lại `python scripts/build_report.py`.

T14 OTA không triển khai. Không nhận điểm T01 vì cảm biến I2C chạy Arduino, không chạy Tasmota. Không nhận T04/T05 vì AI chạy PC, không phải TinyML trên board.
