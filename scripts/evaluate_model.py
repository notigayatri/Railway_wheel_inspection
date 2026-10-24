import json
import time
from pathlib import Path
import numpy as np
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run_evaluation():
    model_path = PROJECT_ROOT / "models" / "best.pt"
    data_yaml = PROJECT_ROOT / "training_data" / "eval_data.yaml"
    
    print("=" * 70)
    print("  Chakraksh (चक्राक्ष) • Wheel Defect Detection Model Benchmark")
    print(f"  Model Weights: {model_path}")
    print(f"  Evaluation Dataset: {data_yaml}")
    print("=" * 70)
    
    model = YOLO(str(model_path))
    
    # Run official Ultralytics Validation on the test split
    print("\n[INFO] Running YOLOv8 validation on held-out test split (split='test')...")
    t0 = time.perf_counter()
    metrics = model.val(
        data=str(data_yaml),
        split="test",
        conf=0.25,
        iou=0.6,
        plots=True,
        save_json=False,
        project=str(PROJECT_ROOT / "outputs" / "evaluation"),
        name="test_eval",
        exist_ok=True,
        verbose=True
    )
    t_val = time.perf_counter() - t0
    
    box_metrics = metrics.box
    has_seg = hasattr(metrics, "seg") and metrics.seg is not None
    seg_metrics = metrics.seg if has_seg else None
    
    class_names = model.names
    test_img_dir = PROJECT_ROOT / "training_data" / "Labeled_data_TXT" / "test" / "images"
    test_images_list = sorted(list(test_img_dir.glob("*.jpg")))
    
    results_summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_images": len(test_images_list),
        "inference_speed_ms": metrics.speed,
        "overall": {
            "box_precision": float(box_metrics.mp),
            "box_recall": float(box_metrics.mr),
            "box_map50": float(box_metrics.map50),
            "box_map50_95": float(box_metrics.map),
            "box_f1": float(2 * (box_metrics.mp * box_metrics.mr) / max(box_metrics.mp + box_metrics.mr, 1e-6)),
        },
        "per_class": {}
    }
    
    if has_seg:
        results_summary["overall"]["seg_map50"] = float(seg_metrics.map50)
        results_summary["overall"]["seg_map50_95"] = float(seg_metrics.map)
        results_summary["overall"]["seg_precision"] = float(seg_metrics.mp)
        results_summary["overall"]["seg_recall"] = float(seg_metrics.mr)
    
    # Per-class breakdown
    for idx, name in class_names.items():
        if idx < len(box_metrics.p):
            p = float(box_metrics.p[idx])
            r = float(box_metrics.r[idx])
            map50 = float(box_metrics.ap50[idx])
            map50_95 = float(box_metrics.ap[idx])
            f1 = 2 * (p * r) / max(p + r, 1e-6)
            
            class_entry = {
                "class_id": idx,
                "class_name": name,
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1_score": round(f1, 4),
                "map50": round(map50, 4),
                "map50_95": round(map50_95, 4),
            }
            if has_seg and idx < len(seg_metrics.ap50):
                class_entry["seg_map50"] = round(float(seg_metrics.ap50[idx]), 4)
                class_entry["seg_map50_95"] = round(float(seg_metrics.ap[idx]), 4)
                
            results_summary["per_class"][name] = class_entry

    # Detailed image-by-image audit
    test_img_dir = PROJECT_ROOT / "training_data" / "Labeled_data_TXT" / "test" / "images"
    test_lbl_dir = PROJECT_ROOT / "training_data" / "Labeled_data_TXT" / "test" / "labels"
    image_audits = []
    
    print("\n[INFO] Running detailed image-by-image verification...")
    for img_file in sorted(test_img_dir.glob("*.jpg")):
        lbl_file = test_lbl_dir / f"{img_file.stem}.txt"
        
        gt_classes = []
        if lbl_file.exists():
            with open(lbl_file, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        cls_id = int(parts[0])
                        gt_classes.append(class_names.get(cls_id, f"Class_{cls_id}"))
                        
        pred_res = model(str(img_file), conf=0.25, verbose=False)[0]
        pred_detections = []
        for box in pred_res.boxes:
            cid = int(box.cls[0])
            cname = class_names.get(cid, f"Class_{cid}")
            conf = float(box.conf[0])
            pred_detections.append({"class": cname, "confidence": round(conf, 3)})
            
        pred_class_counts = {}
        for d in pred_detections:
            pred_class_counts[d["class"]] = pred_class_counts.get(d["class"], 0) + 1
            
        gt_class_counts = {}
        for c in gt_classes:
            gt_class_counts[c] = gt_class_counts.get(c, 0) + 1
            
        image_audits.append({
            "image": img_file.name,
            "ground_truth_counts": gt_class_counts,
            "predicted_counts": pred_class_counts,
            "predictions": pred_detections,
            "inference_time_ms": round(pred_res.speed["inference"], 1),
        })

    results_summary["image_audits"] = image_audits

    # Save structured JSON
    out_dir = PROJECT_ROOT / "outputs" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = out_dir / "benchmark_report.json"
    with open(report_json_path, "w") as f:
        json.dump(results_summary, f, indent=2)
        
    print(f"\n[SUCCESS] Benchmark completed in {t_val:.2f}s!")
    print(f"[SUCCESS] Report saved to: {report_json_path}")
    
    # Print formatted markdown summary
    print("\n" + "=" * 70)
    print("  MODEL EVALUATION & BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"  Precision (BBox):  {results_summary['overall']['box_precision']:.3f}")
    print(f"  Recall (BBox):     {results_summary['overall']['box_recall']:.3f}")
    print(f"  mAP@50 (BBox):     {results_summary['overall']['box_map50']:.3f}")
    print(f"  mAP@50-95 (BBox):  {results_summary['overall']['box_map50_95']:.3f}")
    print(f"  F1-Score:          {results_summary['overall']['box_f1']:.3f}")
    if has_seg:
        print(f"  mAP@50 (Mask):     {results_summary['overall']['seg_map50']:.3f}")
        print(f"  mAP@50-95 (Mask):  {results_summary['overall']['seg_map50_95']:.3f}")
    print(f"  Inference Speed:   {metrics.speed['inference']:.1f} ms/image ({1000/max(metrics.speed['inference'], 1):.1f} FPS)")
    print("-" * 70)
    print("  Per-Class Metrics:")
    for name, c in results_summary["per_class"].items():
        print(f"    - {name:<18}: P={c['precision']:.3f} | R={c['recall']:.3f} | mAP@50={c['map50']:.3f} | F1={c['f1_score']:.3f}")
    print("=" * 70)
    
    return results_summary

if __name__ == "__main__":
    run_evaluation()
