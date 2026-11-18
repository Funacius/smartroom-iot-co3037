# Minh chứng CoreIOT thực đã kiểm tra

| Tệp | Nội dung |
|---|---|
| `SmartRoom_Dashboard.png` | Hai biểu đồ, switch Fan, độ ẩm %, lịch sử alarm Cleared |
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

Điểm cần chỉnh trên dashboard hiện tại: cả hai biểu đồ đang AVG mỗi 30 giây, cửa sổ riêng 1 giờ. Chọn Aggregation=None để hiển thị các đỉnh dữ liệu gốc; có thể dùng chung time window của dashboard. Sau khi sửa, export lại để cập nhật minh chứng. Không sửa JSON export gốc để giả như thay đổi đã có trên cloud.

Export dashboard không chứa runtime ID; không suy ra URL đang dùng từ tên. Cờ `root=false` và ID child chain trong export cũng không được tự ý dùng để thay đổi tài khoản đang hoạt động. Notification hiện đã hoạt động, không cần tạo rule trùng lặp.
