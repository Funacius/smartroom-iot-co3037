# Minh chứng CoreIOT thực đã kiểm tra

Cập nhật 26/11: ảnh mới nằm ở `SmartRoom_Dashboard_20261126.png`, JSON mới ở `smartroom_dashboard_20261126.json`. `dashboard_ai_user_check.json` ghi quan sát, kích thước, SHA-256 và phạm vi kiểm chứng. `../coreiot_dashboard_ai_check.json` có 15/15 kiểm tra cấu hình đạt: 9 widget, chart NONE, trạng thái AI và RPC đúng. Ảnh/export gốc ngày 18/11 được giữ nguyên.

| Tệp | Nội dung |
|---|---|
| `SmartRoom_Dashboard.png` | Hai biểu đồ, switch Fan, độ ẩm %, lịch sử alarm Cleared |
| `SmartRoom_Dashboard_20261126.png` | Ảnh mới: hai biểu đồ, Alarms, Fan và năm thẻ AI/nguồn dữ liệu |
| `smartroom_dashboard_20261126.json` | Export mới 9 widget; chart NONE; Anomaly dùng compareToValue=false, On=Normal, Off=Anomaly |
| `Rule_chains_root.png` | Root lọc room-node-01 và giữ đường RPC |
| `Rule_chains_SmartRoom_alarms.png` | Chuỗi lưu telemetry, tạo alarm và clear có hysteresis |
| `Notification.png` | Web notification New alarm và Alarm cleared |
| `smartroom_co3037.json` | Export dashboard: 2 biểu đồ, bảng alarm và Single Switch |
| `root_rule_chain.json` | Export Root đã nối nhánh SmartRoom |
| `smartroom_alarms.json` | Export child chain tạo/xóa alarm |

Đây là minh chứng cloud với nguồn cảm biến `simulation`, không phải ảnh hoặc số đo phần cứng. Các tệp được giữ nguyên và nhúng vào báo cáo; SHA-256, kiểm tra đồ thị/cấu hình và các trường hợp JavaScript nằm ở `../coreiot_export_check.json`.

Chạy lại kiểm tra tại gốc dự án với Python theo requirements và Node.js (dùng để chạy các script filter export):

```powershell
python scripts/check_coreiot_exports.py
```

Phát hiện AVG 30 giây thuộc bản export cũ ngày 18/11. Bản ngày 26/11 đã xác nhận NONE trên cả hai biểu đồ; cửa sổ 1 giờ vẫn riêng cho từng widget. Các Value card có type latest, đọc giá trị gần nhất; trường timewindow AVG mặc định còn trong JSON của các card này không phải aggregation của biểu đồ.

Export dashboard không chứa runtime ID; không suy ra URL đang dùng từ tên. Cờ `root=false` và ID child chain trong export cũng không được tự ý dùng để thay đổi tài khoản đang hoạt động. Notification hiện đã hoạt động, không cần tạo rule trùng lặp.
