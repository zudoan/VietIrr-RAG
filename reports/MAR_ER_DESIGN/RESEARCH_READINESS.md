# MAR-ER: Research Readiness Review

## Executive decision

MAR-ER có một cơ chế thống nhất, ít tham số và có các guarantee thật về candidate overlap, Top-K overlap và protected-anchor displacement. Nó trực tiếp nhắm vào failure đã quan sát của MASH-ER V1 thay vì thêm một score bonus mới. Vì vậy, thiết kế **đủ rõ để triển khai một thí nghiệm falsification có kiểm soát**.

Tuy nhiên, novelty hiện chỉ ở mức *potential composition-level contribution*; data quá nhỏ để hỗ trợ method-paper claim, đặc biệt chỉ có 8 unique multi gold sets. Do đó:

- **IMPLEMENTATION_READY: YES, WITH PREREGISTRATION**
- **PAPER_READY: NO**
- Không mở Candidate Test và không dùng tên “novel method” trước khi có matched experiment, literature search hệ thống và human-verified external evaluation.

## 1. Strengths

- **Raw-safe scoring:** alternate view chỉ nâng, không hạ raw utility; trực tiếp xử lý failure của fusion 50/50.
- **Tách coverage khỏi ranking:** candidate rescue có quota riêng; final ranking có intrusion budget riêng.
- **Guarantee không cần gold:** giữ ít nhất 80 baseline candidates, 15 baseline Top-20 members, thứ tự tương đối Top-15 và giới hạn tụt tối đa 5 bậc.
- **Ít tham số:** dùng (kappa=60), (B=100), (K=20) đã có; chỉ thêm SLA (d=K/4), được freeze chứ không tune.
- **Leakage-safe by construction:** validity, ranks và corroboration đều tính được từ query/source metadata tại inference.
- **Có thể bác bỏ:** experiment plan nêu trước trường hợp coverage tăng nhưng final recall giảm là thất bại, không phải thành công.

## 2. Weaknesses

- Corroboration (\max(u_{BM25},u_{page})) là một inductive bias hợp lý nhưng chưa được chứng minh calibration; hai nguồn có thể correlated hoặc cùng sai.
- Bảo vệ baseline Top-15 cũng bảo vệ false positives mạnh và chỉ để tối đa 5 rescue slots.
- (d=5) là safety policy, không phải hằng số lý thuyết tối ưu. Guarantee phụ thuộc trực tiếp vào lựa chọn này.
- Candidate anchor chỉ bảo vệ membership, không bảo vệ baseline evidence ở ranks 81--100.
- Rank normalization loại bỏ score-margin information và nhạy với retrieval depth/truncation.
- Modality adaptation hiện là chọn alternate view + validity gate; chưa phải learned or theoretically optimal modality estimator.

## 3. Unproven hypotheses

1. BM25/page corroboration dự báo alternate-view usefulness tốt hơn một equal-weight fusion.
2. Một one-sided uplift đủ để giữ text gains mà tránh table regressions.
3. 20 candidate-rescue slots đủ cho missing evidence nhưng không quá nhiều nhiễu.
4. 5 challenger slots đạt trade-off recovery/regression phù hợp.
5. Candidate gain có thể chuyển thành complete-evidence gain dưới constrained selection.
6. Guarantees về overlap/displacement có tương quan với user-relevant stability.
7. Cơ chế tổng quát ngoài corpus PDF thủy lợi tiếng Việt.

Không giả thuyết nào ở trên được chứng minh chỉ bằng thiết kế.

## 4. Prior-art comparison

| Existing method | Known mechanism | Overlap with MAR-ER | Potential difference | Evidence needed to establish novelty |
|---|---|---|---|---|
| [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) | Thêm document-specific context vào chunk trước embedding và BM25 | `TEXT_CONTEXT`, lexical+dense retrieval | MAR-ER không luôn tin context; chỉ cho one-sided, corroborated uplift | Head-to-head matched implementation; chứng minh gating tạo lợi ích vượt contextual retrieval thuần |
| [Dense Hierarchical Retrieval](https://aclanthology.org/2021.findings-emnlp.19/) | Retrieve document rồi passage, kết hợp relevance ở hai cấp | Page-to-region candidates và page signal | Page rank trong MAR-ER là corroboration/candidate provenance, không hard-prune và không tự cộng bonus | Formal comparison với hierarchical calibration và soft hierarchy variants |
| [DAPR: Document-Aware Passage Retrieval](https://aclanthology.org/2024.acl-long.236/) | Làm passage retrieval nhận biết document context | Context-aware evidence representation | MAR-ER tập trung vào conservative admission và stability bounds hơn là representation training | Thực nghiệm tách representation gain khỏi constrained fusion gain |
| [Multi-View Document Representation Learning](https://aclanthology.org/2022.acl-long.414/) | Học nhiều embeddings/view của document | Nhiều representation cho một evidence | MAR-ER không học fusion; alternate view bị chặn bởi raw dominance và corroboration | Literature search về gated/mixture multi-view retrieval; ablation chứng minh one-sided gate cần thiết |
| [MC-indexing](https://aclanthology.org/2024.findings-emnlp.150/) | Lập nhiều chỉ mục cho raw/keywords/summary rồi hợp nhất retrieval | Multi-index, không fine-tune | MAR-ER dùng modality-specific validity, quota và rank bounds | So sánh fair với multi-view indexing/fusion dưới cùng source budget |
| [Reciprocal Rank Fusion](https://doi.org/10.1145/1571941.1572114) | Hợp nhất ranked lists bằng reciprocal ranks | Eq. (1)--(2), scale-invariant hybrid fusion | MAR-ER không cộng đều mọi list; alternate chỉ tác động một chiều và có gate | Chứng minh improvement không chỉ do RRF/source-depth choice |
| [Multi-modal Table/Text Retrieval for Open QA](https://aclanthology.org/2021.mrqa-1.8/) | Joint retrieval trên passages và tables bằng modality-aware encoders | Text/table distinction | MAR-ER giữ một encoder hiện có và dùng constrained rank fusion thay vì train modality encoders | Benchmark ngoài domain và so sánh với table-aware retriever mạnh |
| [Open Domain QA over Tables](https://aclanthology.org/2021.naacl-main.43/) | Retrieve/rank tables và linked text cho QA | Evidence phân tán qua table và text | MAR-ER nhắm complete evidence trong long Vietnamese PDFs, không reader/QA pipeline | External mixed-modality benchmark và evaluation không phụ thuộc parsing riêng của corpus |
| [Joint Candidate Evidence Retrieval](https://aclanthology.org/2021.naacl-main.363/) | Retrieve tập candidate evidence phục vụ reasoning | Candidate set hướng tới evidence-complete reasoning | MAR-ER dùng fixed candidate budget và baseline-preserving admission, không joint training | So sánh set-level recall và chứng minh constraint đem lại regression control |
| [Multi-hop Evidence Retrieval](https://aclanthology.org/2023.findings-acl.657/) | Retrieve evidence nhiều bước/cross-document cho multi-hop QA | Cross-document complete-evidence objective | MAR-ER là one-shot multi-source retrieval, không query expansion hoặc iterative reasoning | Đánh giá trên benchmark multi-hop độc lập; phân tích giới hạn one-shot retrieval |

## 5. Novelty assessment

### Phần đã biết

Contextual chunks, hierarchical/parent-child retrieval, table/text-aware representations, multi-view indexing, hybrid RRF và evidence-set retrieval đều là hướng đã biết. Dùng riêng từng thành phần không tạo novelty thuyết phục.

### Phần có thể là đóng góp

Ứng viên đóng góp là **cấu trúc ba lớp đồng nhất**:

1. alternate-view improvement chỉ đi một chiều và tỷ lệ với corroboration;
2. candidate expansion bị ràng buộc bởi baseline-overlap quota;
3. final selection là precedence-constrained topological ranking với guarantee Top-K overlap/displacement.

Đây là khác biệt cụ thể, có thể formalize và ablate. Tuy nhiên, hiện chưa đủ literature coverage để khẳng định chưa từng có conservative/safe fusion hoặc constrained reranking tương tự. RRF và các hướng trên cũng làm phần lớn nguyên liệu kỹ thuật đã quen thuộc.

### Kết luận thẳng

MAR-ER hiện là **một tổ hợp có nguyên lý và guarantee rõ hơn MASH-ER V1**, nhưng chưa được chứng minh là đóng góp phương pháp mới. Nếu full method không vượt các component ablations hoặc matched baselines, research value chỉ còn ở negative finding về stability--recall trade-off. Để lập novelty claim cần:

- systematic review cụ thể về safe/conservative rank fusion, constrained top-k reranking và learning-to-rank stability;
- theorem/proof trình bày đầy đủ về guarantees và trade-off capacity;
- bằng chứng trên ít nhất một benchmark độc lập;
- ablation cho thấy tổ hợp, không chỉ representation hoặc RRF, tạo gain.

## 6. Dataset and evaluation limitations

- Dev chỉ có 93 QA, 25 retrieval-multi và 8 unique multi gold sets; statistical power rất thấp cho complete multi-evidence claims.
- Nhiều QA có thể chia sẻ gold tuple/document family, nên QA-level percentage phóng đại mức độc lập.
- Table-only sample và 60/62 diagnostic occurrences hữu ích để phát hiện failure nhưng không đại diện mọi loại bảng.
- Một domain, một ngôn ngữ và PDF/layout pipeline hạn chế external validity.
- Gold evidence có thể đúng cho QA nhưng không đo mọi relevant evidence; rank stability so với baseline không đồng nghĩa semantic correctness.
- Dev đã được dùng cho nhiều vòng diagnosis, làm tăng nguy cơ researcher overfitting dù không tune trực tiếp.
- Candidate Test sealed là đúng, nhưng bản thân một Candidate Test cùng corpus chưa đủ thay thế external replication/human-verified evaluation.

## 7. Algorithm feasibility gate

| Câu hỏi | Đánh giá |
|---|---|
| Công thức nhất quán? | Yes; score có chặn, candidate/final budgets cộng đúng B/K |
| Không leakage? | Yes by design; cần audit implementation |
| Dùng artifacts hiện tại? | Yes; BM25, E5 raw/context/struct, page ranks và baseline order đã có |
| Giải thích regression/recovery? | Yes; provenance, admission score và bounded intrusion đều audit được |
| Baseline/ablation công bằng? | Yes, nếu tái chạy matched snapshot như plan |
| Guarantee thực? | Yes cho overlap/order/displacement; no cho relevance/recall |

**Algorithm feasibility: READY WITH CONDITIONS.** Điều kiện là implementation phải pass deterministic unit tests và mọi stability invariant trước khi xem outcome.

## 8. Paper feasibility gate

| Câu hỏi | Đánh giá |
|---|---|
| Novelty đã xác lập? | No; mới có potential composition-level difference |
| Đủ unique gold sets? | No, đặc biệt multi chỉ có 8 |
| Cần human/external evaluation? | Yes |
| Claim hiện có thể nói? | “Một constrained fusion design có formal stability bounds và falsifiable hypothesis.” |
| Claim chưa thể nói? | “State of the art”, “general rank-stable improvement”, “novel method”, hoặc “improves multi-evidence retrieval” |

**Paper feasibility: NOT READY.** Một Dev experiment tốt chỉ nâng trạng thái lên “promising”; paper readiness cần Candidate-Test/external replication, uncertainty theo cluster, error audit và novelty review sâu hơn.

## 9. Recommended decision

Nên triển khai **đúng một controlled MAR-ER experiment** theo `EXPERIMENT_PLAN.md`, với mục tiêu falsification chứ không tối ưu tiếp. Dừng ngay nếu candidate gain vẫn đi cùng final regression, table regressions quay lại, hoặc full method không hơn ablations. Không thêm heuristic sau khi thấy kết quả và không mở Candidate Test nếu Dev gates thất bại.

Giữ tên MAR-ER chỉ khi báo cáo luôn dùng nghĩa “bounded rank-stable”. Nếu implementation bỏ protected-prefix/precedence constraint, tên phù hợp hơn là `Modality-Adaptive Conservative Fusion`, vì khi đó không còn guarantee về rank.
