import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import time

# Bổ sung thư mục gốc của dự án vào sys.path để import src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import VehicleState
from src.guardrail import VinFastGuardrail

def run_benchmark():
    # Tìm đường dẫn đến file test data
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_data_path = os.path.join(base_dir, "data", "vinfast_test_data.json")
    keywords_path = os.path.join(base_dir, "config", "intent_keywords.json")
    rules_path = os.path.join(base_dir, "config", "safety_rules.yaml")

    if not os.path.exists(test_data_path):
        print(f"Error: Test data file not found at {test_data_path}")
        return

    with open(test_data_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    # Khởi tạo Guardrail Engine
    guardrail = VinFastGuardrail(keywords_path, rules_path)

    total_samples = len(test_cases)
    blocked_count = 0
    passed_count = 0
    correct_count = 0
    
    # Các biến tính toán FPR (False Positive Rate)
    # FPR = FP / (FP + TN) = Số lần bị chặn sai (FP) / Tổng số mẫu đáng lẽ phải cho qua (Expected PASS)
    expected_pass_count = 0
    false_positives = 0
    
    total_latency_ms = 0.0
    latencies = []

    print("=" * 80)
    print("RUNNING VINFAST AI GUARDRAIL BENCHMARK ENGINE")
    print("=" * 80)
    print(f"Loaded {total_samples} test samples from {test_data_path}.\n")

    results_table = []
    
    for idx, case in enumerate(test_cases, 1):
        query = case["query"]
        state_dict = case["state"]
        expected_intent = case.get("expected_intent", "")
        expected_action = case.get("expected_action", "PASS")

        state = VehicleState(**state_dict)
        
        # Đo thời gian xử lý thực tế ngoài latency trong result để có cái nhìn độc lập
        t_start = time.perf_counter()
        result = guardrail.process(query, state)
        t_end = time.perf_counter()
        
        latency = (t_end - t_start) * 1000.0
        total_latency_ms += latency
        latencies.append(latency)

        actual_action = result.action
        
        # Thống kê Block / Pass dựa trên các kết quả mở rộng mới
        is_blocked = actual_action.startswith("BLOCK") or actual_action in ["CONFIRM", "NOT_VOICE_ACTIONABLE"]
        
        if is_blocked:
            blocked_count += 1
        else:
            passed_count += 1

        # Kiểm tra dự đoán chính xác
        is_correct = (actual_action == expected_action) or (expected_action in ("PASS", "ALLOW") and actual_action == "ALLOW")
        if is_correct:
            correct_count += 1

        # Tính toán False Positive
        # expected_action có thể là PASS hoặc ALLOW
        is_expected_pass = expected_action in ["PASS", "ALLOW"]
        if is_expected_pass:
            expected_pass_count += 1
            if is_blocked:
                false_positives += 1

        results_table.append([
            idx,
            query[:25] + "..." if len(query) > 25 else query,
            result.intent,
            expected_action,
            actual_action,
            f"{latency:.3f} ms"
        ])

    avg_latency = total_latency_ms / total_samples if total_samples > 0 else 0.0
    block_rate = (blocked_count / total_samples) * 100.0 if total_samples > 0 else 0.0
    fpr = (false_positives / expected_pass_count) * 100.0 if expected_pass_count > 0 else 0.0
    accuracy = (correct_count / total_samples) * 100.0 if total_samples > 0 else 0.0
    
    p90_latency = 0.0
    if latencies:
        sorted_latencies = sorted(latencies)
        idx_p90 = int(len(sorted_latencies) * 0.90)
        p90_latency = sorted_latencies[min(idx_p90, len(sorted_latencies) - 1)]

    # In kết quả chi tiết của từng mẫu test
    headers = ["No.", "Query", "Detected Intent", "Expected", "Actual", "Latency"]
    row_format = "{:<4} | {:<28} | {:<26} | {:<8} | {:<8} | {:<10}"
    print(row_format.format(*headers))
    print("-" * 95)
    for row in results_table:
        print(row_format.format(*row))
    print("-" * 95)

    # In báo cáo tổng kết (Summary Report)
    print("\n" + "=" * 40 + " SUMMARY REPORT " + "=" * 40)
    print(f"Total Test Samples   : {total_samples}")
    print(f"Total PASS Decisions : {passed_count}")
    print(f"Total BLOCK Decisions: {blocked_count}")
    print(f"Block Rate (%)       : {block_rate:.2f}%")
    print(f"Accuracy (%)         : {accuracy:.2f}%")
    print(f"False Positives      : {false_positives} (out of {expected_pass_count} expected PASS)")
    print(f"False Positive Rate  : {fpr:.2f}%")
    print(f"Average Latency      : {avg_latency:.4f} ms")
    print(f"P90 Latency          : {p90_latency:.4f} ms")
    print(f"Max Latency          : {max(latencies):.4f} ms" if latencies else "N/A")
    print(f"Min Latency          : {min(latencies):.4f} ms" if latencies else "N/A")
    print("=" * 96)

if __name__ == "__main__":
    run_benchmark()
