# Phase 1' — TF-IDF T2 candidate (trained on golden pool, evaluated on FROZEN)

> `vf_guardrails/evals/run_t2.py` · 2026-09-07 10:56
> train: 2313 golden-pool rows · fit 0.4s · infer p50/p99 1.04/3.71 ms
> eval: 530 frozen rows (424 positive + 106 hard-negative)
> working model = **SVC · char2-5 + word1-2**

## Baseline

| classifier | all | positive | hard-neg |
|---|---|---|---|
| T1 only (keywords) | 53.4% | 58.3% | 34.0% |

## TF-IDF variant comparison (no abstain, frozen)

| variant | all | positive | hard-neg | fit s |
|---|---|---|---|---|
| SVC · char3-5 + word1-2 | **87.9%** | 90.6% | 77.4% | 0.3 |
| SVC · char3-5 only | **87.0%** | 90.1% | 74.5% | 0.2 |
| SVC · char2-5 + word1-2 | **88.3%** | 91.0% | 77.4% | 0.4 |
| LogReg · char3-5 + word1-2 | **87.4%** | 90.3% | 75.5% | 3.3 |

## TF-IDF T2 standalone (frozen)

| abstain config | all | positive | hard-neg | UNKNOWN rate |
|---|---|---|---|---|
| no-abstain | **88.3%** | 91.0% | 77.4% | 0% |
| margin>=0.2 | **83.6%** | 87.0% | 69.8% | 10% |
| margin>=0.4 | **77.7%** | 81.8% | 61.3% | 18% |
| score>=0 & margin>=0.3 | **73.2%** | 75.7% | 63.2% | 24% |

## T1 → TF-IDF T2 cascade (T2 fires only when T1 = INTENT_UNKNOWN)

| abstain config | all | positive | hard-neg |
|---|---|---|---|
| no-abstain | **85.7%** | 88.2% | 75.5% |
| margin>=0.2 | **83.4%** | 86.6% | 70.8% |
| margin>=0.4 | **80.9%** | 84.7% | 66.0% |
| score>=0 & margin>=0.3 | **78.3%** | 81.1% | 67.0% |

## Context — golden-pool CV, group-by-rule_id (PESSIMISTIC bound)

Holding out a whole rule's ~20 near-duplicate utterances removes the worst
leakage, but for the many single-rule intents it also removes the *entire*
intent from training → those fold rows score 0. So this is a lower bound,
not the real number. The **frozen set (above) is the number to trust.**

- SVC · char2-5 + word1-2: **77.6%** (folds 73%, 81%, 90%, 79%, 65%)

## TF-IDF T2 (no-abstain) top confusions on frozen

| true | predicted | n |
|---|---|---|
| `unlock_doors` | `get_door_lock_status` | 6 |
| `lock_doors` | `get_door_lock_status` | 4 |
| `activate_tcs` | `deactivate_esc` | 2 |
| `activate_avh` | `activate_autopark` | 2 |
| `shift_gear_park` | `get_gear` | 2 |
| `restore_driverseat_pos` | `ad_driverseat_angle` | 2 |
| `turnon_turnsignal_left` | `turnon_hazardlight` | 2 |
| `get_door_lock_status` | `unlock_doors` | 2 |
| `get_avh_status` | `activate_autopark` | 2 |
| `explain_feature` | `turnoff_LKA` | 2 |
| `open_door` | `open_sunroof` | 1 |
| `open_door` | `open_trunk` | 1 |
| `open_trunk` | `unlock_doors` | 1 |
| `open_trunk` | `OPEN_BONNET` | 1 |
| `open_trunk` | `fold_backseat` | 1 |
| `lock_doors` | `fold_backseat` | 1 |
| `unlock_doors` | `ad_steeringwheel` | 1 |
| `activate_ahb` | `activate_autopark` | 1 |
| `activate_ahb` | `activate_aac` | 1 |
| `turnon_corneringlight` | `turnon_lowbeam` | 1 |

---
> Số liệu tự sinh. Diễn giải + kết luận: `docs/guardrail-integration/STATUS.md`.
