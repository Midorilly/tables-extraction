import json
import os
import difflib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

GROUND_TRUTH_DIR = os.path.join(PROJECT_ROOT, "data", "ground_truth", "test")
DOCLING_DIR = os.path.join(PROJECT_ROOT, "data", "extractions", "baseline", "metrics", "test")
PLUMBER_DIR = os.path.join(PROJECT_ROOT, "data", "extractions", "custom", "metrics", "test")
REPORTS_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "evaluation_reports")

os.makedirs(REPORTS_OUT_DIR, exist_ok=True)

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def flatten_headers(headers_data):
    """
    Flattens expected_columns (or columns) into a 1D sequence for exact order matching.
    Handles ANY nested combination of lists and dictionaries perfectly.
    (Strict matching: no longer normalizes dot-separated MultiIndex headers).
    """
    raw_columns = headers_data.get("expected_columns", headers_data.get("columns", []))
    
    def _extract_strings(data):
        extracted = []
        if isinstance(data, dict):
            # Sort keys to ensure consistent order regardless of original dict order
            for key in sorted(data.keys()):
                extracted.extend(_extract_strings(data[key]))
        elif isinstance(data, list):
            for item in data:
                extracted.extend(_extract_strings(item))
        else:
            extracted.append(str(data))
        return extracted
        
    flat_list = _extract_strings(raw_columns)
    
    normalized_list = []
    for col in flat_list:
        col_str = str(col).strip().lower()
        normalized_list.append(col_str)
        
    return normalized_list

def calculate_metrics(ground_truth, predicted):
    """
    Calculates metrics and returns a structured JSON-ready dictionary 
    and raw numeric data for global aggregation.
    """
    
    gt_logical_tables = ground_truth.get("logical_tables", [])
    pred_logical_tables = predicted.get("logical_tables", [])
    
    # Create a set of all pages that contain GT tables
    # If a table falls in any of these pages, it's potentially useful. If it falls outside, it's likely noise (summary, etc.).
    gt_valid_pages = set()
    for t in gt_logical_tables:
        gt_valid_pages.update(t.get("pages_spanned", []))
        
    useful_pred_tables_details = []
    useless_pred_tables_details = []
    
    for pt in pred_logical_tables:
        pred_pages = set(pt.get("pages_spanned", []))
        desc = pt.get("description", f"Table {pt.get('table_id')}")
        
        if pred_pages.intersection(gt_valid_pages):
            useful_pred_tables_details.append(desc)
        else:
            useless_pred_tables_details.append(desc)

    gt_total_tables = len(gt_logical_tables)
    useful_pred_tables_count = len(useful_pred_tables_details)
    
    # Number of tables that are useful but exceed the GT count
    # indicating fragmentation: tables that should be one but span multiple pages
    fragmentation_extra = max(0, useful_pred_tables_count - gt_total_tables)

    tables_metrics = {
        "expected_logical_tables": gt_total_tables,
        "extracted_useful_tables_count": useful_pred_tables_count,
        "extracted_useful_tables_list": useful_pred_tables_details,
        "useless_tables_noise_count": len(useless_pred_tables_details),
        "useless_tables_noise_list": useless_pred_tables_details,
        "fragmentation_extra_fragments": fragmentation_extra
    }

    gt_headers_sequence = []
    for t in gt_logical_tables:
        gt_headers_sequence.extend(flatten_headers(t.get("headers", {})))
        
    pred_headers_sequence = []
    for t in pred_logical_tables:
        pred_headers_sequence.extend(flatten_headers(t.get("headers", {})))

    exact_ordered_matches = 0
    header_accuracy = 0.0
    
    if gt_headers_sequence:
        sm = difflib.SequenceMatcher(None, gt_headers_sequence, pred_headers_sequence)
        exact_ordered_matches = sum(block.size for block in sm.get_matching_blocks())
        header_accuracy = (exact_ordered_matches / len(gt_headers_sequence)) * 100

    header_metrics = {
        "expected_sequence_length": len(gt_headers_sequence),
        "predicted_sequence_length": len(pred_headers_sequence),
        "perfectly_aligned_columns": exact_ordered_matches,
        "alignment_score_percentage": round(header_accuracy, 1)
    }

    gt_dict = {str(item["lot_id"]): set(str(s) for s in item.get("sublots", [])) for item in ground_truth.get("hierarchy", [])}
    pred_dict = {str(item["lot_id"]): set(str(s) for s in item.get("sublots", [])) for item in predicted.get("hierarchy", [])}

    missing_lots = []
    hierarchy_losses_details = [] 
    correct_sublots = 0
    total_gt_sublots = 0

    for lot_id, gt_sublots in gt_dict.items():
        total_gt_sublots += len(gt_sublots)
        if lot_id not in pred_dict:
            missing_lots.append(lot_id)
            if gt_sublots:
                hierarchy_losses_details.append(f"Lot {lot_id} missing completely -> Lost Sublots: {list(gt_sublots)}")
        else:
            pred_sublots = pred_dict[lot_id]
            missing_sub = gt_sublots - pred_sublots
            correct_sub = gt_sublots.intersection(pred_sublots)
            correct_sublots += len(correct_sub)
            if missing_sub:
                hierarchy_losses_details.append(f"Lot {lot_id} found -> But missing Sublots: {list(missing_sub)}")

    total_gt_lots = len(gt_dict)
    found_lots = total_gt_lots - len(missing_lots)
    lot_recall = (found_lots / total_gt_lots) * 100 if total_gt_lots > 0 else 0
    sublot_accuracy = (correct_sublots / total_gt_sublots) * 100 if total_gt_sublots > 0 else 0

    hierarchy_metrics = {
        "lots_expected": total_gt_lots,
        "lots_found": found_lots,
        "lot_recall_percentage": round(lot_recall, 1),
        "missing_lots_ids": missing_lots,
        "sublots_expected": total_gt_sublots,
        "sublots_mapped_correctly": correct_sublots,
        "sublot_hierarchy_score_percentage": round(sublot_accuracy, 1),
        "hierarchy_losses_details": hierarchy_losses_details
    }

    report_dict = {
        "tables_and_fragmentation": tables_metrics,
        "header_integrity": header_metrics,
        "hierarchy_and_entities": hierarchy_metrics
    }
    
    raw_metrics = {
        "gt_tables": gt_total_tables,
        "frag_extra": fragmentation_extra,
        "gt_headers_len": len(gt_headers_sequence),
        "aligned_headers": exact_ordered_matches,
        "gt_lots": total_gt_lots,
        "found_lots": found_lots,
        "gt_sublots": total_gt_sublots,
        "correct_sublots": correct_sublots
    }
    
    return report_dict, raw_metrics

def init_global_metrics():
    return {
        "gt_tables": 0, "frag_extra": 0,
        "gt_headers_len": 0, "aligned_headers": 0,
        "gt_lots": 0, "found_lots": 0,
        "gt_sublots": 0, "correct_sublots": 0
    }

def update_global_metrics(global_m, local_m):
    for k in global_m.keys():
        global_m[k] += local_m[k]

def build_global_summary_dict(global_m):
    h_acc = (global_m['aligned_headers'] / global_m['gt_headers_len']) * 100 if global_m['gt_headers_len'] > 0 else 0
    l_acc = (global_m['found_lots'] / global_m['gt_lots']) * 100 if global_m['gt_lots'] > 0 else 0
    s_acc = (global_m['correct_sublots'] / global_m['gt_sublots']) * 100 if global_m['gt_sublots'] > 0 else 0
    
    return {
        "global_fragmentation": {
            "total_expected_tables": global_m['gt_tables'],
            "total_extra_fragments": global_m['frag_extra']
        },
        "global_header_alignment": {
            "total_expected_columns": global_m['gt_headers_len'],
            "total_aligned_columns": global_m['aligned_headers'],
            "global_alignment_score_percentage": round(h_acc, 1)
        },
        "global_hierarchy_recall": {
            "total_lots_expected": global_m['gt_lots'],
            "total_lots_found": global_m['found_lots'],
            "global_lot_recall_percentage": round(l_acc, 1),
            "total_sublots_expected": global_m['gt_sublots'],
            "total_sublots_mapped": global_m['correct_sublots'],
            "global_sublot_hierarchy_score_percentage": round(s_acc, 1)
        }
    }

if __name__ == "__main__":
    if not os.path.exists(GROUND_TRUTH_DIR):
        print(f"Directory not found: {GROUND_TRUTH_DIR}")
        exit()

    global_baseline = init_global_metrics()
    global_custom = init_global_metrics()
    processed_files = 0

    for filename in os.listdir(GROUND_TRUTH_DIR):
        if not filename.lower().endswith('.json'):
            continue
            
        print(f"Evaluating Document: {filename}")
        
        gt_path = os.path.join(GROUND_TRUTH_DIR, filename)
        docling_path = os.path.join(DOCLING_DIR, filename)
        plumber_path = os.path.join(PLUMBER_DIR, filename)

        gt = load_json(gt_path)
        if not gt:
            continue
            
        docling_pred = load_json(docling_path)
        plumber_pred = load_json(plumber_path)
        
        # Structure for the individual document report
        doc_report = {
            "document_name": filename,
            "methods": {}
        }
        
        if docling_pred:
            doc_dict, raw_docling = calculate_metrics(gt, docling_pred)
            doc_report["methods"]["baseline_docling"] = doc_dict
            update_global_metrics(global_baseline, raw_docling)
        else:
            print(f"  -> Missing baseline prediction for {filename}")
            
        if plumber_pred:
            plumber_dict, raw_plumber = calculate_metrics(gt, plumber_pred)
            doc_report["methods"]["custom_pipeline"] = plumber_dict
            update_global_metrics(global_custom, raw_plumber)
        else:
            print(f"  -> Missing custom prediction for {filename}")
            
        # Save individual report as JSON
        with open(os.path.join(REPORTS_OUT_DIR, filename), 'w', encoding='utf-8') as f:
            json.dump(doc_report, f, indent=4, ensure_ascii=False)
            
        processed_files += 1

    # Save Global Summary as JSON
    if processed_files > 0:
        global_report = {
            "total_documents_evaluated": processed_files,
            "systems_summary": {
                "baseline_docling": build_global_summary_dict(global_baseline),
                "custom_pipeline": build_global_summary_dict(global_custom)
            }
        }
        
        with open(os.path.join(REPORTS_OUT_DIR, "GLOBAL_SUMMARY_REPORT.json"), 'w', encoding='utf-8') as f:
            json.dump(global_report, f, indent=4, ensure_ascii=False)
            
        print(f"\nAll reports successfully saved as JSON to: {REPORTS_OUT_DIR}")
    else:
        print("No files were evaluated.")