def validate(qa: dict, context: dict) -> dict:
    table_evidence = [item for item in qa.get("gold_evidence", []) if item.get("region_type") == "table"]
    if not table_evidence:
        return {"status": "SKIP_NOT_APPLICABLE", "failures": []}
    failures = []
    for evidence in table_evidence:
        trace = evidence.get("table_trace") or {}
        table = context["tables"].get(trace.get("table_id"))
        if not table:
            failures.append(f"MISSING_TABLE:{trace.get('table_id')}")
            continue
        row_index, column_index = trace.get("row_index"), trace.get("column_index")
        if not isinstance(row_index, int) or not isinstance(column_index, int):
            failures.append("INVALID_TABLE_INDEX")
            continue
        try:
            raw = table["rows"][row_index][column_index]
            header = table["headers"][column_index]
        except (IndexError, TypeError):
            failures.append("TABLE_INDEX_OUT_OF_RANGE")
            continue
        if raw != trace.get("raw_cell") or header != trace.get("column_label"):
            failures.append("TABLE_TRACE_VALUE_MISMATCH")
        expected_label = table["row_labels"][row_index]
        if expected_label != trace.get("row_label"):
            failures.append("TABLE_ROW_LABEL_MISMATCH")
        if table.get("quality_label") != "GOOD":
            failures.append("NON_GOOD_TABLE")
    return {"status": "FAIL" if failures else "PASS", "failures": failures}
