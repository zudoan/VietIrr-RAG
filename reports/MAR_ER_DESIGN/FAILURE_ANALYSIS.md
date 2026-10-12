# MAR-ER: Scientific Failure Analysis

## Phạm vi và quy ước bằng chứng

Phân tích này chỉ dùng Dev và các artifacts B2, C1--C1.2, R1, R1.1. Candidate Test vẫn sealed. Các con số dưới đây là kết quả đã quan sát; diễn giải nguyên nhân được ghi riêng là giả thuyết. Không có gold, answer text hoặc nhãn success nào được dùng để xây quy tắc inference của MAR-ER.

| Run | Complete Candidate Coverage@100 | All-Evidence Recall@20 | Multi All-Evidence Recall@20 |
|---|---:|---:|---:|
| A0 Raw/Hard | 77.42% | 62.37% | 60% |
| A1 Raw/Soft | 81.72% | 53.76% | 60% |
| A2 Multi-view/Hard | 78.49% | 50.54% | 56% |
| A3 Multi-view/Soft | 86.02% | 47.31% | 56% |

Dev có 93 QA, trong đó 25 retrieval-multi nhưng chỉ có 8 unique multi gold sets. Vì vậy, các tỷ lệ theo QA không tương đương 93 hoặc 25 quan sát độc lập.

## 1. Vì sao multi-view fusion 50/50 thất bại?

### Quan sát đã xác minh

- A2 chỉ tăng candidate coverage 1.07 điểm phần trăm so với A0 nhưng làm All R@20 giảm 11.83 điểm và Multi All R@20 giảm 4 điểm.
- Trong kiểm tra R1.1, `TABLE_STRUCT` xếp hạng kém `TABLE_RAW` ở 60/62 lượt xuất hiện gold-table đã kiểm tra.
- R1.1 ghi nhận phép trộn 50/50 làm yếu raw view đang mạnh. Các regression table của R1 tập trung ở chính nhóm mà structural view yếu hơn raw.

### Giả thuyết nguyên nhân

Phép trung bình đối xứng ngầm giả định hai view có cùng độ tin cậy và mỗi view bổ sung thông tin độc lập. Giả định đó sai trong trường hợp table: structural serialization có thể mất tiêu đề, đơn vị, ngữ cảnh cột/hàng hoặc làm chuỗi xa phân phối biểu diễn của E5. Khi một view tốt và một view yếu được cấp trọng số bằng nhau, view yếu không chỉ “không giúp” mà còn thay đổi thứ tự của view tốt. Ngoài ra, score hoặc rank ở các pool khác nhau không có ý nghĩa tuyệt đối như nhau; cộng trực tiếp khiến số lượng view trở thành một lợi thế nhân tạo.

### Chưa đủ dữ liệu để kết luận

- 60/62 là bằng chứng chẩn đoán mạnh trên Dev, không chứng minh mọi structural table representation đều bất lợi.
- Chưa tách được tổn thất do serialization, truncation, embedding, hay fusion.
- Chưa có benchmark độc lập để xác nhận đây là hiện tượng tổng quát thay vì đặc thù corpus.

### Hệ quả thiết kế

Raw phải là backbone. Alternate view chỉ được tạo **one-sided uplift** khi nó xếp evidence cao hơn raw và có tín hiệu corroboration độc lập. Alternate view không được phép tự làm giảm raw score.

## 2. Vì sao soft hierarchy tăng coverage nhưng giảm final recall?

### Quan sát đã xác minh

- A1 so với A0: candidate coverage tăng từ 77.42% lên 81.72%, nhưng All R@20 giảm từ 62.37% xuống 53.76%.
- A3 so với A0: candidate coverage tăng 8.60 điểm phần trăm, nhưng All R@20 giảm 15.06 điểm.
- A3 cứu 9 QA ở candidate level và làm mất 1; tuy vậy ở final Top-20 chỉ cứu 4 và gây 18 regression. Chẩn đoán ghi nhận 9 trường hợp tránh được page pruning nhưng 18 trường hợp rank displacement.
- Trên subset 8 `c12_missing_multi`, A3 cứu 4 candidate nhưng chỉ cứu 1 All R@20. Trên subset table-regression, có 7 regression và không có recovery.

### Giả thuyết nguyên nhân

Soft retrieval giải quyết “ceiling” của candidate set nhưng đồng thời đưa nhiều evidence cạnh tranh vào cùng Top-20. Page/source prior hoặc alternate-view signal, nếu được cộng như bonus tự do, có thể đẩy evidence raw-relevant ra khỏi Top-20. Candidate recall và ranking precision vì thế là hai bài toán khác nhau: pool tốt hơn không tự động dẫn tới final ranking tốt hơn.

### Chưa đủ dữ liệu để kết luận

- Chưa biết phần regression nào do page score, phần nào do multi-view score, và phần nào do distribution shift của pool; A3 thay đổi nhiều thành phần cùng lúc.
- Chưa có per-query counterfactual đủ lớn để suy ra một threshold tối ưu mà không overfit Dev.

### Hệ quả thiết kế

Soft source chỉ nên mở rộng pool có quota; không được trực tiếp chiếm Top-K không giới hạn. MAR-ER tách hai tầng bảo vệ: giữ 80/100 baseline candidates và giữ 15/20 baseline Top-K members, rồi để evidence mới cạnh tranh trong phần ngân sách còn lại.

## 3. Vì sao contextual representation giúp text nhưng làm hại table?

### Quan sát đã xác minh

- R1/R2 cải thiện tổng thể so với raw baseline: All R@20 tăng từ 64.52% lên 65.59% ở cấu hình tốt hơn, và Multi All R@20 từ 60% lên 64%.
- Phân tích subgroup cho thấy text được cứu trong khi table chịu regression; structural table rank kém raw ở 60/62 lượt kiểm tra.

### Giả thuyết nguyên nhân

Text context thường thêm tiêu đề mục, chủ đề tài liệu và antecedent bị thiếu trong một chunk, nên query--evidence alignment tốt hơn. Với table, một serialization “cấu trúc” có thể kéo dài chuỗi, thay đổi thứ tự đọc, lặp nhãn hoặc tách số khỏi header/đơn vị; contextual prefix còn có thể chiếm token budget. Kết quả là representation bổ sung không giữ được lexical/numeric anchors vốn có trong raw table.

### Chưa đủ dữ liệu để kết luận

Không thể từ Dev kết luận rằng contextualization luôn có lợi cho text hoặc structuralization luôn có hại cho table. Hiệu ứng có thể phụ thuộc layout, độ dài bảng và chất lượng parsing.

### Hệ quả thiết kế

MAR-ER dùng alternate view theo modality: `TEXT_CONTEXT` cho text; `TABLE_STRUCT` chỉ khi source structure hợp lệ. Dù hợp lệ, table view vẫn phải vượt raw rank và được corroborate; “hợp lệ về cấu trúc” không đồng nghĩa “đáng tin về relevance”.

## 4. Khi nào giữ raw, khi nào tin alternate view?

Raw được giữ nguyên khi một trong các điều kiện sau xảy ra:

- alternate representation không tồn tại hoặc không vượt qua kiểm tra cấu trúc nguồn;
- alternate không xếp evidence cao hơn raw;
- alternate xếp cao nhưng không có corroboration từ BM25 hoặc page retrieval;
- evidence đã mạnh ở raw và alternate chỉ tạo thay đổi âm.

Alternate view được phép nâng điểm khi đồng thời:

1. view hợp lệ theo metadata có sẵn tại inference;
2. rank utility của alternate lớn hơn raw;
3. ít nhất một nguồn độc lập hơn -- lexical hoặc page retrieval -- hỗ trợ evidence.

Quy tắc này không khẳng định alternate là đúng. Nó chỉ biến độ tin cậy thành một điều kiện cần có thể tính không dùng gold. BM25 giữ numeric/keyphrase anchors; page retrieval cung cấp agreement ở granularity khác. Dùng giá trị lớn hơn của hai nguồn là một phép “OR corroboration” có chặn trên, tránh phạt evidence cross-document chỉ vì thiếu page rank.

Điều chưa thể kết luận là corroboration có calibration tốt trên corpus khác hay không. Một evidence thật nhưng chỉ alternate view tìm thấy có thể bị bỏ lỡ; đây là failure mode có chủ ý của một thiết kế bảo thủ.

## 5. Cứu evidence ngoài Top-P page mà không để nhiễu chiếm Top-K

MAR-ER không hard-prune evidence ngoài page shortlist. Nó hợp nhất baseline hard candidates, global BM25, global raw E5, modality alternate E5 và page-expanded candidates theo evidence ID. Nhưng hai giới hạn cấu trúc được áp dụng:

- **Candidate anchor:** giữ nguyên 80 evidence đầu của matched raw/hard baseline trong B=100; tối đa 20 vị trí còn lại dành cho toàn bộ nguồn mở rộng và baseline tail.
- **Top-K intrusion budget:** giữ nguyên membership của 15 evidence đầu trong baseline Top-20; chỉ 5 slot còn lại được quyết định lại bằng adaptive score.

Do mỗi source chỉ đóng góp một occurrence sau deduplication và mọi rank được đưa về cùng rank utility, source có nhiều duplicates hay score scale lớn không thể tự nhân trọng số. Missing page rank bằng 0 và không loại evidence. Cross-document và cả text/table evidence đều cạnh tranh bằng cùng quy tắc, nhưng alternate representation phụ thuộc modality.

## Kết luận khoa học từ failure analysis

Các artifacts đủ để bác bỏ ba giả định của MASH-ER V1 trên Dev: equal-view trust, unrestricted soft-source promotion, và coi candidate gain như final success. Chúng **chưa** đủ để chứng minh MAR-ER sẽ cải thiện retrieval. Thiết kế hợp lý nhất để thử tiếp là giữ raw order như một prior mạnh, giới hạn capacity của nguồn mới, và định nghĩa rank stability bằng guarantee trên membership/displacement thay vì bằng tên gọi hoặc score bonus.
