# HƯỚNG DẪN BẢO VỆ ĐỒ ÁN VÀ VẬN HÀNH DEMO VIETIRR-RAG (FINAL RELEASE HANDOVER)
**Ngày cập nhật:** 30/10/2026  
**Hạn bảo vệ đồ án tốt nghiệp:** 02/11/2026  
**Trạng thái hệ thống:** `WEBSITE_SYNCED_DEMO_READY` (ĐỒNG BỘ NỘI DUNG, BỘ CÂU HỎI THỬ NGHIỆM ĐÃ XÁC MINH, SẴN SÀNG DEMO HỘI ĐỒNG)

---

## 1. Khởi Động Nhanh Cho Buổi Bảo Vệ Đồ Án (Quick Start Live Demo)

### Bước 1: Khởi động Ollama Model (Local GPU)
```bash
ollama serve
# Kiểm tra model qwen2.5:7b sẵn sàng:
ollama run qwen2.5:7b "Xin chào"
```

### Bước 2: Khởi động Backend API (Cổng 8000)
```bash
cd d:\Thuy_Loi\Nam_4\deep_learning\thuyloi_rag
.venv_b2\Scripts\python.exe -m uvicorn viirr_api.app:app --host 127.0.0.1 --port 8000
```
Kiểm tra: Truy cập `http://127.0.0.1:8000/api/v1/health` -> Trả về `{"status":"ready", "corpus_version":"V4_R6_FROZEN", "r6": {"initialized": true}}`.

### Bước 3: Khởi động Frontend Web (Cổng 5173)
```bash
cd d:\Thuy_Loi\Nam_4\deep_learning\thuyloi_rag\frontend
npm run dev
```
Truy cập: `http://localhost:5173` trên trình duyệt Chrome/Edge.

---

## 2. Các Kịch Bản Demo Trực Tiếp Trên Web (Live Demo Scenarios)

Người dùng hoặc Hội đồng có thể sử dụng ngay **bộ câu hỏi thử nghiệm** ở sidebar bên trái giao diện:

### Kịch bản 1 — Tra cứu số liệu đơn lẻ & Mở PDF chứng minh đúng trang 56:
- Chọn tab **"Số liệu"** -> Click câu hỏi:  
  > *"Theo báo cáo Nam Măng Thít năm 2024, cao trình đáy của cống Hàm Giang là bao nhiêu mét?"*
- Bấm **"Tra cứu ngay ↗"**.
- **Kết quả:**
  - Câu trả lời: *"Theo báo cáo Nam Măng Thít năm 2024, cao trình đáy của cống Hàm Giang là -2,0 m."*
  - Citation Card: `IRR_CTL_2024_9a520097` — Trang 56.
  - Bấm vào trích dẫn: Trình xem PDF nhúng mở tức thì Trang 56, hiển thị đúng dòng số liệu cống Hàm Giang.

### Kịch bản 2 — Tra cứu lượng mưa trạm quan trắc (Bản tin dự báo nguồn nước):
- Chọn tab **"Số liệu"** -> Click câu hỏi:  
  > *"Theo Bản tin dự báo nguồn nước Lưu vực sông Hoàng Long (Từ 01/6 đến 30/6/2019), lượng mưa trong tháng 5, từ 1/5 đến 28/5/2019 của NINH BÌNH được ghi nhận là bao nhiêu?"*
- Bấm **"Tra cứu ngay ↗"**.
- **Kết quả:** Trích xuất chính xác 239 mm (đạt 139% so với TBNN), trích dẫn tài liệu `IRR_CTL_2019_1fc21515`, trang 1.

### Kịch bản 3 — Tra cứu kép đa công trình (Bắc Trang & Bông Bót):
- Chọn tab **"So sánh"** -> Click câu hỏi:  
  > *"Theo báo cáo Nam Măng Thít năm 2024, cao trình đáy của cống Bắc Trang và cống Bông Bót lần lượt là bao nhiêu?"*
- Bấm **"Tra cứu ngay ↗"**.
- **Kết quả:** Trả về đầy đủ cả 2 giá trị (-3,0 m cho Bắc Trang và -3,0 m cho Bông Bót) với 2 citations độc lập tại trang 56.

### Kịch bản 4 — Kiểm tra giới hạn hệ thống & Từ chối an toàn (Fail-closed):
- Chọn tab **"Giới hạn"** -> Click câu hỏi:  
  > *"Cao trình mực nước chết và dung tích hữu ích của hồ Bản Chát là bao nhiêu?"*
- Bấm **"Tra cứu ngay ↗"**.
- **Kết quả:** Hệ thống từ chối lịch sự, nêu rõ hồ Bản Chát không có trong dữ liệu tài liệu hiện hành, không bịa đặt số liệu ảo.

---

## 3. Trình Chiếu Báo Cáo Khoa Học & Chế Độ Hội Đồng (16:9)

1. **Truy cập Báo cáo Khoa học:** Click vào mục **"Báo cáo Khoa học"** trên Navigation header hoặc truy cập `/presentation`.
2. **Kiểm tra số liệu:**
   - Dải thông tin đầu trang: 93 PDF · 2.578 trang · 27.144 đơn vị bằng chứng · V4_R6_FROZEN.
   - Mục 08 Thực nghiệm: Click tab **"R6 Frozen Pipeline"** để xem bảng số liệu Hit@100 (91.40%), Page Hit@5 (67.74%), Evidence Page Hit@5 (61.29%).
3. **Chế độ Báo cáo Hội đồng:** Bấm nút **"Chế độ Báo cáo Hội đồng (16:9)"** ở góc trên cùng bên phải để chuyển sang chế độ trình chiếu fullscreen chuẩn tỷ lệ 16:9.

---

## 4. Lệnh Kiểm Thử Nghiệm Thu Tự Động
```bash
cd d:\Thuy_Loi\Nam_4\deep_learning\thuyloi_rag

# Chạy toàn bộ 82 unit & regression tests:
.venv_b2\Scripts\pytest.exe tests/ -v

# Kiểm tra build frontend:
cd frontend && npm run build
```
