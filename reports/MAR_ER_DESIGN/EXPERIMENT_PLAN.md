# MAR-ER: Preregistered Experiment Plan

## 1. Scope

Tài liệu này thiết kế thực nghiệm; **không thực thi**. Phase A, evidence IDs, gold, QA và splits giữ nguyên. Dev là tập duy nhất được phép dùng cho chẩn đoán/iteration; Candidate Test vẫn sealed cho đến khi implementation, unit tests, configs, success gates và human-validity audit được freeze.

Mọi run dùng cùng evidence universe, query/evidence preprocessing, E5 checkpoint, BM25 analyzer, page index, hardware policy, candidate budget (B=100), final cutoff (K=20), và deterministic tie-breaking. Không fine-tune, LLM, model mới hoặc gold-guided gating.

## 2. Research questions

1. One-sided adaptive view contribution có giữ lợi ích raw tốt hơn multi-view 50/50 không?
2. Candidate anchor/quota có giữ candidate gain của soft retrieval mà giảm source domination không?
3. Bounded rank stability có giảm baseline regression đủ nhiều mà vẫn cho phép rescue không?
4. Full MAR-ER có cải thiện complete-evidence success, không chỉ candidate coverage, trên unique gold sets và modality subgroups không?

## 3. Fair baselines

| ID | System | Vai trò và kiểm soát |
|---|---|---|
| H0 | Historical reported baseline | Chỉ cung cấp bối cảnh lịch sử. Nếu preprocessing/index khác, không dùng cho superiority claim. |
| B0 | Matched raw hard-hierarchy baseline (A0) | Baseline chính; cùng snapshot, universe, B=100, K=20 và raw BM25/E5 pipeline. |
| B1 | Matched Global RRF | Global BM25 + raw E5, scaled RRF với (kappa=60); không page hard-pruning. |
| B2 | Matched R1 contextual retrieval | Cấu hình R1 tốt nhất được freeze trước MAR-ER; không retune. |
| B3 | MASH-ER V1 A3 | Multi-view/soft configuration đã định nghĩa; tái chạy matched nếu artifacts cho phép. |
| M | MAR-ER full | Equations, quotas và constrained selection trong `METHOD_SPEC.md`. |

Nếu một baseline không thể tái tạo dưới snapshot chung, phải gắn nhãn `historical_nonmatched`; không được trộn con số đó vào paired test. Latency phải đo sau warm-up và trên cùng device/batch policy.

## 4. Ablations

Các ablation chính độc lập, không chọn cấu hình theo kết quả:

| ID | Adaptive representation | Soft candidate recovery | Rank-stability | Mục đích |
|---|---:|---:|---:|---|
| A0 | no | no | no | matched backbone |
| A-REP | yes | no | no | chỉ kiểm tra Eq. (3)--(5) trên (mathcal C_0) |
| A-CAND | no | yes | no | chỉ kiểm tra Eq. (7)--(8), dùng raw (R_0) |
| A-STAB | no | no | yes | chỉ kiểm tra protected prefix/selection trên (mathcal C_0), dùng (R_0) |
| MAR-ER | yes | yes | yes | full method |

Secondary leave-one-component-out runs (`FULL-REP`, `FULL-CAND`, `FULL-STAB`) chỉ dùng để kiểm tra interaction, không thay primary method. Sensitivity của intrusion budget (d\in\{0,2,5,10\}) là secondary; primary luôn (d=5). Không chọn (d) thắng Dev rồi báo cáo như primary.

## 5. Metrics

### 5.1 Primary

Với gold set (G_q), candidate set (mathcal C_q), final Top-20 (T_q):

\[
\text{CompleteCandidate@100}(q)=\mathbf1[G_q\subseteq\mathcal C_q],
\]

\[
\text{AllEvidenceRecall@20}(q)=\mathbf1[G_q\subseteq T_q].
\]

Report macro average trên:

- toàn bộ Dev;
- retrieval-multi subset;
- **unique gold-set balanced success**: nhóm QA theo canonical sorted tuple của gold evidence IDs, lấy trung bình trong từng tuple rồi macro-average các tuple, để paraphrases không nhân số quan sát.

Không metric nào cho phép candidate gain bù cho final loss. All-Evidence Recall@20 và unique-set-balanced success là decision metrics; candidate coverage chỉ đo upper bound.

### 5.2 Secondary and diagnostic

- Text-only, Table-only và Mixed gold modality.
- Cross-page và cross-document.
- Single-evidence và retrieval-multi, ghi rõ chỉ có 8 unique multi gold sets hiện tại.
- Per-query MRR/nDCG chỉ là ranking diagnostics, không thay complete-evidence metrics.
- Baseline recovery: B0 fail, method success.
- Baseline regression: B0 success, method fail.
- Candidate recovered/lost và transition matrix.
- Top-20 overlap với B0; protected Top-15 retention; mean/max downward displacement của anchors; number of challenger intrusions.
- Source provenance của mỗi admitted/challenger evidence, duplicate count trước/sau merge, missing-page cases.
- Query latency (median, p95), indexing/storage delta, peak RAM/VRAM và retrieved-list sizes.

### 5.3 Mandatory stability audit

Mỗi query phải thỏa:

- candidate overlap với B0 Top-100 (ge80);
- final Top-20 overlap với B0 Top-20 (ge15);
- mọi B0 Top-15 member còn trong final Top-20;
- relative order của protected anchors không đảo;
- maximum protected-anchor downward displacement (le5).

Bất kỳ violation nào là implementation failure, không phải kết quả thực nghiệm.

## 6. Statistical validation

### 6.1 Unit of analysis

Report song song ba mức: QA, unique gold set, và document family. Kết luận chính không coi nhiều QA có cùng gold tuple là độc lập. Với multi subset, luôn kèm raw counts trên 8 unique gold sets, không chỉ phần trăm.

### 6.2 Paired uncertainty

- Tạo paired differences giữa MAR-ER và từng matched baseline trên cùng query/gold group.
- Dùng cluster bootstrap 10,000 replicates, seed `20261012`; resample document families, rồi tính metric macro trên unique gold sets trong family sample.
- Báo point estimate, 95% percentile CI, recovered/regressed counts và exact transition table.
- Với số cluster quá ít hoặc CI không ổn định, đánh dấu `UNDERPOWERED`; không chuyển sang QA-level test để tạo significance giả.
- Không correction/p-value nào biến Dev thành confirmatory test. Candidate Test chỉ được mở một lần sau freeze và cần cùng paired analysis.

## 7. Reproducibility and leakage controls

Trước khi chạy phải freeze:

1. dataset/artifact checksums, evidence universe và split IDs;
2. exact baseline config, (kappa=60), (B=100), (K=20), (d=5), per-source depth (B);
3. modality/structural-validity rules dựa duy nhất vào source metadata;
4. deterministic sort keys, duplicate resolution và missing-rank handling;
5. software environment, E5/BM25 versions, device, precision, batch size và seeds;
6. metric code với synthetic unit tests cho complete-set logic và five rank guarantees;
7. một audit log chứng minh inference không đọc gold/answer fields.

Mọi exception sau khi thấy Dev outcome phải được ghi thành protocol deviation. Không thay gate, quota, validity rule hoặc source depth để cứu riêng 8 multi gold sets.

## 8. Predeclared success gates

### Gate A: implementation validity

Tất cả reproducibility/leakage checks pass; candidate size (le100); unique IDs; năm rank-stability invariants đạt 100% queries. Gate này bắt buộc.

### Gate B: algorithmic feasibility on Dev

So với matched B0, full MAR-ER phải đồng thời:

- Complete Candidate Coverage@100 không giảm;
- All-Evidence Recall@20 không giảm ở overall và unique-gold-set-balanced view;
- Multi All-Evidence Recall@20 không giảm, báo kèm raw unique-set count;
- số final recoveries không nhỏ hơn regressions;
- Table-only All R@20 không giảm; không chấp nhận overall gain được mua bằng systematic table loss;
- ít nhất một complete-evidence recovery phải có provenance từ soft/global source, chứng minh recovery mechanism thực sự hoạt động.

Gate B chỉ cho phép kết luận “đáng đánh giá tiếp”, không cho phép paper claim.

### Gate C: evidence for a method claim

Để gọi là promising method, không chỉ safe prototype:

- MAR-ER phải có point estimate All R@20 và unique-set-balanced success cao hơn **mọi matched baseline**;
- cải thiện không chỉ đến từ duplicate QA hoặc một document family;
- full method phải tốt hơn A-REP/A-CAND/A-STAB trên ít nhất một primary complete-evidence metric và không kém các ablation trên hai metric còn lại;
- paired cluster CI của improvement so với B0 không được cho thấy material negative effect; một superiority claim mạnh hơn cần CI nằm trên 0 trên Candidate Test hoặc benchmark độc lập;
- latency/storage trade-off phải được báo, không được ẩn khi accuracy tăng.

Với Dev hiện tại, ngay cả Gate C cũng chỉ là bằng chứng sơ bộ vì 8 unique multi sets quá ít.

## 9. Predeclared rejection criteria

Bác bỏ phiên bản MAR-ER hiện tại nếu xảy ra bất kỳ điều nào sau:

- candidate coverage tăng nhưng overall hoặc unique-set All R@20 giảm so với B0;
- regressions nhiều hơn recoveries, đặc biệt regression tập trung ở table;
- rank-stability invariant bị vi phạm;
- adaptive representation tái tạo pattern TABLE_STRUCT lấn át TABLE_RAW;
- gain biến mất khi cân bằng theo unique gold sets/document family;
- full method không hơn component ablations, cho thấy complexity không tạo giá trị;
- improvement chỉ đạt được sau khi sửa (d), gate hoặc validity rule theo Dev outcome;
- resource cost tăng rõ nhưng complete-evidence metrics không tăng.

Khi rejection xảy ra, không mở Candidate Test và không tiếp tục thêm heuristic. Kết luận đúng là hypothesis không được hỗ trợ.

## 10. Execution order after design approval

1. Implement equations và invariants với synthetic tests, chưa đọc Candidate Test.
2. Reproduce matched B0/B1/B2/B3 trên Dev.
3. Freeze config/checksums.
4. Chạy ablations và MAR-ER một lần trên Dev; xuất transition/audit tables.
5. Áp success/rejection gates như đã viết.
6. Chỉ nếu Gate A--C có bằng chứng đủ và human audit xác nhận dữ liệu, preregister external/Candidate-Test evaluation. Việc đó nằm ngoài phase thiết kế hiện tại.
