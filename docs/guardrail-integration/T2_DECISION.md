# T2 intent classifier — so sánh & quyết định

**Ngày:** 2026-09-07 · **Trạng thái: CHỐT — chọn TF-IDF.**

Đo trên **frozen independent test set** (530 dòng). Train (nếu có) trên golden
pool 2.313 dòng. Không đo trên split của golden pool (leakage — xem
`memory: no-cv-on-golden-pool-leakage`).

---

## 1. Số liệu (frozen)

| Classifier | all | positive | hard-neg | infer | Deps |
|---|---|---|---|---|---|
| T1 (keyword Aho-Corasick, không train) | 53.4% | 58.3% | 34.0% | ~0.01 ms | `pyahocorasick` |
| **T2 — TF-IDF + LinearSVC** (char2-5 + word1-2) | **88.3%** | **91.0%** | 77.4% | ~1 ms | `scikit-learn` |
| T2 — TF-IDF char-only | 87.0% | 90.1% | 74.5% | ~1 ms | `scikit-learn` |
| T2 — TF-IDF + LogisticRegression | 87.4% | 90.3% | 75.5% | ~1 ms | `scikit-learn` |
| **T2 — PhoBERT emb + LinearSVC** | **79.2%** | 80.2% | 75.5% | ~7 ms (GPU) | `torch`+`transformers`+`pyvi`, model 500 MB |
| T1 → T2(TF-IDF) cascade | 85.7% | 88.2% | 75.5% | | |

Golden-pool CV group-by-rule_id (chặn dưới bi quan, intent 1-rule bị bỏ hẳn khỏi train): ~78%.

Chi tiết: `METRICS_PHASE1_T2.md` (TF-IDF), `METRICS_PHASE1_T2_PHOBERT.md` (PhoBERT),
`METRICS_PHASE1_FROZEN.md` (T1).

## 2. Kết luận: **TF-IDF thắng rõ**

- **Chính xác hơn ~9 điểm** (88.3% vs 79.2%) trên tập độc lập.
- **Nhẹ hơn:** chỉ `scikit-learn`, không torch/transformers/model 500 MB.
- **Nhanh hơn ~7–50×**, chạy mọi máy (PhoBERT cần venv CUDA riêng — CPU torch
  `c10.dll` hỏng trên máy này).
- Rơi vào đúng ô "PhoBERT ≤ TF-IDF" của khung quyết định → **chọn TF-IDF**.

**Vì sao PhoBERT thua:** `dangvantuan/vietnamese-embedding` là model similarity
tổng quát, chưa fine-tune. Nó *làm mờ* đúng những phân biệt quan trọng ở đây —
confusion của PhoBERT dồn vào `turnoff_lowbeam ↔ turnoff_highbeam` (4),
`turnon_highbeam ↔ turnoff_highbeam` (3): "đèn pha" và "đèn cốt" gần nhau về
nghĩa nhưng là intent khác. Char n-gram của TF-IDF bắt thẳng token phân biệt
("cốt" vs "pha", "capo" vs "cốp", "xi nhan trái" vs "phải").

## 3. Phát hiện phụ (ảnh hưởng tích hợp Pha 2′/3′)

1. **T2 standalone (88.3%) > T1→T2 cascade (85.7%).** T1 trả lời chắc-nhưng-sai
   ~2.6 điểm. → Kiến trúc "T1 trước, T2 fallback" (PRD FR-03) **không tối ưu**
   với bộ keyword T1 hiện tại.
   **Khuyến nghị:** **T2 (TF-IDF) làm primary.** T1 hạ vai trò: chỉ dùng để
   *xác nhận* / *tăng confidence* khi T1 và T2 đồng ý, hoặc bỏ hẳn (đo lại khi
   dọn Pha 1′). T3 SLM vẫn hoãn (D5).
2. **Abstain đắt.** Không abstain cho accuracy tốt nhất. `margin≥0.2` →
   83.6% + 10% UNKNOWN. Chỉ bật nếu downstream thực sự cần "thà hỏi lại".
   Guardrail spec FR-03 muốn có threshold+margin → giữ cơ chế trong code
   (`T2Config`) nhưng để mặc định no-abstain, cấu hình được.
3. **Lỗi còn lại của TF-IDF** dồn vào cặp **câu-hỏi ↔ lệnh**:
   `unlock_doors`/`lock_doors` ↔ `get_door_lock_status` (10),
   `activate_tcs` ↔ `deactivate_esc`, `shift_gear_park` ↔ `get_gear`. Mơ hồ
   ngữ nghĩa thật (trật tự từ / ngữ điệu). Hướng cải thiện sau: thêm sample
   golden cho các cặp này, hoặc 1 rule hậu-xử-lý (câu có "?" / "chưa" / "hay" ở
   cuối → nghiêng về `get_*`).

## 4. Việc tiếp theo

- **T2 = TF-IDF `char2-5 + word1-2 + LinearSVC`**, no-abstain, **primary**.
  Đóng gói vào `vf_guardrails/classifier/` (đã có), thêm hàm train + lưu model
  (pickle) để Pha 2′ nạp.
- Bước 3 (dọn Pha 1′): thay classifier trong `vf_guardrails/src/guardrail.py`
  bằng `policy/` engine + `classifier/` TF-IDF (T2 primary, T1 phụ/bỏ). Xoá
  `safety_engine.py` + `safety_rules.yaml` + `src/agent.py` + `app_sim.py`.
- venv `.venv-phobert/` (~6 GB, gitignored): giữ để re-run `run_t2_phobert.py`
  hoặc xoá — số PhoBERT đã ghi lại, không cần nữa.

## 5. Chạy lại

```bash
py -3 vf_guardrails/evals/run_frozen.py          # T1
py -3 vf_guardrails/evals/run_t2.py              # TF-IDF (chính)
.venv-phobert\Scripts\python vf_guardrails/evals/run_t2_phobert.py   # PhoBERT (đối chứng)
```
