# VietIrr-RAG

Hệ thống Truy xuất và Hỏi đáp Định vị Bằng chứng cho Tài liệu Thủy lợi Tiếng Việt

---

## Tổng quan Dự án

VietIrr-RAG là hệ thống hỏi đáp có căn cứ (Retrieval-Augmented Generation - RAG) được thiết kế chuyên biệt cho tài liệu kỹ thuật công trình thủy lợi và tài nguyên nước tại Việt Nam.

### Thách thức Kỹ thuật
1. **Định dạng Tài liệu Phức tạp**: Hồ sơ kỹ thuật thủy lợi thường dài hàng chục đến hàng trăm trang, chứa nhiều bản đồ, bảng ma trận cao trình - dung tích và quy trình vận hành liên hồ chứa.
2. **Yêu cầu Độ chính xác Số liệu Tuyệt đối**: Các thông số như cao trình mực nước chết (MNC), mực nước dâng bình thường (MNDBT), mực nước lũ kiểm tra (MNLKT) đòi hỏi sự chính xác tuyệt đối; sai số hoặc suy diễn sai lệch có thể dẫn đến nguy cơ mất an toàn công trình.
3. **Định vị Bằng chứng Phân cấp**: Truy xuất đoạn văn bản thông thường dễ làm mất ngữ cảnh của bảng biểu hoặc trang gốc. Hệ thống cần định vị chính xác từ cấp tài liệu, trang tài liệu đến từng khối văn bản hoặc ô bảng dữ liệu (`Page-to-Region`).

---

## Kiến trúc Hệ thống

Quy trình xử lý của VietIrr-RAG phân định rõ hai giai đoạn:

### 1. Tiền xử lý và Đánh chỉ mục (Offline)
- Trích xuất cấu trúc PDF: Phân tách khối văn bản và ma trận bảng biểu bằng bộ bóc tách bố cục chuyên dụng.
- Đánh chỉ mục hỗn hợp:
  - Chỉ mục từ vựng (BM25) với bộ tách từ tối ưu hóa cho thuật ngữ thủy lợi tiếng Việt.
  - Chỉ mục ngữ nghĩa mật độ cao sử dụng mô hình nhúng BGE-M3 (vector 1024 chiều).

### 2. Truy xuất và Sinh phản hồi (Online)
- **Truy xuất Hỗn hợp (Hybrid Retrieval)**: Kết hợp kết quả từ BM25 và BGE-M3 thông qua thuật toán Hợp nhất Thứ hạng Nghịch đảo (Reciprocal Rank Fusion - RRF, tham số k=60).
- **Tái xếp hạng (Cross-Encoder Reranking)**: Sử dụng mô hình `BGE-Reranker-0.6B` để tính toán tương quan sâu giữa câu hỏi và danh sách ứng viên hàng đầu.
- **Định vị Phân cấp (Hierarchical Page-to-Region)**: Lọc các trang có mật độ thông tin cao nhất, sau đó định vị chính xác vùng văn bản (`TEXT_REGION`) hoặc vùng bảng (`TABLE_REGION`).
- **Sinh phản hồi Cục bộ**: Sử dụng mô hình ngôn ngữ lớn nguồn mở cục bộ (`Qwen2.5:7B`) với prompt ràng buộc dữ kiện thực tế.
- **Kiểm soát Trích dẫn (Citation Guard)**: Ràng buộc mọi khẳng định trong câu trả lời phải kèm mã định danh bằng chứng hợp lệ (`REG_...` hoặc `TAB_...`), tự động từ chối trả lời nếu thiếu căn cứ xác thực.
- **Giám sát Bản thể học (Ontology Shadow Mode)**: Trích xuất các khẳng định kỹ thuật nguyên tử, kiểm tra đối sánh với 45 ràng buộc thủy lực trong chế độ chạy ngầm (Shadow Mode) phục vụ đo lường và cảnh báo.

---

## Tập Dữ liệu và Đánh giá Thực nghiệm

### Thống kê Tập Dữ liệu V4
- **Số lượng tài liệu**: 93 báo cáo và quy trình vận hành thủy lợi
- **Tổng số trang**: 2.578 trang
- **Số đơn vị bằng chứng**: 27.144 đơn vị (27.053 vùng văn bản và 91 vùng bảng biểu)
- **Repository dữ liệu chính thức**: [https://github.com/zudoan/vietirr-rag-dataset](https://github.com/zudoan/vietirr-rag-dataset)

### Kết quả Đánh giá Truy xuất (Tập DEV-93)

Các chỉ số dưới đây được xác minh trực tiếp từ artifact đóng băng `reports/EXPERIMENTS/R6_RETRIEVAL_DEV93_METRICS.json`:

| Chỉ số Đánh giá | Baseline R5 | Pipeline R6 | Chênh lệch |
| :--- | :---: | :---: | :---: |
| **Candidate Hit@100** | 76,34% (71/93) | **91,40% (85/93)** | +15,06% |
| **Page Hit@5** | 63,44% (59/93) | **67,74% (63/93)** | +4,30% |
| **Evidence Page Hit@5** | 58,06% (54/93) | **61,29% (57/93)** | +3,23% |
| **MRR@5** | 0,4579 | **0,4511** | -0,0068 |
| **nDCG@5** | 0,4894 | **0,5077** | +0,0183 |
| **Khôi phục Vùng Bảng** | 0,00% (0/93) | **17,20% (16/93)** | +17,20% |
| **Độ trễ trung vị (p50)** | 4.505 ms | **4.401 ms** | -104 ms |

*Lưu ý khoa học*: Hit@K đo lường khả năng tìm kiếm được đúng bằng chứng nguồn trong tập ứng viên; chỉ số này không đồng nghĩa với độ chính xác của câu trả lời cuối cùng. Độ chính xác sinh câu trả lời end-to-end cần được đánh giá độc lập trên bộ tiêu chí toàn diện.

---

## Hướng dẫn Khởi chạy Nhanh

### Yêu cầu Tiên quyết
- Python 3.10 hoặc 3.11
- Node.js 20.x trở lên
- Ollama phục vụ mô hình `qwen2.5:7b`

### 1. Khởi chạy Mô hình Ngôn ngữ Cục bộ
```bash
ollama run qwen2.5:7b
```

### 2. Cài đặt và Khởi chạy Backend FastAPI
```bash
python -m venv .venv
# Trên Windows PowerShell:
.venv\Scripts\Activate.ps1
# Trên Linux/macOS:
source .venv/bin/activate

pip install -e .
uvicorn viirr_api.app:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Cài đặt và Khởi chạy Frontend React/Vite
```bash
cd frontend
npm install
npm run dev
```

Truy cập giao diện nghiên cứu tại `http://127.0.0.1:5173`.

---

## Cấu trúc Tài liệu Chi tiết
- [Kiến trúc Toàn diện (Tiếng Anh)](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/docs/ARCHITECTURE.md)
- [Quy trình Truy xuất R6 (Tiếng Anh)](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/docs/RETRIEVAL_PIPELINE.md)
- [Giám sát Bản thể học (Tiếng Anh)](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/docs/ONTOLOGY_VERIFICATION.md)
- [Nghi thức Đánh giá Thực nghiệm (Tiếng Anh)](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/docs/EVALUATION.md)
- [Chính sách và Nguồn Dữ liệu (Tiếng Anh)](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/docs/DATA_AVAILABILITY.md)
- [Lịch sử Nghiên cứu (Tiếng Anh)](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/docs/RESEARCH_HISTORY.md)
