# Phân tích phân bố và nhóm câu hỏi VietIrrDocBench V3.2

## Phạm vi và nguyên tắc

- Phân tích nội dung trực tiếp **343 TRAIN + 93 DEV = 436 Q&A**.
- Không mở nội dung **109 Candidate Test** đang niêm phong; chỉ dùng aggregate đã có trong manifest/report.
- Tổng frozen benchmark theo thống kê công bố: **545 Q&A**.
- Human-validated trong TRAIN+DEV: **0/436**.
- Nhóm lĩnh vực dưới đây được nối với document inventory; đó là taxonomy audit, không phải nhãn gold do người gán.

## 1. Phân bố split và độ khó

| Split | Tổng | Core | Challenge | Core share | Challenge share |
|---|---:|---:|---:|---:|---:|
| train | 343 | 289 | 54 | 84.3% | 15.7% |
| dev | 93 | 68 | 25 | 73.1% | 26.9% |
| candidate_test | 109 | 21 | 88 | 19.3% | 80.7% |

Candidate Test là một stress-test khác phân phối: challenge, cross-document và table-table cao hơn rất mạnh so với TRAIN/DEV.

| Split | Same page | Cross-page cùng tài liệu | Cross-document | Retrieval multi |
|---|---:|---:|---:|---:|
| train | 332 | 11 | 0 | 11 |
| dev | 68 | 22 | 3 | 25 |
| candidate_test | 45 | 1 | 63 | 88 |

## 2. Nhóm câu hỏi TRAIN+DEV

### Theo loại QA chính thức

| QA type | Số câu | Tỷ lệ |
|---|---:|---:|
| TEXT_ONLY | 244 | 56.0% |
| TABLE_ONLY | 113 | 25.9% |
| TABLE_TO_TABLE_COMPARISON | 43 | 9.9% |
| TABLE_TO_TEXT_EXPLANATION | 16 | 3.7% |
| TABLE_TO_TEXT_FORECAST | 15 | 3.4% |
| SAME_ENTITY_DIFFERENT_TIME | 3 | 0.7% |
| STATE_TO_RECOMMENDATION | 2 | 0.5% |

### Theo modality hiệu dụng

| Modality | Số câu | Tỷ lệ |
|---|---:|---:|
| TEXT_ONLY | 246 | 56.4% |
| TABLE_ONLY | 113 | 25.9% |
| TABLE_TABLE | 46 | 10.6% |
| TEXT_TABLE | 31 | 7.1% |

### Theo chủ đề/lĩnh vực câu hỏi

| Topic | TRAIN | DEV | Tổng | Tỷ lệ |
|---|---:|---:|---:|---:|
| RAINFALL | 40 | 40 | 80 | 18.35% |
| AREA | 54 | 13 | 67 | 15.37% |
| WATER_LEVEL | 55 | 3 | 58 | 13.3% |
| STORAGE | 31 | 24 | 55 | 12.61% |
| WATER_QUALITY | 48 | 3 | 51 | 11.7% |
| WATER_SOURCE | 46 | 5 | 51 | 11.7% |
| SALINITY | 19 | 0 | 19 | 4.36% |
| WATER_SUPPLY | 12 | 2 | 14 | 3.21% |
| DISCHARGE | 9 | 2 | 11 | 2.52% |
| DISASTER_PREVENTION | 8 | 0 | 8 | 1.83% |
| IRRIGATION_AGRICULTURE | 7 | 1 | 8 | 1.83% |
| RESERVOIR_OPERATION | 5 | 0 | 5 | 1.15% |
| DROUGHT_SHORTAGE | 4 | 0 | 4 | 0.92% |
| DAM_SAFETY | 3 | 0 | 3 | 0.69% |
| RELATION_STATE_ACTION | 2 | 0 | 2 | 0.46% |

### Theo dạng hỏi ngôn ngữ (heuristic)

| Dạng hỏi | Số câu | Tỷ lệ |
|---|---:|---:|
| DIRECT_FACT_LOOKUP | 119 | 27.3% |
| QUANTITATIVE_LOOKUP | 111 | 25.5% |
| RELATIONAL_OR_MULTI_EVIDENCE | 79 | 18.1% |
| LIST_OR_SELECTION | 66 | 15.1% |
| DESCRIPTIVE_STATUS | 59 | 13.5% |
| COMPARISON | 2 | 0.5% |

## 3. Độ phân tán theo tài liệu

- Có QA trên **57/89** tài liệu ACCEPT (64.04%); **32 tài liệu không có câu nào**.
- Trung bình trên toàn bộ tài liệu ACCEPT: **4.9326** lượt QA/tài liệu; median **2**.
- Tài liệu cao nhất: **42** câu; top-5 chiếm **31.4%** lượt tham gia tài liệu.
- Gini gồm cả tài liệu 0-QA: **0.672**; HHI: **0.037**.

### 20 tài liệu có nhiều Q&A nhất

| Hạng | Doc ID | Tài liệu | Lĩnh vực | TRAIN | DEV | Tổng | Nhóm câu chính |
|---:|---|---|---|---:|---:|---:|---|
| 1 | IRR_CTL_2024_9c1d87a6 | Báo cáo tổng kết giám sát, dự báo chất lượng nước hệ thống công trình thủy lợi Ô Môn - Xà No năm 2024 | Quan trắc/giám sát và dự báo chất lượng nước | 42 | 0 | 42 | TABLE_TO_TABLE_COMPARISON:23; TABLE_ONLY:11; TEXT_ONLY:8 |
| 2 | IRR_CTL_2024_9a520097 | Báo cáo tổng kết giám sát, dự báo chất lượng nước hệ thống công trình thủy lợi Nam Măng Thít năm 2024 | Quan trắc/giám sát và dự báo chất lượng nước | 36 | 0 | 36 | TABLE_TO_TABLE_COMPARISON:15; TABLE_ONLY:10; TEXT_ONLY:8; STATE_TO_RECOMMENDATION:2; TABLE_TO_TEXT_EXPLANATION:1 |
| 3 | IRR_CTL_2026_79f76fed | Bản tin DB nguồn nước và KHSDN vùng NAM TRUNG BỘ - TUẦN 14/3/2025 ÷ 20/3/2025 | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 0 | 26 | 26 | TABLE_ONLY:11; TEXT_ONLY:9; TABLE_TO_TEXT_EXPLANATION:6 |
| 4 | IRR_CTL_2019_5278ca2b | Bản tin dự báo nguồn nước Lưu vực sông Cà Lồ - Ngũ Huyện Khê (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 17 | 0 | 17 | TABLE_ONLY:9; TEXT_ONLY:8 |
| 5 | IRR_CTL_2019_a1445f42 | Bản tin dự báo nguồn nước Lưu vực sông Thương (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 0 | 17 | 17 | TABLE_TO_TEXT_FORECAST:7; TEXT_ONLY:5; TABLE_ONLY:5 |
| 6 | IRR_CTL_2019_c565a3a3 | Bản tin dự báo nguồn nước Vùng giữa sông Hồng - Thái Bình (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 17 | 0 | 17 | TABLE_ONLY:14; TEXT_ONLY:3 |
| 7 | IRR_CTL_2019_645d37d3 | Bản tin dự báo nguồn nước Lưu vực sông Lục Nam (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 0 | 16 | 16 | TABLE_ONLY:11; TABLE_TO_TEXT_EXPLANATION:3; TEXT_ONLY:2 |
| 8 | IRR_CTL_2019_848be3bc | Bản tin dự báo nguồn nước Lưu vực sông Cầu (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 15 | 0 | 15 | TABLE_ONLY:11; TEXT_ONLY:4 |
| 9 | IRR_CTL_2025_dee3c4a4 | Bản tin dự báo nguồn nước và kế hoạch sử dụng nước vùng Nam Trung Bộ - Vụ Hè Thu 2025 | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 15 | 0 | 15 | TABLE_ONLY:10; TABLE_TO_TABLE_COMPARISON:5 |
| 10 | IRR_CTL_2019_0009185e | Bản tin dự báo nguồn nước vùng Đông Bắc Bộ (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 14 | 0 | 14 | TABLE_TO_TEXT_FORECAST:8; TEXT_ONLY:6 |
| 11 | IRR_CTL_2019_6b023172 | Bản tin dự báo nguồn nước Lưu vực sông Bằng Giang (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 0 | 14 | 14 | TABLE_TO_TEXT_EXPLANATION:6; TABLE_ONLY:6; TEXT_ONLY:2 |
| 12 | IRR_CTL_2019_01834078 | Bản tin dự báo nguồn nước vùng hạ du sông Hồng (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 11 | 0 | 11 | TABLE_ONLY:7; TEXT_ONLY:4 |
| 13 | IRR_CTL_2019_d9169102 | Bản tin dự báo nguồn nước Lưu vực thượng nguồn sông Đà (Từ 19/7 đến 25/7/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 10 | 0 | 10 | TEXT_ONLY:8; TABLE_ONLY:2 |
| 14 | IRR_CTL_2025_72b54901 | Giám sát, dự báo chất lượng nước Hệ thống An Trạch kỳ 11, ngày 18/04/2025 | Quan trắc/giám sát và dự báo chất lượng nước | 10 | 0 | 10 | TEXT_ONLY:10 |
| 15 | IRR_CTL_2019_1fc21515 | Bản tin dự báo nguồn nước Lưu vực sông Hoàng Long (Từ 01/6 đến 30/6/2019) | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 0 | 9 | 9 | TABLE_ONLY:6; SAME_ENTITY_DIFFERENT_TIME:3 |
| 16 | IRR_CTL_2025_fe5fdf2c | Bản tin DB nguồn nước và KHSDN vùng TÂY NGUYÊN - TUẦN 14/3/2025 ÷ 20/3/2025 | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 9 | 0 | 9 | TEXT_ONLY:9 |
| 17 | IRR_GOV_2021_7063d2bd | tong ket tai nguyen nuoc mekong 2021 | Báo cáo tổng kết tài nguyên nước/mùa lũ Mê Công | 9 | 0 | 9 | TEXT_ONLY:9 |
| 18 | IRR_GOV_2026_2b689fe4 | so tay cap xa thuy loi 2026 | Sổ tay quản lý thủy lợi cấp xã | 9 | 0 | 9 | TEXT_ONLY:9 |
| 19 | IRR_CTL_2019_216a5561 | Báo cáo kỳ 9: Diễn biến nguồn nước vùng ĐBSCL đến ngày 28/8, dự báo nguồn nước từ 29/8-07/9/2019 | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 7 | 0 | 7 | TEXT_ONLY:7 |
| 20 | IRR_CTL_2019_9b94947e | BC kỳ 3: Diễn biến nguồn nước vùng ĐBSCL đến ngày 17/7, dự báo nguồn nước từ ngày 18/7 - 27/7/2019 | Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 7 | 0 | 7 | TEXT_ONLY:7 |

## 4. Phân bố theo lĩnh vực tài liệu

`Unique QA participation` đếm một QA một lần trong mỗi lĩnh vực mà gold document của nó tham gia; tổng có thể lớn hơn 436 nếu QA nối nhiều lĩnh vực.

| Lĩnh vực tài liệu | Docs corpus | Docs có QA | Coverage | QA participation | Share TRAIN+DEV | Topic chính |
|---|---:|---:|---:|---:|---:|---|
| Bản tin/báo cáo dự báo nguồn nước và kế hoạch sử dụng nước | 37 | 19 | 51.35% | 224 | 51.38% | RAINFALL:67; STORAGE:53; WATER_LEVEL:33; AREA:29; WATER_SOURCE:21 |
| Quan trắc/giám sát và dự báo chất lượng nước | 29 | 28 | 96.55% | 166 | 38.07% | WATER_QUALITY:51; AREA:38; WATER_SOURCE:29; WATER_LEVEL:20; SALINITY:8 |
| Báo cáo tổng kết tài nguyên nước/mùa lũ Mê Công | 1 | 1 | 100.0% | 9 | 2.06% | RAINFALL:3; DISCHARGE:3; STORAGE:1; WATER_LEVEL:1; WATER_SOURCE:1 |
| Sổ tay quản lý thủy lợi cấp xã | 1 | 1 | 100.0% | 9 | 2.06% | RESERVOIR_OPERATION:3; DAM_SAFETY:3; DISASTER_PREVENTION:3 |
| Bản tin thiên tai tháng | 3 | 3 | 100.0% | 8 | 1.83% | DISASTER_PREVENTION:3; RAINFALL:2; RESERVOIR_OPERATION:1; WATER_SUPPLY:1; IRRIGATION_AGRICULTURE:1 |
| Báo cáo đánh giá hạ tầng cấp nước | 1 | 1 | 100.0% | 7 | 1.61% | WATER_SUPPLY:2; IRRIGATION_AGRICULTURE:2; DISCHARGE:1; DROUGHT_SHORTAGE:1; DISASTER_PREVENTION:1 |
| Văn bản quy định phòng chống thiên tai | 1 | 1 | 100.0% | 6 | 1.38% | SALINITY:5; DISASTER_PREVENTION:1 |
| Báo cáo tình huống vận hành hồ khi lũ | 1 | 1 | 100.0% | 4 | 0.92% | WATER_LEVEL:4 |
| Bản tin thủy văn/nguồn nước đột xuất do bão | 1 | 1 | 100.0% | 2 | 0.46% | RAINFALL:2 |
| Bản tin dự báo lũ và vận hành hồ chứa | 1 | 1 | 100.0% | 1 | 0.23% | RAINFALL:1 |
| Báo cáo rủi ro thiên tai và khí hậu quốc gia | 1 | 0 | 0.0% | 0 | 0.0% |  |
| Công điện/văn bản chỉ đạo ứng phó mưa lớn | 1 | 0 | 0.0% | 0 | 0.0% |  |
| Khung theo dõi, đánh giá chiến lược | 1 | 0 | 0.0% | 0 | 0.0% |  |
| Kế hoạch/lịch lấy nước phục vụ sản xuất | 1 | 0 | 0.0% | 0 | 0.0% |  |
| Quy trình pháp lý vận hành liên hồ chứa | 7 | 0 | 0.0% | 0 | 0.0% |  |
| Sổ tay quản lý rủi ro thiên tai dựa vào cộng đồng | 1 | 0 | 0.0% | 0 | 0.0% |  |
| Tài liệu lịch sử đê điều Việt Nam | 1 | 0 | 0.0% | 0 | 0.0% |  |

## 5. Rủi ro phân bố và chất lượng

1. **Không có human ground truth:** 0/436 TRAIN+DEV được human-validated.
2. **Bao phủ tài liệu chưa đủ:** 32/89 tài liệu ACCEPT không có QA TRAIN/DEV.
3. **Thiên lệch lĩnh vực:** dự báo nguồn nước và chất lượng nước chiếm phần lớn QA; toàn bộ 7 quy trình vận hành liên hồ ACCEPT không có QA TRAIN/DEV.
4. **Candidate Test tập trung một family:** 109/109 (100%) thuộc `IRR_SIWRP_2026_43c7d5c0`.
5. **Distribution shift có chủ ý nhưng rất mạnh:** Candidate Test có 63/109 cross-document và 63/109 table-table; TRAIN tương ứng 0/343 và 43/343.
6. **Template/câu gần trùng:** có 0 cặp trùng nguyên câu sau chuẩn hóa; 173 cặp đạt token-set Jaccard >= 0.90 trên toàn TRAIN+DEV, nhưng chỉ 1 cặp xuyên TRAIN–DEV ở ngưỡng này (12 cặp nếu hạ ngưỡng xuống 0.80). Đây là heuristic nhạy với câu cùng template, không tự động đồng nghĩa leakage nội dung.
7. **Template hóa:** top-10 heuristic templates chiếm 23.2% TRAIN+DEV.

## 6. Kết luận sử dụng

- Bộ Q&A hiện phù hợp hơn với đánh giá retrieval trên hai miền chi phối: dự báo nguồn nước và chất lượng nước.
- Chưa đủ cơ sở gọi là benchmark bao phủ toàn diện thủy lợi/tài nguyên nước vì nhiều nhóm pháp lý, vận hành hồ, đê điều, hạ tầng và PCTT không có hoặc có rất ít QA.
- Candidate Test nên được mô tả là series/family stress-test, không phải đại diện đồng đều cho toàn corpus.
- Trước khi dùng để kết luận khoa học, cần human-review một mẫu phân tầng theo topic × document × modality, rồi sửa/loại các QA sai nguồn hoặc sai semantics.
