# VietIrrDocBench — Cross-Domain Compatibility Specification

## 1. Context & Purpose
VietIrrDocBench is the primary benchmark and research domain for long structured document retrieval in Vietnamese. 
To support scientific inquiry into cross-domain generalization (e.g., Transfer Learning from Corporate/Financial to Irrigation/Water Resources and vice versa), the benchmark adheres to a unified meta-schema.

```
+------------------------------------------------------------------+
|                     GENERIC ROOT META-SCHEMA                     |
| Document -> Section -> Subsection -> Page -> Region -> Table     |
| Entities | Metrics | TimePeriods | Units | Causes | Effects      |
+------------------------------------------------------------------+
               |                                    |
               v                                    v
+-------------------------------+   +-------------------------------+
|     CORPORATE / FINANCIAL     |   |   IRRIGATION / WATER RES.     |
| (Auxiliary Reference Domain)  |   |    (Primary Research Domain)  |
+-------------------------------+   +-------------------------------+
| Entity: Company, Subsidiary   |   | Entity: Reservoir, Basin, Dam |
| Metric: Revenue, EBITDA, Debt |   | Metric: WaterLevel, Discharge |
| Period: Q3/2023, FY2024       |   | Period: Flood season, 10-day  |
| Unit: VND, Billion, %         |   | Unit: m, m3/s, mil m3, mg/L   |
| Rule: Loan covenants, audited |   | Rule: Operating curve, alert  |
+-------------------------------+   +-------------------------------+
```

## 2. Structural Schema Mapping

| Level | Generic Schema | Corporate Domain | Irrigation / Water Resources (VietIrrDocBench) |
|---|---|---|---|
| **Document** | `doc_id`, `title`, `agency`, `doc_type`, `date` | Annual Report, Financial Statement, Audit Report | Quy trình vận hành liên hồ chứa, Báo cáo nguồn nước, Kế hoạch sử dụng nước |
| **Section** | `section_id`, `section_title`, `level` | "Báo cáo Ban điều hành", "Thuyết minh BCTC" | "Chế độ vận hành mùa lũ", "Quy định cắt giảm lũ", "Hiện trạng tích nước" |
| **Page** | `page_id`, `page_number`, `normalized_text` | Page 1..N | Page 1..N |
| **Region** | `region_id`, `region_type`, `bbox` | Heading, Paragraph, Table, Footnote | Heading, Paragraph, Table, Footnote, List |
| **Table** | `table_id`, `headers`, `rows`, `columns` | Balance sheet table, Cash flow table | Bảng thông số kỹ thuật hồ, Bảng mực nước đón lũ, Bảng lưu lượng xả |

## 3. Semantic & Taxonomy Mapping

### 3.1 Entities (`entities`)
- **Generic**: `[{"name": str, "type": str, "normalized": str}]`
- **Irrigation Domain**:
  - `RiverBasin` (Lưu vực sông: Sông Hồng, Sông Mã, Sông Cả, Sông Hương, Vu Gia - Thu Bồn, Đồng Nai, Ba, Sê San, Srêpôk, ĐBSCL...)
  - `Reservoir` (Hồ chứa: Hòa Bình, Sơn La, Lai Châu, Bản Chát, Tuyên Quang, Thác Bà, Cửa Đạt, Hủa Na, Bản Vẽ, Tả Trạch, Hương Điền, A Vương, Đak Mi 4, Trị An, Dầu Tiếng...)
  - `HydrologicalStation` (Trạm thủy văn: Hà Nội, Tạ Bú, Hòa Bình, Cẩm Thủy, Nam Đàn, Nông Sơn, Ái Nghĩa, Tà Lài...)
  - `IrrigationSystem` (Hệ thống thủy nông: Bắc Hưng Hải, Sông Nhuệ, Nam Măng Thít, Ô Môn Xà No...)
  - `Dam` / `Canal` / `Operator` / `Province`.

### 3.2 Metrics (`metrics`)
- **Generic**: Quantitative attribute name + value type (Observed, Forecast, Planned, Threshold).
- **Irrigation Domain**:
  - `WaterLevel` (Mực nước thượng lưu / hạ lưu)
  - `ReservoirStorage` (Dung tích trữ toàn bộ / hữu ích / phòng lũ)
  - `StoragePercentage` (Tỷ lệ dung tích trữ %)
  - `Inflow` (Lưu lượng đến hồ $Q_{\text{đến}}$)
  - `Outflow` / `Discharge` (Lưu lượng xả qua tràn / qua tổ máy phát điện / tổng lưu lượng về hạ du $Q_{\text{xả}}$)
  - `FloodLevel` (Mực nước đón lũ, mực nước dâng bình thường MNDBT, mực nước chết MNC, mực nước gia cường MNGC)
  - `Salinity` (Độ mặn 1g/L, 4g/L, ranh mặn)
  - `Rainfall` (Lượng mưa ngày, lượng mưa đợt)
  - `IrrigatedArea` (Diện tích tưới, diện tích lấy nước gieo cấy lúa)

### 3.3 Units (`units`)
- Standardized mapping:
  - Elevation/Length: `m`, `cm`, `mm`
  - Flow rate: `m3/s`, `m3/ngay-dem`
  - Volume: `m3`, `trieu m3` ($10^6\text{ m}^3$), `ty m3` ($10^9\text{ m}^3$)
  - Area: `ha`, `km2`
  - Concentration: `mg/L`, `g/L`, `‰` (phần nghìn độ mặn)
  - Percentage: `%`

### 3.4 Temporal Periods (`time_periods`)
- Types: `POINT_IN_TIME` (tại thời điểm $t$), `RANGE` (khoảng thời gian), `SEASON` (mùa lũ, mùa kiệt, vụ Đông Xuân, vụ Hè Thu, vụ Mùa).
- Forecasting dimension: `OBSERVED` vs `FORECAST` vs `PLANNED` vs `THRESHOLD`.

## 4. Transferability for Benchmarking
By retaining these standardized fields across datasets:
1. Retrieval models (dense encoders, hybrid BM25+splade, page-level rankers) can be evaluated zero-shot or cross-task between domains.
2. Models evaluated on VietIrrDocBench demonstrate structural retrieval capability on tabular and hierarchical regulatory documents without domain hardcoding.
