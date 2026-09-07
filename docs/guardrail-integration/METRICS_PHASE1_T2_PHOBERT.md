# Phase 1' — PhoBERT T2 candidate (trained on golden pool, evaluated on FROZEN)

> `vf_guardrails/evals/run_t2_phobert.py` · 2026-09-07 10:39 · model `dangvantuan/vietnamese-embedding` · embed 4s
> eval: 530 frozen rows (424 positive + 106 hard-negative)
> Classifier head = LinearSVC on sentence embeddings (same head as the TF-IDF candidate).

| metric | value |
|---|---|
| **intent accuracy (all)** | **79.2%** |
| positive only | 80.2% |
| hard-negative only | 75.5% |

## Top confusions on frozen

| true | predicted | n |
|---|---|---|
| `turnoff_lowbeam` | `turnoff_highbeam` | 4 |
| `lock_doors` | `get_door_lock_status` | 3 |
| `turnon_highbeam` | `turnoff_highbeam` | 3 |
| `get_door_lock_status` | `unlock_doors` | 3 |
| `get_avh_status` | `activate_avh` | 3 |
| `open_door` | `open_trunk` | 2 |
| `open_door` | `open_sunroof` | 2 |
| `unlock_doors` | `get_door_lock_status` | 2 |
| `turnon_lowbeam` | `turnon_highbeam` | 2 |
| `activate_aac` | `activate_creepmode` | 2 |
| `ad_driverseat_pos` | `ad_driverseat_angle` | 2 |
| `turnoff_turnsignal_right` | `turnoff_highbeam` | 2 |
| `turnoff_turnsignal_right` | `turnoff_LKA` | 2 |
| `get_avh_status` | `activate_creepmode` | 2 |
| `open_door` | `activate_campmode` | 1 |
| `open_door` | `unlock_doors` | 1 |
| `open_trunk` | `fold_backseat` | 1 |
| `lock_doors` | `unlock_doors` | 1 |
| `unlock_doors` | `open_door` | 1 |
| `OPEN_BONNET` | `open_window` | 1 |

---
> So sánh với TF-IDF: `METRICS_PHASE1_T2.md`. Kết luận: `STATUS.md`.
