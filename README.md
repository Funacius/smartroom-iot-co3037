# SmartRoom — Đồ án Internet of Things (CO3037)

Giám sát nhiệt độ/độ ẩm phòng học, phát hiện bất thường trên máy tính và điều khiển quạt có xác nhận từ node.

[Báo cáo PDF](report/CO3037_CHUA_CAP_MA_NHOM_IoTReport.pdf) · [Nguồn LaTeX](report/main.tex) · [Hướng dẫn CoreIOT](coreiot/README.md) · [Kịch bản demo](docs/DEMO.md)

Dashboard đã có: [mở dashboard hiện tại](https://app.coreiot.io/dashboards/all/0ca724e0-e352-11f1-8cd8-29dc599bec29). Để thay hai nút bằng switch và giữ nguyên dashboard, xem [cập nhật tại chỗ](coreiot/UPDATE_EXISTING.md); không cần import thêm dashboard.

**Nhóm:** Bùi Quốc Thái — 2353086 — thai.bui1569@hcmut.edu.vn; Nguyễn Vinh Anh Quân — 2353007 — quan.nguyenvinhanh@hcmut.edu.vn.
**Giảng viên:** TS. Nguyễn Hòa Hưng. **Mã nhóm:** chưa được cấp.

Kiến trúc: `DHT20 + YoloUNO sensor/actuator ↔ ESP-NOW ↔ YoloUNO bridge ↔ USB Serial ↔ PC gateway ↔ MQTT/TLS ↔ CoreIOT`.
Máy tính có dashboard riêng tại `http://127.0.0.1:8080`; bridge có web server tại `http://192.168.4.1` khi kết nối Wi-Fi AP của bridge.

## Trạng thái thực tế

- Firmware `sensor` và `bridge` đã build trên PlatformIO; chưa nạp lên board trong phiên làm việc này.
- Gateway, HTTP dashboard, journal, xử lý lệnh/ACK, outbox và adapter CoreIOT đã kiểm thử tự động. Xem `evidence/pytest.xml` và `evidence/verification.json`.
- AI Isolation Forest được train và đánh giá trên **dữ liệu sinh**, không phải số đo phòng học. Metrics/CSV có nguồn dữ liệu rõ ràng.
- Đã nhận và kiểm tra 4 ảnh cùng 3 JSON export thực trong `evidence/coreiot/`: dashboard/switch, Root/child RuleChain và Web notification tạo/xóa alarm. Switch dùng telemetry `fan`, RPC `setFan` với boolean đúng; độ ẩm đã có đơn vị %. Còn cần đổi AVG 30 giây thành None trên hai biểu đồ để không làm thấp đỉnh nóng, rồi kiểm thử phần cứng. Xem `evidence/coreiot_export_check.json` và báo cáo đã nhúng ảnh.
- PDF bám mẫu Word, đủ sáu chương; phần chưa kiểm chứng được ghi rõ. Cần mã nhóm, video và ảnh/đo thực tế trước khi nộp.

## Chạy thử nhanh trên Windows

Mở PowerShell tại gốc repository:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python ai/train.py
.venv\Scripts\python -m gateway.main --simulate
```

Mở <http://127.0.0.1:8080>. Chu kỳ giả lập 60 giây: bình thường 20 giây → nóng 20 giây → hồi phục 20 giây. Bật/tắt quạt sẽ đi qua trạng thái pending rồi applied với ACK mô phỏng. Nhấn Ctrl+C để dừng.
Không bật `--cloud` thì không gửi gì tới CoreIOT; outbox sẽ tăng. Simulation dùng riêng `runtime/simulation.sqlite3`.

## Phần cứng và firmware

| Thành phần | Số lượng | Chức năng |
|---|---:|---|
| YoloUNO ESP32-S3 | 2 | Sensor/actuator + bridge |
| DHT20 I2C | 1 | Nhiệt độ/độ ẩm |
| Quạt DC thấp áp + module driver tương thích logic 3,3 V | 1 bộ | Điều khiển qua GPIO, không cấp quạt trực tiếp từ GPIO |
| Cáp USB dữ liệu | 2 | Nạp/chạy và kết nối bridge |
| PC/laptop có Internet | 1 | Gateway Python |

Chân **đề xuất cần đối chiếu board thật**: SDA GPIO11, SCL GPIO12, driver input GPIO6. GPIO thô khác nhãn Dx trên board.
DHT20 gắn cổng I2C của YoloUNO theo tài liệu OhStem; đảm bảo I2C pull-up ở 3,3 V, nguồn và mass chung theo module.
Board definition trong dự án dùng flash 4 MB, DIO và không dùng PSRAM để tránh phụ thuộc các mô tả dung lượng khác nhau của YoloUNO; xác minh revision trước khi flash.

1. VS Code đã có PlatformIO. Cài CLI nếu máy khác chưa có: `python -m pip install platformio==6.2.0`.
2. Copy `firmware/include/config.example.h` thành `config.local.h`.
3. Build và nạp từng role; đọc dòng `STA MAC` của mỗi board. Khi mới khởi động, cấu hình MAC mẫu chưa giao tiếp được.
4. Với mỗi board, điền `PEER_MAC` của **board còn lại**, cùng channel và cùng khóa ngẫu nhiên 16 byte. Mỗi lần đổi role/MAC phải build và nạp lại đúng role. Lưu hai bản cấu hình riêng ngoài Git nếu cần.

```powershell
pio run -d firmware
pio run -d firmware -e sensor -t upload --upload-port COM5
pio device monitor --port COM5 --baud 115200
pio run -d firmware -e bridge -t upload --upload-port COM6
```

5. Copy `gateway/config.example.json` thành `runtime/config.json`, sửa `serial_port` đúng cổng bridge. Tắt Serial Monitor trên cổng bridge trước khi chạy gateway.
6. Chạy `.venv\Scripts\python -m gateway.main --config runtime/config.json`.
7. Đổi password AP và Basic Auth trong cấu hình firmware. Vào Wi-Fi `SmartRoom-Bridge`, mở `192.168.4.1`; yêu cầu điều khiển từ web bridge cần PC gateway đang chạy.

Quạt mặc định tắt; lệnh bật có lease 30 giây rồi tự tắt; cảm biến lỗi cũng đưa đầu ra về tắt. Đây là mô hình học tập, chưa có cảm biến tốc độ để xác nhận quạt thực sự quay.
Giữ DB gateway để ID lệnh không quay về đầu trong khi node lưu ID cũ ở NVS. Nếu bắt đầu một đợt triển khai mới và xóa DB, phải chủ ý đồng bộ/reset NVS node.

## CoreIOT

Server của lớp: <https://app.coreiot.io/home>. Nếu chưa tạo gì, mở [hướng dẫn bắt đầu từ đầu](coreiot/README.md#bắt-đầu-ngay-trên-tài-khoản-của-bạn): tạo `smartroom-pc-gateway`, bật **Is gateway**, lấy token rồi chạy:

```powershell
python scripts/start_coreiot.py
```

Chương trình hỏi token kín, không lưu token; dùng profile `app.coreiot.io:1883` không TLS theo tài liệu CoreIOT và chạy dashboard mô phỏng tại <http://127.0.0.1:8081>. Child `room-node-01` được đăng ký khi kết nối; kiểm tra Latest telemetry trước khi import dashboard. Khi có board và đã sửa cổng Serial trong `runtime/coreiot_config.json`, chạy `python scripts/start_coreiot.py --hardware`.

Làm theo [coreiot/README.md](coreiot/README.md): tạo gateway, nhập token kín bằng `Read-Host`, đặt hostname/cổng, chạy `--cloud`, import dashboard, gắn RuleChain, tạo Notification rule và chụp bằng chứng.

RPC method `setFan`, params boolean `true` hoặc `false`. Không dùng chuỗi. TTL lệnh 5 giây; chỉ trả thành công sau ACK node. Khi timeout, trạng thái vật lý **chưa rõ**, không được kết luận chắc chắn quạt chưa bật.
CoreIOT adapter dùng API ThingsBoard chuẩn; cần kiểm chứng tương thích trên server lớp.

## Kiểm thử, đánh giá và dựng báo cáo

```powershell
.venv\Scripts\python -m pytest -q --junitxml=evidence/pytest.xml
.venv\Scripts\python scripts/evaluate.py
.venv\Scripts\python scripts/verify.py --firmware
.venv\Scripts\python scripts/build_report.py
```

XeLaTeX cần MiKTeX hoặc TeX Live và các font Times New Roman, Arial, Consolas. `report/metadata.json` chứa thông tin nhóm/link.
File xuất hiện tại `report/CO3037_CHUA_CAP_MA_NHOM_IoTReport.pdf` khi chưa có mã nhóm; sau khi điền mã nhóm, build script đặt lại tên theo quy định.
Tất cả lệnh chạy ở **gốc repository**. Log và số đo gốc ở `evidence/`. `scripts/evaluate.py` đo xử lý SQLite trên PC, không đo độ trễ sensor→cloud.
Muốn train với dữ liệu thực: `.venv\Scripts\python ai/train.py --csv duong_dan.csv`; cột `temperature,humidity,label`, label=0 bình thường/1 bất thường, sắp xếp thời gian. 60% đầu dùng lấy mẫu normal train, 40% cuối test. Không tự gắn nhãn bằng ngưỡng rồi dùng accuracy đó để chứng minh AI vượt luật ngưỡng.

Thu thập từ phần cứng: `python scripts/record_hardware.py --seconds 300`; script từ chối lưu simulation làm minh chứng phần cứng.
Kịch bản demo và câu hỏi bảo vệ: [docs/DEMO.md](docs/DEMO.md).

## Bám tiêu chí chấm điểm

| Mã | Điểm tối đa | Nội dung chuẩn bị | Tình trạng cần lưu ý |
|---|---:|---|---|
| T06 | 1,5 | ESP-NOW unicast mã hóa, packet và ACK | Build đạt; cần thử hai board |
| T07 | 1 | Web server trên bridge | Build đạt; cần ảnh web/điều khiển board |
| T08 | 1 | Gateway hai chiều, lưu bền, ACK | Telemetry cloud được xác nhận; cần USB thật và RPC từ cloud |
| T09 | 1 | Isolation Forest trên gateway | Đã chạy với dữ liệu sinh; cần train/đánh giá thực |
| T10 | 1 | Giao diện giám sát/điều khiển PC | Đã chạy local |
| T11 | 1 | Template dashboard CoreIOT | Có ảnh/export; switch và đơn vị đúng, còn chỉnh AVG 30 giây |
| T12 | 1 | RuleChain cảnh báo với hysteresis | Ảnh alarm Major và thông báo tạo/xóa đã nhận trên CoreIOT |
| T13 | 0,5 | Notification khi tạo alarm | Có ảnh Web notification tạo/xóa cho room-node-01 |
| T15 | 2 | Child synchronization qua Gateway API | Latest telemetry đã được xác nhận; cần ảnh gateway-child và thử RPC |
| N06 | 1 | Dashboard riêng phát hiện/ghi sự kiện, CSV | Đã chạy local |

Tổng công nghệ **mục tiêu** 10 điểm trước trần → tối đa 8; báo cáo tối đa 2; bonus tối đa 1; tổng cuối vẫn tối đa 10. **Không phải điểm đã đạt**.
Không claim T01 (I2C không chạy Tasmota), T04/T05 (không TinyML), T14 (không OTA), N07 (không dựng ThingsBoard local).

## Cấu trúc mã nguồn và nguyên lý

```text
firmware/       2 role Arduino C++, packet ESP-NOW 25 byte, config mẫu
gateway/        core xử lý, SQLite, Serial/MQTT, HTTP dashboard
ai/             train.py và model tạo cục bộ
coreiot/        template, dashboard, RuleChain, hướng dẫn CoreIOT
tests/          kiểm thử logic và giao thức ở mức phần mềm
scripts/        đo, kiểm tra, dựng báo cáo, thu thập phần cứng
report/         main.tex, metadata, kết quả PDF
docs/           kịch bản demo, nguồn đề bài/mẫu
evidence/       log build/test, CSV, biểu đồ và screenshot thật từ phần mềm
```

Luồng quan trọng: `Gateway.ingest` kiểm tra dữ liệu → loại trùng `(device,boot,seq)` → AI/ngưỡng → lưu reading + event + outbox trong giao dịch SQLite. `Gateway.flush` chỉ xóa bản tin khi MQTT báo PUBACK; ngữ nghĩa **at least once**, không phải exactly once.
`Gateway.command` tạo pending → `tick` gửi/retry → `ack` kiểm tra ID và giá trị → applied; hết TTL → failed. Không dùng `toggle` nên phát lại không đảo đầu ra ngoài ý muốn.

## Phân công và sử dụng AI

Phân công **đề xuất**, chưa phải xác nhận đóng góp đã hoàn thành: Thái 50% (firmware, ESP-NOW, phần cứng, đo); Quân 50% (gateway, AI, CoreIOT, tổng hợp report). Hai thành viên cùng đọc code và demo.
Mã nguồn, tài liệu và báo cáo được trợ giúp bởi AI trong phiên này. Không tạo commit giả mang tên thành viên thứ hai; mỗi người cần tự thực hiện, kiểm chứng và commit phần đóng góp thực tế trước khi nộp.
Tái sử dụng thư viện Arduino/ESP-IDF, DHT20, ArduinoJson, scikit-learn, Paho và widget template ThingsBoard; ghi nguồn trong báo cáo và `coreiot/templates/PROVENANCE.json`. Gateway/firmware điều phối/dashboard HTML/test/report được viết cho dự án này.
