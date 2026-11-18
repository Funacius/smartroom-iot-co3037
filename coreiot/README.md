# Thiết lập CoreIOT theo thứ tự (T11, T12, T13, T15)

## Dashboard đang dùng: cập nhật tại chỗ

Dashboard cố định của nhóm: <https://app.coreiot.io/dashboards/all/0ca724e0-e352-11f1-8cd8-29dc599bec29>. Người dùng xác nhận bản RPC đã chạy; API local cũng ghi các lệnh có RPC ID ở trạng thái `applied`. Tiếp theo đổi hai nút thành một switch trên **chính dashboard này**, giữ nguyên ID.

Chạy `python scripts/update_coreiot_dashboard.py --apply --remember-session` trong terminal khác, nhập kín tài khoản CoreIOT, rồi refresh tab hiện tại. Script sao lưu trước khi ghi; tùy chọn remember lưu phiên được Windows mã hóa để các lần cập nhật sau có thể thực hiện trực tiếp, không import lại. Xem [hướng dẫn cập nhật tại chỗ](UPDATE_EXISTING.md). Hiện script đã được kiểm thử cục bộ; chưa lưu switch lên cloud vì cần đăng nhập người dùng một lần.

## Trạng thái và bước tiếp theo

Ngày 18/11/2026, người dùng xác nhận Latest telemetry và các nút RPC chạy. API gateway local cổng 8081 ghi nguồn `simulation`, dữ liệu mới, outbox bằng 0 và các lệnh có RPC ID ở trạng thái applied. Đây là kiểm chứng với node mô phỏng, chưa phải quạt phần cứng.

Giữ terminal `start_coreiot.py` đang chạy. Mở **Dashboards → + → Import dashboard**, chọn `coreiot/smartroom_dashboard.json` rồi Import. Nếu nút Import nằm riêng ở thanh công cụ, chọn nút đó. Mở dashboard **SmartRoom CO3037**, vào Edit → Entity aliases và kiểm tra alias **SmartRoom sensor** trỏ đến `room-node-01`. Nếu alias không resolve, đổi thành **Single entity → Device → room-node-01** và Save.

Người dùng đã gửi ảnh dashboard CoreIOT: hai biểu đồ nhận dữ liệu từ `room-node-01`; bảng alarm trống. Ảnh cho thấy trục độ ẩm ghi nhầm °C dù legend ghi %. Đã sửa generator và JSON cục bộ; cần áp dụng bản mới trên tài khoản. Ảnh nằm trong cuộc trò chuyện, chưa có file ảnh/export trong repository.

### Hướng dẫn khởi tạo bản RPC trước đây

1. Giữ terminal gateway cổng 8081 đang chạy. Từ trang Dashboards, import `coreiot/smartroom_dashboard_rpc.json`. File này có tên **SmartRoom CO3037 RPC**, giữ dashboard bạn đã tạo để đối chiếu.
2. Mở dashboard mới, kiểm tra alias **SmartRoom sensor** trỏ đúng `room-node-01`. Có hai biểu đồ, hai nút **Bật quạt / Tắt quạt** và bảng alarm. Đơn vị độ ẩm đã sửa thành %, hai biểu đồ dùng chung cửa sổ 10 phút, không lấy trung bình để che đỉnh nóng ngắn.
3. Nhấn **Bật quạt** một lần; đợi phản hồi rồi mở Latest telemetry của child và kiểm tra `fan=true`. Trong dashboard local <http://127.0.0.1:8081>, lệnh mới phải chuyển `pending → applied`.
4. Nhấn **Tắt quạt**, kiểm tra `fan=false` và một lệnh applied mới. Lần thử này là RPC CoreIOT ↔ gateway ↔ node mô phỏng; chưa phải điều khiển quạt phần cứng.
5. Nếu báo thiếu widget **RPC Button**, dùng **Edit mode → Add widget → Control widgets → RPC Button**. Target là `room-node-01`, method `setFan`, params `true`/`false` (boolean), tắt **Is one way command**, timeout 10000 ms, bật hiển thị lỗi. Hướng dẫn RPC Button: <https://thingsboard.io/iot-hub/widgets/rpc-button/>.

Bản RPC đã được người dùng xác nhận chạy; các lệnh có RPC ID đã xuất hiện ở trạng thái applied trong gateway. Các bước import ở phần này chỉ dành cho khởi tạo, không cần lặp lại với dashboard hiện tại. Dùng luồng cập nhật tại chỗ ở đầu tài liệu. Bảng alarm chưa có dòng là bình thường trước khi gắn RuleChain.

## Bắt đầu ngay trên tài khoản của bạn

Trang của lớp: <https://app.coreiot.io/home>. Bạn chưa cần tạo cảm biến, dashboard hay RuleChain trước.

1. Đăng nhập, chọn **Entities → Devices** ở menu trái.
2. Nhấn **+ → Add new device** (hoặc **Add device**). Điền **Name** là `smartroom-pc-gateway`. Giữ Device profile mặc định cho lần thử đầu, bật **Is gateway**, rồi nhấn **Add**. Nếu không thấy ô gateway trong hộp tạo, mở thiết bị vừa thêm → chỉnh sửa chi tiết để bật **Is gateway** và Save.
3. Mở `smartroom-pc-gateway` → **Manage credentials**; chọn loại **Access token** nếu cần và copy token. Có phiên bản đặt nút **Copy access token** ngay trong chi tiết thiết bị. Giữ token trên máy bạn; không gửi trong cuộc trò chuyện.
4. Mở terminal VS Code ở gốc dự án và chạy `python scripts/start_coreiot.py`. Nếu bạn dùng môi trường ảo của README, chạy `.venv\Scripts\python scripts/start_coreiot.py`. Dán token khi chương trình hỏi; ký tự sẽ không hiện. Script dùng cổng dashboard **8081** để không trùng demo local 8080.
5. Mở <http://127.0.0.1:8081>. Quay lại **Entities → Devices**, tìm child **`room-node-01`**, mở tab **Latest telemetry**. Sau khoảng vài giây phải có `temperature`, `humidity`, `fan`, `seq` và `data_source=simulation`. Khi chưa thấy, đợi tải lại danh sách và kiểm tra gateway đã bật Is gateway.

Script tự tạo `runtime/coreiot_config.json`, không lưu token. Mặc định chạy mô phỏng và gửi dữ liệu sinh lên tài khoản của bạn; dùng database riêng `runtime/coreiot_simulation.sqlite3` để không phát lại lịch sử demo local trước đó. **Không cần tạo child bằng tay trong lần thử đầu**: gateway gửi connect để CoreIOT tạo/đăng ký child. Nếu server báo không đủ quyền, ghi lại thông báo để xử lý quyền hoặc tạo child theo chính sách của lớp.

Theo [tài liệu kết nối chính thức CoreIOT](https://coreiot.io/docs/ket-noi-va-gui-du-lieu/), MQTT dùng hostname **`app.coreiot.io`**, cổng **1883**. Profile riêng `gateway/config.coreiot.example.json` đặt `mqtt_tls=false`; kênh MQTT này không mã hóa. Kiểm tra endpoint tại máy ngày 18/11/2026: TCP 1883 truy cập được, TCP 8883 bị từ chối. Sau đó người dùng đã xác nhận nhận telemetry trên CoreIOT; chưa xác minh RPC và các tính năng cloud còn lại. Nếu quản trị lớp cấp endpoint TLS, cập nhật hostname/cổng/TLS trong cấu hình runtime tương ứng.

Sau khi child có telemetry, mới làm các mục dashboard, RPC và RuleChain bên dưới. Khi có board, sửa `serial_port` trong runtime config rồi chạy `python scripts/start_coreiot.py --hardware`.

Dashboard và các nút RPC đã được người dùng xác nhận chạy. Switch cập nhật tại chỗ và RuleChain còn cần xác minh trên tài khoản.
Gateway dùng MQTT Gateway API theo tài liệu ThingsBoard; telemetry và RPC mô phỏng đã chạy trên CoreIOT.
Không cần gửi mật khẩu đăng nhập hay token cho người khác. Bạn tự nhập token vào terminal trên máy mình.

## 1. Tạo gateway và child device — T08, T15

1. Đăng nhập <https://app.coreiot.io/home>. Mở **Entities → Devices** (tên menu có thể khác theo phiên bản).
2. Tạo thiết bị `smartroom-pc-gateway`, bật **Is gateway**. Nếu có lựa chọn **Overwrite activity time**, giữ thiết lập mặc định của lớp.
3. Lấy **Access token của gateway**, không phải token child device.
4. Với `app.coreiot.io`, dùng profile `gateway/config.coreiot.example.json` hoặc script bắt đầu ở trên. Nếu tự cấu hình, copy profile này thành `runtime/config.json`: `mqtt_host=app.coreiot.io`, `mqtt_port=1883`, `mqtt_tls=false`. Hostname không có `https://` hoặc `/home`. `gateway/config.example.json` là profile chung cho endpoint TLS, không phải cấu hình đã xác minh của server này.
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
2. Mở Entity aliases, kiểm tra alias `SmartRoom sensor` tìm được **room-node-01**. File dùng filter `entityName` cho loại `DEVICE` theo schema ThingsBoard. Nếu phiên bản CoreIOT không tự resolve, chọn **Single entity → Device → room-node-01** rồi Save.
3. Kiểm tra hai biểu đồ và alarm table. Nếu thiếu widget `system.time_series_chart` ở phiên bản cũ, thêm widget Time series chart có sẵn và gắn hai key tương ứng. Đây là bước tương thích cần xác minh trên CoreIOT thực tế.
4. Thêm widget **Control → RPC button/switch**. Chọn child `room-node-01`, method `setFan`, params **boolean** `true`/`false`, two-way RPC, timeout 10000 ms. Không truyền chuỗi `"true"` hay object `{value:true}`.
5. Với Switch Control, chọn lấy trạng thái **Time series → fan**, method gửi `setFan`, convert `return value === true;`. Không chọn lấy trạng thái bằng RPC `getValue`. Luồng cập nhật tại chỗ cấu hình sẵn các trường này.
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
