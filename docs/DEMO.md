# Kịch bản demo SmartRoom (7–9 phút)

Không quay màn hình mô phỏng và gọi đó là thiết bị thật. Dữ liệu phần mềm có nhãn `simulation`.

| Thời gian dự kiến | Thao tác | Mục liên quan | Minh chứng cần lưu |
|---|---|---|---|
| 0:00–0:45 | Giới thiệu 2 YoloUNO, DHT20, quạt qua module driver và máy tính | Kiến trúc | Toàn cảnh mạch thật |
| 0:45–1:45 | Cho thấy MAC hai node, cùng channel, tăng `seq`, dữ liệu Serial | T06 | Log gửi/nhận và ảnh dây nối |
| 1:45–2:30 | Kết nối AP bridge, mở 192.168.4.1, xem dữ liệu và gửi yêu cầu quạt khi PC đang chạy | T07 | Quay web trên ESP32 và quạt thật |
| 2:30–3:30 | Dashboard PC, bật/tắt quạt, chỉ ra pending → applied sau ACK | T08, T10 | CSV sự kiện và log ACK |
| 3:30–4:15 | Đưa vào tình huống nhiệt độ cao có kiểm soát, xem anomaly và score | T09 | Nêu rõ model đang train dữ liệu sinh hay dữ liệu thực |
| 4:15–5:15 | CoreIOT hiện child device, telemetry đúng tên, dashboard template và RPC setFan | T11, T15 | Ảnh gateway/child và phản hồi RPC |
| 5:15–6:15 | RuleChain tạo/xóa alarm, nhận thông báo in-app/email | T12, T13 | RuleChain, alarm và thông báo thực nhận |
| 6:15–7:00 | Ngắt mạng cloud, dữ liệu chờ tăng; nối lại, outbox giảm | T08 | Log/CSV trước-sau |
| 7:00–8:00 | Ngắt sensor, trạng thái stale; gửi lệnh không có ACK phải failed | N06 | Dashboard và nhật ký SQLite |
| 8:00–9:00 | Mở báo cáo, kết quả đo, phân công và khai báo AI | Báo cáo | Bảng tự đánh giá đã cập nhật bằng chứng |

Điền timestamp **thực tế** sau khi quay; các mốc trên chỉ là dự kiến.
Chạy `python scripts/record_hardware.py --seconds 300 --output evidence/hardware/session.jsonl`
trong lúc gateway phần cứng đang chạy để lưu dữ liệu nhận thật.

## Câu hỏi bảo vệ

1. Vì sao cảm biến I2C trên Arduino không được nhận T01? Vì T01 yêu cầu I2C **trên Tasmota**.
2. Vì sao gửi MQTT thành công không có nghĩa quạt đã quay? PUBACK chỉ xác nhận broker nhận; cần ACK từ node. ACK GPIO cũng chưa đo tốc độ quạt.
3. Mất ACK có chắc quạt chưa bật? Không. Lệnh có thể đã thực thi; hệ thống ghi trạng thái vật lý chưa rõ.
4. Mô hình AI khác luật 32 °C như thế nào? Isolation Forest học phân bố hai biến; luật ngưỡng là cơ chế xác định độc lập.
5. Accuracy trên dữ liệu sinh có chứng minh triển khai thực tế? Không. Cần dữ liệu thật và tập kiểm thử theo thời gian/phòng khác.
6. Vì sao QoS 1 vẫn có dữ liệu lặp? Khi broker đã nhận nhưng gateway chưa xóa outbox và khởi động lại, bản tin được gửi lại.
7. Vì sao quạt tự tắt sau 30 giây? Firmware giới hạn thời gian lệnh thủ công; lease tránh để lệnh cũ duy trì vô hạn.
8. Xóa DB gateway có ảnh hưởng gì? ID lệnh quay về đầu, còn node giữ ID trong NVS; cần sao lưu DB hoặc reset NVS có chủ ý khi bắt đầu triển khai mới.
