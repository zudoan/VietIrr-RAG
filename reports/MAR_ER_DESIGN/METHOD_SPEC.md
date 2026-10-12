# MAR-ER: Method Specification

## 1. Problem formulation

Cho query (q), evidence universe (mathcal E) gồm các `TEXT_REGION` và `TABLE_REGION` lấy từ PDF dài. Mỗi QA có một gold set không được thuật toán nhìn thấy; thành công complete-evidence tại (K) đòi hỏi toàn bộ gold evidence cùng xuất hiện trong Top-(K). Mục tiêu là tạo:

- candidate set (mathcal C(q)), tối đa (B=100) unique evidence IDs;
- ranking cuối (pi(q)), trong đó đánh giá chính dùng (K=20).

Thiết kế phải tận dụng nguồn global/soft để cứu evidence bị page hierarchy bỏ sót nhưng không để nguồn mới tự do phá raw ranking mạnh.

## 2. Main scientific hypothesis

**Giả thuyết MAR-ER:** nếu (i) alternate representation chỉ tạo one-sided uplift khi được một nguồn độc lập hơn corroborate, (ii) candidate expansion có quota bảo vệ baseline, và (iii) final Top-(K) có ngân sách xâm nhập hữu hạn, thì có thể chuyển candidate-coverage gain thành complete-evidence gain với ít baseline regression hơn MASH-ER V1.

Đây là giả thuyết có thể bác bỏ, chưa phải kết luận. Cơ chế chính thống nhất là **conservative evidence admission** ở cả score, candidate membership và final membership. MAR-ER dùng tên đầy đủ *Modality-Adaptive, Bounded-Rank-Stable Evidence Retrieval*; chữ “bounded” là thiết yếu.

## 3. Notation and inputs

| Ký hiệu | Định nghĩa |
|---|---|
| (q) | query sau preprocessing cố định của Workspace B |
| (e\in\mathcal E) | một unique evidence ID |
| (m(e)) | modality: `TEXT_REGION` hoặc `TABLE_REGION` |
| (p(e)) | page chứa evidence |
| (r_s(e\mid q)) | rank 1-based của evidence trong source (s); (+\infty) nếu vắng |
| (s\in\{L,R,A,P\}) | BM25 raw, E5 raw, modality alternate, page relevance |
| (pi_0) | matched raw/hard baseline ranking, không sửa |
| (B,K) | candidate budget 100 và evaluation cutoff 20 |
| (d) | Top-(K) intrusion budget, cố định (\lfloor K/4\rfloor=5) |
| (kappa) | RRF rank constant 60, giữ từ baseline/protocol hiện có |

Các input hợp lệ là BM25 ranks, raw E5 ranks, contextual-text/structural-table E5 ranks hiện có, page ranks, evidence modality, page/document ID và cờ structural validity có thể suy ra từ source metadata. Không có gold, answer hay success label trong input.

### Modality-specific alternate view

\[
A(e)=
\begin{cases}
\text{TEXT\_CONTEXT}, & m(e)=\text{TEXT\_REGION},\\
\text{TABLE\_STRUCT}, & m(e)=\text{TABLE\_REGION}.
\end{cases}
\]

`TABLE_STRUCT` chỉ được đánh dấu hợp lệ nếu structural serialization bắt nguồn từ parsed row/header/cell metadata hợp lệ; không dựng cấu trúc từ query. `TEXT_CONTEXT` chỉ dùng context đã được lập chỉ mục, không tạo theo answer.

Mỗi evidence có nhiều nhất **một** alternate representation theo modality, và tất cả alternate vectors hợp lệ được tìm trong một unified E5 index. Không lấy một Top-(B) riêng cho text rồi một Top-(B) riêng cho table; làm vậy sẽ cấp hai “rank 1” và biến số modality lists thành ưu thế giả. Raw và alternate dùng cùng encoder/similarity convention trước khi chuyển sang rank utility.

## 4. Rank normalization

Với mọi rank source (s), định nghĩa normalized reciprocal-rank utility:

\[
u_s(e\mid q)=
\begin{cases}
\dfrac{\kappa+1}{\kappa+r_s(e\mid q)}, & r_s(e\mid q)<\infty,\\
0, & \text{nếu evidence vắng trong source.}
\end{cases}
\tag{1}
\]

### Diễn giải và cách tính

- (u_s\in[0,1]), rank 1 luôn bằng 1; chỉ cần lookup rank rồi áp dụng (1).
- Hệ số (kappa+1) chỉ rescale RRF bằng hằng số dương, nên không đổi thứ tự của baseline RRF.
- Mọi view có cùng range; thêm view không tự làm tổng score lớn hơn vì MAR-ER không cộng tất cả view.
- (kappa=60) là protocol constant đã có, không tune trên 8 multi gold sets.

### Lý do và điều kiện thất bại

Rank normalization tránh so sánh cosine với BM25 score khác thang. Tuy nhiên, rank bỏ qua khoảng cách score: rank 1 và 2 có thể gần nhau hoặc rất xa. Nếu list bị truncate quá ngắn, giá trị 0 có thể có nghĩa “chưa được retrieve” chứ không phải “không liên quan”. Vì vậy mọi source phải dùng cùng retrieval depth đã preregister.

## 5. Raw backbone and adaptive view contribution

### 5.1 Raw relevance

\[
R_0(e\mid q)=\tfrac12 u_L(e\mid q)+\tfrac12 u_R(e\mid q).
\tag{2}
\]

Đây là scaled two-source RRF của matched raw baseline. Hệ số (1/2) không phải learned weight; nó giữ BM25 và raw E5 đối xứng như baseline và giữ score trong ([0,1]). Trong code, lấy hai normalized rank utilities và tính trung bình. Nó có thể thất bại khi cả lexical và raw dense đều bỏ sót evidence.

### 5.2 Validity and corroboration

Cho (v(e)\in\{0,1\}) là cờ alternate representation hợp lệ theo metadata, và:

\[
c(e\mid q)=\max\{u_L(e\mid q),u_P(p(e)\mid q)\}.
\tag{3}
\]

Page utility của evidence là utility rank của parent page. Missing page rank cho (u_P=0), không loại evidence. (c) là “OR corroboration”: lexical match hoặc một granularity độc lập hơn có thể hỗ trợ alternate view. `max` giữ (c\le1), không thưởng hai lần khi cả BM25 và page cùng mạnh, và không bắt evidence cross-document phải có page rank nếu BM25 đã hỗ trợ.

Corroboration không chứng minh relevance. BM25 và page retriever vẫn có thể cùng sai; ngược lại, một alternate-only gold evidence thật sẽ có (c=0) và không được nâng.

### 5.3 One-sided modality-adaptive utility

\[
D_{\mathrm{adapt}}(e\mid q)=u_R(e\mid q)+v(e)c(e\mid q)
\left[u_A(e\mid q)-u_R(e\mid q)\right]_+,
\tag{4}
\]

với ([x]_+=\max(x,0)). Final admission relevance là:

\[
R(e\mid q)=\tfrac12 u_L(e\mid q)+\tfrac12 D_{\mathrm{adapt}}(e\mid q).
\tag{5}
\]

### Tính chất

Vì (0\le v,c\le1):

\[
u_R(e\mid q)\le D_{\mathrm{adapt}}(e\mid q)
\le\max\{u_R(e\mid q),u_A(e\mid q)\}.
\tag{6}
\]

Do đó alternate view không bao giờ làm giảm raw dense utility. Nếu alternate kém raw, phần dương bằng 0. Nếu alternate tốt hơn nhưng không được corroborate, score vẫn là raw. Nếu được corroborate hoàn toàn, dense utility tiến tới alternate nhưng không vượt view tốt hơn.

### Cách tính, lý do và failure condition

Implementation chỉ cần bốn rank lookup, cờ validity và các phép toán trong (3)--(5). Không có threshold học từ gold và không có 50/50 raw/alternate dilution. Cơ chế thất bại khi alternate là nguồn duy nhất phát hiện gold, khi corroboration sai, hoặc khi raw/BM25 rank mạnh nhưng sai tạo false promotion. Nó cũng không calibrate khác biệt query-specific giữa text và table; modality chỉ chọn view nào đủ tư cách, không cấp một trọng số table/text tùy chỉnh.

## 6. Evidence-preserving soft candidate retrieval

### 6.1 Source lists

Mỗi source trả tối đa (B) unique evidence IDs trước khi hợp nhất:

1. (mathcal C_0=\pi_0[1:B]): matched raw/hard baseline;
2. global BM25 raw Top-(B);
3. global E5 raw Top-(B);
4. modality alternate E5 Top-(B), sau structural-validity filtering;
5. page-to-region Top-(B), dùng page ranks hiện có nhưng không loại phần ngoài shortlist.

Gọi hợp (mathcal U) là union của năm list theo unique evidence ID. Mỗi ID giữ rank/provenance của từng source; một duplicate không được biến thành nhiều candidates hoặc nhiều phiếu.

### 6.2 Baseline anchor and rescue quota

Với (h=B-K=80):

\[
\mathcal A_B=\pi_0[1:h],
\qquad
\mathcal Q_B=\operatorname{Top}_{B-h}^{R}
(\mathcal U\setminus\mathcal A_B),
\tag{7}
\]

\[
\mathcal C=\mathcal A_B\cup\mathcal Q_B.
\tag{8}
\]

`Top` sắp theo (R) giảm dần, rồi `evidence_id` tăng dần để phá hòa. Vì (mathcal C_0\subseteq\mathcal U), luôn đủ 20 baseline-tail items để lấp quota nếu nguồn mới không cạnh tranh được.

### Ý nghĩa và bảo đảm

- Evidence ngoài page shortlist được vào nếu nó xuất hiện trong global lexical/dense/alternate list và nằm trong 20 điểm (R) cao nhất ngoài anchor.
- Nguồn mới cạnh tranh với baseline tail bằng cùng rank-normalized score, không bằng raw score riêng của nguồn.
- Mỗi source bị cap (B); sau dedup mỗi ID có một occurrence. Vì thế số lượng/scale của một source không tự tạo domination.
- (|\mathcal C\cap\mathcal C_0|\ge80). Đây là guarantee không cần biết gold.
- Text, table và cross-document evidence dùng cùng candidate quota; modality chỉ thay đổi alternate view hợp lệ.

Giới hạn: baseline evidence ở vị trí 81--100 có thể bị thay. Vì gold không biết trước, không thể bảo đảm candidate recall không giảm. Quota 20 cũng giới hạn số rescue.

## 7. Bounded rank-stable final selection

### 7.1 Định nghĩa rank stability

Đặt intrusion budget:

\[
d=\lfloor K/4\rfloor=5,
\qquad
\mathcal A_K=\pi_0[1:K-d]=\pi_0[1:15].
\tag{9}
\]

Chọn challengers:

\[
\mathcal Q_K=\operatorname{Top}_{d}^{R}(\mathcal C\setminus\mathcal A_K),
\qquad
\mathcal T_K=\mathcal A_K\cup\mathcal Q_K.
\tag{10}
\]

Final Top-(K) là thứ tự điểm (R) cao nhất **chịu precedence constraints**:

\[
a_i\prec a_j\quad\forall a_i,a_j\in\mathcal A_K, i<j,
\tag{11}
\]

trong đó (a_i=\pi_0[i]). Một cách tính xác định: tất cả challengers và chỉ “anchor kế tiếp” là available; ở mỗi bước emit available item có (R) cao nhất, hòa thì ưu tiên baseline rank rồi evidence ID; khi emit anchor, mở anchor tiếp theo. Sau Top-(K), các phần tử còn lại của (mathcal C) được xếp theo (R), baseline rank và evidence ID.

### 7.2 Bảo đảm không cần gold

Từ (9)--(11):

1. (|\pi[1:K]\cap\pi_0[1:K]|\ge K-d=15), tức Top-20 overlap ít nhất 75%.
2. Toàn bộ baseline Top-15 còn trong final Top-20.
3. Thứ tự tương đối của 15 anchors không đổi.
4. Mỗi anchor tụt tối đa (d=5) bậc vì chỉ có 5 challengers có thể được chèn trước nó.
5. Tối đa 5 final slots nằm ngoài protected prefix.

Đây là nghĩa chính xác của “bounded rank-stable”. (d=K/4) là operational safety budget được preregister như SLA giữ 75% membership, không được chọn theo Dev outcome. Sensitivity theo (d\in\{0,2,5,10\}) chỉ là secondary analysis sau primary run; không được dùng chọn kết quả chính.

### 7.3 Điều không thể bảo đảm

Không biết gold nên MAR-ER không thể bảo đảm:

- giữ toàn bộ baseline success: gold ở baseline ranks 16--20 vẫn có thể bị evict;
- challenger là relevant hoặc evidence còn thiếu được cứu;
- complete-evidence recall tăng;
- score/rank được calibration ngoài corpus;
- rescue quá 5 missing evidences vào Top-20.

Ràng buộc giảm regression capacity đồng thời giảm recovery capacity. Đây không phải monotonic recall guarantee.

## 8. Full algorithm pseudocode

```text
INDEXING (reuse existing artifacts; no training)
  for each evidence e:
    store evidence_id, doc_id, page_id, modality
    store raw text/table representation and raw E5 vector
    if TEXT_REGION: attach indexed TEXT_CONTEXT vector when available
    if TABLE_REGION and parsed structure is valid:
      attach TABLE_STRUCT vector and set v(e)=1
    else set v(e)=0 for unavailable alternate
  retain BM25 raw index, page index, and deterministic ID ordering

MULTI_VIEW_REPRESENTATION(q)
  encode q with the existing E5 query encoder
  retrieve/rank global raw E5
  retrieve/rank TEXT_CONTEXT and valid TABLE_STRUCT indexes
  retrieve/rank BM25 raw and pages
  map every retrieved item to its unique evidence_id and source rank

CANDIDATE_GENERATION(q)
  obtain baseline ranking pi0 with the matched raw/hard pipeline
  take up to B unique IDs from each of:
      pi0, global BM25, global raw E5, alternate E5, page-to-region
  U <- deduplicated union; retain all source ranks and provenance

ADAPTIVE_SCORING(e)
  convert L, R, A and parent-page P ranks to u using Eq. (1)
  c <- max(u_L, u_P)
  D_adapt <- u_R + v(e) * c * max(u_A - u_R, 0)
  score R(e) <- 0.5*u_L + 0.5*D_adapt

CANDIDATE_FUSION
  A_B <- first B-K=80 IDs of pi0
  Q_B <- best K=20 IDs in U \ A_B by (R desc, evidence_id asc)
  C <- A_B union Q_B

FINAL_RANKING
  d <- floor(K/4)=5
  A_K <- first K-d=15 IDs of pi0
  Q_K <- best d IDs in C \ A_K by
         (R desc, baseline_rank asc, evidence_id asc)
  T_K <- A_K union Q_K
  topK <- constrained priority ordering of T_K:
          preserve A_K precedence; otherwise choose highest R
  tail <- remaining C ordered by
          (R desc, baseline_rank asc, evidence_id asc)
  return topK followed by tail
```

## 9. Complexity

Gọi (N) là số evidence, (N_P) số page, (V) số dense representations khả dụng trên mỗi evidence (raw cộng tối đa một alternate), (D) embedding dimension, và (S=5) source lists.

- Với exact dense retrieval, query scoring là (O(VND)); page scoring là (O(N_PD)); BM25 phụ thuộc inverted-list matches. ANN có thể thay đổi retrieval cost nhưng không đổi method definition.
- Lấy Top-(B) bằng heap là (O(VN\log B)) sau scoring, thay vì full sort (O(VN\log N)).
- Union/dedup tối đa (SB) entries: (O(SB)) expected với hash map.
- Adaptive scoring và candidate selection: (O(SB\log B)); constrained Top-(K): (O(K\log K)).
- Storage dense là (O(VND)), cộng lexical/page indexes. Vì dùng embeddings hiện có, MAR-ER không yêu cầu model/training storage mới; production implementation vẫn cần đo peak RAM/VRAM.

## 10. Synthetic worked example

Ví dụ này hoàn toàn synthetic và chỉ minh họa đúng công thức. Query cần hai evidence: (e_T) là text và (e_B) là table. Baseline hard hierarchy tìm (e_T) ở rank 4 nhưng page shortlist loại page chứa (e_B).

Với (kappa=60):

| Evidence | (r_L) | (r_R) | (r_A) | (r_P) | Ghi chú |
|---|---:|---:|---:|---:|---|
| (e_T), text | 5 | 3 | 2 | 4 | baseline đã tìm thấy, context chỉ nhỉnh hơn raw |
| (e_B), table | 80 | 120 | 10 | missing | global lexical/structural retrieval tìm thấy |

Cho (e_T): (u_L=61/65=0.93846), (u_R=61/63=0.96825), (u_A=61/62=0.98387), (u_P=61/64=0.95313). Do đó (c=0.95313), (D_{adapt}=0.96825+0.95313(0.98387-0.96825)=0.98314), và (R(e_T)=0.96080). Raw signal không bị giảm.

Cho (e_B): (u_L=61/140=0.43571), (u_R=61/180=0.33889), (u_A=61/70=0.87143), (u_P=0). BM25 corroborate structural view nên (c=0.43571), (D_{adapt}=0.33889+0.43571(0.87143-0.33889)=0.57092), và (R(e_B)=0.50332).

Giả sử (e_B) không thuộc baseline Top-100 vì hard page filter, nhưng vào union qua global lists. Baseline Top-80 vẫn được giữ; (e_B) cạnh tranh cho 20 rescue/tail slots bằng (R=0.50332) và được chọn nếu thuộc Top-20 remainder. Ở final stage, (e_T) thuộc protected Top-15 nên chắc chắn còn trong Top-20. Nếu (e_B) nằm trong 5 challengers có (R) cao nhất, nó vào Top-20; final ranking chứa đủ hai evidence. Không bước nào biết rằng hai ID này là gold.

### Synthetic failure example

Một table (e_F) có raw rank 300, alternate rank 4, nhưng vắng trong BM25 và page ranks. Khi đó (c=0), nên (D_{adapt}=u_R): alternate không nâng điểm dù có rank rất cao. Evidence có thể vào union qua alternate list nhưng khó thắng candidate/final quota. Nếu (e_F) thật sự là gold, MAR-ER bỏ lỡ nó. Đây là cái giá có chủ ý của conservative admission; nới gate để cứu trường hợp này cũng mở lại failure mode “weak alternate dominates raw”.

## 11. Failure modes and novelty limitations

### Failure modes

- Correlated false positives giữa BM25/page và alternate vẫn được uplift.
- Gold evidence chỉ hiện diện trong alternate view nhưng không corroboration bị bỏ lỡ.
- Baseline sai ở Top-15 được bảo vệ và chiếm capacity.
- Multi-evidence query cần hơn 5 rescues không thể hoàn tất ở K=20.
- Truncated rankings, parsing lỗi hoặc duplicate-ID mapping sai làm guarantee đầu vào vô nghĩa.
- Fixed (d=5) có thể quá bảo thủ hoặc quá lỏng trên domain khác.

### Novelty limitations

Contextual chunks, hierarchical retrieval, multi-view representations, RRF, table-aware retrieval và multi-hop evidence retrieval đều đã có prior art. Phần có khả năng tạo đóng góp không phải từng thành phần, mà là tổ hợp có cấu trúc của:

1. one-sided, corroboration-gated alternate-view uplift;
2. baseline-overlap guarantee ở candidate budget;
3. precedence-constrained Top-(K) với overlap và displacement bounds.

Hiện chưa có bằng chứng rằng tổ hợp này là novel theo literature đầy đủ, và chưa có thực nghiệm chứng minh nó hữu ích. Vì vậy nên mô tả MAR-ER hiện tại là **một thiết kế constrained fusion có giả thuyết nghiên cứu rõ**, không phải một phương pháp mới đã được xác lập.
