import json

def main():
    samples = [json.loads(l) for l in open('reports/v2_2/human_review_sample/sample_core_long_qa_20.jsonl', encoding='utf-8')][:5]
    samples += [json.loads(l) for l in open('reports/v2_2/human_review_sample/sample_three_evidence_20.jsonl', encoding='utf-8')][:5]
    negs = [json.loads(l) for l in open('reports/v2_2/human_review_sample/sample_counterfactual_negatives_20.jsonl', encoding='utf-8')][:5]

    with open('reports/v2_2/human_review_sample/sample_inspection_view.md', 'w', encoding='utf-8') as f:
        f.write('# VietIrrDocBench V2.2 - Human Inspection Detailed View\n\n')
        f.write('> Trạng thái: `HUMAN_VALIDATED = false`. Bảng mẫu dưới đây phục vụ hội đồng / chuyên gia thẩm định trực tiếp.\n\n')
        f.write('## 1. Selected Multi-Evidence & Core-Long QA Samples\n\n')
        for idx, q in enumerate(samples, 1):
            f.write(f"### QA #{idx}: `{q['qa_id']}`\n")
            f.write(f"- **Question**: {q['question']}\n")
            f.write(f"- **Reference Answer**: {q['answer']}\n")
            f.write(f"- **Document**: `{q['doc_id']}` (Pages: {q.get('gold_pages')})\n")
            f.write(f"- **Evidence Count**: {q.get('evidence_count')}\n")
            f.write('- **Gold Evidence Items**:\n')
            for ev in q.get('gold_evidence', []):
                f.write(f"  - `[{ev.get('evidence_id')}]` (Page {ev.get('page_number')}, Role: `{ev.get('role')}`): {ev.get('exact_content')}\n")
            f.write('\n---\n\n')
            
        f.write('## 2. Selected Minimal Counterfactual Hard Negatives\n\n')
        for idx, n in enumerate(negs, 1):
            f.write(f"### Negative Set #{idx}: `{n['negative_set_id']}`\n")
            f.write(f"- **Associated QA**: `{n['qa_id']}`\n")
            f.write(f"- **Type**: `{n['negative_type']}` (Corrupted Factor: `{n['corrupted_factor']}`)\n")
            f.write(f"- **Target Signature**: `{json.dumps(n.get('target_signature'), ensure_ascii=False)}`\n")
            f.write(f"- **Negative Signature**: `{json.dumps(n.get('negative_signature'), ensure_ascii=False)}`\n")
            f.write('\n---\n\n')
            
    print("Generated reports/v2_2/human_review_sample/sample_inspection_view.md")

if __name__ == "__main__":
    main()
