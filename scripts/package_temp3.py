import os
import shutil
import glob

def main():
    temp3_dir = "temp3"
    os.makedirs(temp3_dir, exist_ok=True)

    # 1. Copy Data Artifacts
    shutil.copy2("data/qa/pilot_qa.jsonl", os.path.join(temp3_dir, "pilot_qa.jsonl"))
    shutil.copy2("data/qa/page_localization_gold.jsonl", os.path.join(temp3_dir, "page_localization_gold.jsonl"))
    shutil.copy2("data/negatives/hard_negatives.jsonl", os.path.join(temp3_dir, "hard_negatives.jsonl"))
    shutil.copy2("data/manifests/download_manifest.jsonl", os.path.join(temp3_dir, "download_manifest.jsonl"))
    shutil.copy2("data/manifests/source_catalog.csv", os.path.join(temp3_dir, "source_catalog.csv"))
    shutil.copy2("data/manifests/doc_id_migration.json", os.path.join(temp3_dir, "doc_id_migration.json"))

    # 2. Copy Documentation and Checksums
    shutil.copy2("DATASET_CARD.md", os.path.join(temp3_dir, "DATASET_CARD.md"))
    shutil.copy2("README.md", os.path.join(temp3_dir, "PROJECT_README.md"))
    shutil.copy2("checksums/sha256sums.txt", os.path.join(temp3_dir, "sha256sums.txt"))
    shutil.copy2("configs/qa/evidence_roles_v2_2.yaml", os.path.join(temp3_dir, "evidence_roles_v2_2.yaml"))

    # 3. Copy All Reports
    for f in glob.glob("reports/v2_2/*.*"):
        if os.path.isfile(f):
            shutil.copy2(f, os.path.join(temp3_dir, os.path.basename(f)))

    # 4. Copy Human Review Sample Directory
    sample_src = "reports/v2_2/human_review_sample"
    sample_dst = os.path.join(temp3_dir, "human_review_sample")
    if os.path.exists(sample_src):
        if os.path.exists(sample_dst):
            shutil.rmtree(sample_dst)
        shutil.copytree(sample_src, sample_dst)

    # 5. Copy Validation Source Modules
    val_src = "src/validation"
    val_dst = os.path.join(temp3_dir, "validation_modules")
    if os.path.exists(val_src):
        if os.path.exists(val_dst):
            shutil.rmtree(val_dst)
        shutil.copytree(val_src, val_dst)

    # 6. Create Index Guide in temp3
    readme_path = os.path.join(temp3_dir, "README_TEMP3_INDEX.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# VIETIRRDOCBENCH V2.2 - GÓI DỮ LIỆU ĐÓNG GÓI CHUẨN (TEMP3)\n\n")
        f.write("Thư mục này tổng hợp toàn bộ các artifacts quan trọng nhất của đợt hoàn thiện **V2.2 Semantic Hotfix**.\n\n")
        f.write("## 1. Dữ liệu Benchmark Core (Ground-Truth)\n")
        f.write("- `pilot_qa.jsonl`: 348 QA V2.2 chuẩn hóa (100% độc lập validated, 0 rỗng/placeholder, 81 QA tài liệu dài).\n")
        f.write("- `page_localization_gold.jsonl`: Metadata định vị trang gold độc lập và đồng nhất.\n")
        f.write("- `hard_negatives.jsonl`: 627 bộ minimal counterfactual hard negatives (206 entity, 197 metric, 31 period, 193 provenance conflict).\n\n")
        f.write("## 2. Nguồn gốc & Danh mục tài liệu\n")
        f.write("- `download_manifest.jsonl`: 40 bản ghi tải về (18 core_long, 22 temporal).\n")
        f.write("- `source_catalog.csv`: 40 bản ghi nguồn chính thức từ cơ quan nhà nước (0 mồ côi).\n")
        f.write("- `doc_id_migration.json`: Bản đồ ánh xạ chuẩn hóa năm xuất bản tài liệu.\n\n")
        f.write("## 3. Hệ thống Báo cáo Kiểm toán V2.2\n")
        f.write("- `dataset_stats.json`: Single Source of Truth cho toàn bộ số liệu thống kê.\n")
        f.write("- `10_v2_2_readiness.json`: Checklist sẵn sàng Phase A.\n")
        f.write("- `v2_2_final_audit.json`: Kết quả audit 27 tiêu chí kỹ thuật và ngữ nghĩa (100% PASS).\n")
        f.write("- `01_semantic_qa_audit.md` & `.json`: Báo cáo phân loại QA (256 Kept, 50 Repaired, 33 Rejected).\n")
        f.write("- `02_independent_necessity_audit.md`: Báo cáo kiểm định tính tất yếu bằng validator độc lập.\n")
        f.write("- `03_counterfactual_quality.md`: Báo cáo chất lượng hard negatives tối thiểu.\n")
        f.write("- `04_table_semantic_audit.md`: Báo cáo loại bỏ lỗi ngày tháng làm chỉ tiêu và thực thể chung chung.\n")
        f.write("- `05_distribution_audit.md`: Báo cáo độ phủ tài liệu và lưu vực sông.\n")
        f.write("- `06_v2_2_stats.md`: Báo cáo tổng hợp số liệu thống kê canonical.\n\n")
        f.write("## 4. Mẫu kiểm định cho chuyên gia\n")
        f.write("- `human_review_sample/`: Chứa các file mẫu phân tầng (single, 2-ev, 3-ev, cross-page, text+table, counterfactual, core-long) kèm file đọc chi tiết `sample_inspection_view.md`.\n\n")
        f.write("## 5. Quy chuẩn ngữ nghĩa & Mã nguồn Validator\n")
        f.write("- `evidence_roles_v2_2.yaml`: Taxonomy chuẩn hóa 15 evidence semantic roles.\n")
        f.write("- `validation_modules/`: Mã nguồn 3 bộ validator độc lập (necessity, table semantic, counterfactual).\n")
        f.write("- `DATASET_CARD.md`: Thẻ dữ liệu hoàn chỉnh chuẩn học thuật.\n")
        f.write("- `sha256sums.txt`: Bảng mã băm kiểm tra tính toàn vẹn.\n")

    print(f"Done! Successfully packaged all essential files into {temp3_dir}/")

if __name__ == "__main__":
    main()
