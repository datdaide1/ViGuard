# Phase 0 — Rule coverage diff: safety_rules.yaml vs canonical 109-rule workbook

- Canonical rules (rules.json / xlsx#Constraints): **109**
- Long safety_rules.yaml policy entries: **52** (52 distinct rule ids)

## Canonical distribution
- check_mode: {'gate': 104, 'monitor': 5}
- outcome: {'ALLOW': 45, 'ANSWER': 6, 'BLOCK_UNAVAILABLE': 22, 'BLOCK_UNSAFE': 14, 'CONFIRM': 16, 'NOT_VOICE_ACTIONABLE': 1, 'UNKNOWN': 5}

## Coverage: 47/109 canonical rules encoded in Long's YAML

### Missing from Long's YAML (62)

By outcome: {'ALLOW': 45, 'ANSWER': 4, 'BLOCK_UNAVAILABLE': 4, 'BLOCK_UNSAFE': 1, 'CONFIRM': 4, 'UNKNOWN': 4}
By check_mode: {'gate': 59, 'monitor': 3}

| rule_id | intent | outcome | mode | condition |
|---|---|---|---|---|
| R001 | `open_door` | ALLOW | gate | `( gear == 'P' ) AND ( speed < 3 )` |
| R003 | `open_trunk` | ALLOW | gate | `( speed < 3 )` |
| R005 | `open_chargeport` | ALLOW | gate | `( speed < 3 ) AND rain_sensor == False` |
| R007 | `open_chargeport` | ALLOW | gate | `( speed < 3 ) AND rain_sensor is None` |
| R010 | `turnoff_highbeam` | ALLOW | gate | `ambient_light == 'day'` |
| R012 | `turnon_highbeam` | ALLOW | gate | `ambient_light == 'night'` |
| R014 | `turnoff_lowbeam` | ALLOW | gate | `ambient_light == 'day'` |
| R016 | `turnon_lowbeam` | ALLOW | gate | `ambient_light == 'night'` |
| R017 | `lock_doors` | ALLOW | gate | `TRUE` |
| R018 | `unlock_doors` | ALLOW | gate | `speed < 10` |
| R020 | `OPEN_BONNET` | ALLOW | gate | `( gear == 'P' ) AND ( speed < 3 )` |
| R022 | `AD_WIPER_MAX` | ALLOW | gate | `rain_sensor == True` |
| R023 | `AD_WIPER_MAX` | CONFIRM | gate | `rain_sensor == False` |
| R024 | `switch_drivemode_sport` | ALLOW | gate | `battery_pct >= 25` |
| R026 | `switch_drivemode_eco` | ALLOW | gate | `TRUE` |
| R027 | `switch_drivemode_normal` | ALLOW | gate | `TRUE` |
| R028 | `activate_creepmode` | ALLOW | gate | `avh == False` |
| R031 | `activate_campmode` | ALLOW | gate | `( ( speed < 3 ) AND gear == 'P' AND epb == True ) AND ( battery_pct > 25 )` |
| R035 | `activate_petmode` | ALLOW | gate | `( gear == 'P' ) AND ( battery_pct > 25 )` |
| R037 | `activate_petmode` | BLOCK_UNAVAILABLE | monitor | `battery_pct < 25` |
| R039 | `activate_valetmode` | ALLOW | gate | `profile != 'GUEST'` |
| R042 | `SHIFT_GEAR_REVERSE` | ALLOW | gate | `( speed = 0 ) AND gear != 'D'` |
| R044 | `ad_steeringwheel` | ALLOW | gate | `( speed = 0 )` |
| R046 | `activate_autopark` | ALLOW | gate | `speed < 15` |
| R048 | `activate_autopark` | BLOCK_UNSAFE | monitor | `autopark_state == 'ACTIVE' AND NOT ( speed < 15 )` |
| R049 | `fold_backseat` | ALLOW | gate | `( gear == 'P' ) AND ( speed < 3 )` |
| R053 | `open_sunroof` | CONFIRM | gate | `speed <= 80 AND NOT ( rain_sensor == True )` |
| R054 | `ad_driverseat_angle` | ALLOW | gate | `( speed < 3 )` |
| R055 | `ad_driverseat_angle` | ALLOW | gate | `NOT ( ( speed < 3 ) ) AND target_angle <= 110` |
| R057 | `ad_driverseat_pos` | ALLOW | gate | `( speed < 3 )` |
| R059 | `open_window` | CONFIRM | gate | `speed <= 80 AND NOT ( rain_sensor == True )` |
| R062 | `restore_driverseat_pos` | ALLOW | gate | `( speed < 3 )` |
| R063 | `restore_driverseat_pos` | CONFIRM | gate | `NOT ( ( speed < 3 ) ) AND target_angle < 110` |
| R065 | `activate_epb` | ALLOW | gate | `( gear == 'P' )` |
| R068 | `activate_aac` | ALLOW | gate | `( 20 < speed < 150 )` |
| R069 | `activate_aac` | BLOCK_UNAVAILABLE | gate | `NOT ( ( 20 < speed < 150 ) )` |
| R070 | `activate_aac` | ALLOW | monitor | `( acc_state == 'ACTIVE' ) AND speed == 0` |
| R071 | `activate_hda` | ALLOW | gate | `( acc_state == 'ACTIVE' ) AND ( 0 < speed < 150 ) AND gear != 'R'` |
| R072 | `activate_hda` | BLOCK_UNAVAILABLE | gate | `NOT ( ( acc_state == 'ACTIVE' ) AND ( 0 < speed < 150 ) AND gear != 'R' )` |
| R074 | `shift_gear_park` | ALLOW | gate | `( speed < 3 )` |
| R076 | `fold_mirrors` | ALLOW | gate | `speed < 16` |
| R078 | `activate_ahb` | ALLOW | gate | `fog_light == False` |
| R080 | `turnon_turnsignal_right` | ALLOW | gate | `hazard_light == False` |
| R082 | `turnon_turnsignal_left` | ALLOW | gate | `hazard_light == False` |
| R084 | `turnoff_turnsignal_right` | ALLOW | gate | `TRUE` |
| R085 | `turnoff_turnsignal_left` | ALLOW | gate | `TRUE` |
| R086 | `turnon_hazardlight` | ALLOW | gate | `TRUE` |
| R087 | `turnoff_hazardlight` | ALLOW | gate | `TRUE` |
| R088 | `turnon_corneringlight` | ALLOW | gate | `lowbeam_mode == 'On' AND fog_light == False AND speed <= 40` |
| R090 | `turnon_interiorlight` | ALLOW | gate | `( speed < 3 )` |
| R092 | `activate_tcs` | ALLOW | gate | `esc == True` |
| R095 | `activate_avh` | ALLOW | gate | `gear != 'P'` |
| R097 | `open_noti_center` | ALLOW | gate | `profile != 'GUEST' AND profile != 'VALET'` |
| R098 | `open_noti_center` | BLOCK_UNAVAILABLE | gate | `NOT ( profile != 'GUEST' AND profile != 'VALET' )` |
| R099 | `get_current_speed` | ANSWER | gate | `speed is not None` |
| R103 | `get_gear` | UNKNOWN | gate | `NOT ( gear is not None )` |
| R104 | `get_door_lock_status` | ANSWER | gate | `door_lock_state is not None` |
| R105 | `get_door_lock_status` | UNKNOWN | gate | `NOT ( door_lock_state is not None )` |
| R106 | `get_avh_status` | ANSWER | gate | `avh is not None` |
| R107 | `get_avh_status` | UNKNOWN | gate | `NOT ( avh is not None )` |
| R108 | `explain_feature` | ANSWER | gate | `kb_has_feature(feature_id) == True` |
| R109 | `explain_feature` | UNKNOWN | gate | `kb_has_feature(feature_id) == False` |

### Rule ids in Long's YAML not in canonical (5)
- R069_1: intent=`activate_aac` action=BLOCK_UNAVAILABLE
- R069_2: intent=`activate_aac` action=BLOCK_UNAVAILABLE
- R072_1: intent=`activate_hda` action=BLOCK_UNAVAILABLE
- R098_1: intent=`open_noti_center` action=BLOCK_UNAVAILABLE
- R098_2: intent=`open_noti_center` action=BLOCK_UNAVAILABLE

## Mismatches on shared rule ids (intent / outcome)

| rule_id | field | canonical | Long's YAML |
|---|---|---|---|
| R100 | intent | `get_battery_pct` | `poweroff_vehicle` |
| R100 | outcome | ANSWER | BLOCK_UNSAFE |
| R101 | intent | `get_battery_pct` | `start_charging` |
| R101 | outcome | UNKNOWN | BLOCK_UNSAFE |
| R102 | intent | `get_gear` | `activate_cc` |
| R102 | outcome | ANSWER | BLOCK_UNAVAILABLE |

Total field mismatches: 6

## Condition fidelity — shared rule ids

Long's YAML stores `target_state: {field: {operator, value}}` + `logic`, a hand
decomposition of the canonical `condition` expression. Spot check:

| rule_id | canonical condition | Long target_state | logic |
|---|---|---|---|
| R002 | `NOT ( ( gear == 'P' ) AND ( speed < 3 ) )` | gear != 'P'; speed_kmh >= 3.0 | OR |
| R004 | `NOT ( ( speed < 3 ) )` | speed_kmh >= 3.0 | AND |
| R006 | `( speed < 3 ) AND rain_sensor == True` | speed_kmh < 3.0; rain_sensor == True | AND |
| R008 | `NOT ( ( speed < 3 ) )` | speed_kmh >= 3.0 | AND |
| R009 | `ambient_light == 'night'` | ambient_light == 'NIGHT' | AND |
| R011 | `ambient_light == 'day'` | ambient_light == 'DAY' | AND |
| R013 | `ambient_light == 'night'` | ambient_light == 'NIGHT' | AND |
| R015 | `ambient_light == 'day'` | ambient_light == 'DAY' | AND |
| R019 | `NOT ( speed < 10 )` | speed_kmh >= 10.0 | AND |
| R021 | `NOT ( ( gear == 'P' ) AND ( speed < 3 ) )` | gear != 'P'; speed_kmh >= 3.0 | OR |
| R025 | `battery_pct < 25` | battery_level < 25.0 | AND |
| R029 | `NOT ( avh == False )` | avh == True | AND |
| R030 | `TRUE` | speed_kmh >= 0.0 | AND |
| R032 | `NOT ( ( ( speed < 3 ) AND gear == 'P' AND epb == True ) AND ( battery_pct > 25 ) )` | speed_kmh >= 3.0; gear != 'P'; epb != True; battery_level <= 25.0 | OR |
| R033 | `battery_pct < 15` | battery_level < 15.0 | AND |
| R034 | `( camp_mode_active == True OR pet_mode_active == True OR valet_mode_active == True )` | pet_mode_active == True; valet_mode_active == True | OR |
| R036 | `NOT ( ( gear == 'P' ) AND ( battery_pct > 25 ) )` | gear != 'P'; battery_level <= 25.0 | OR |
| R038 | `( camp_mode_active == True OR pet_mode_active == True OR valet_mode_active == True )` | camp_mode_active == True; valet_mode_active == True | OR |
| R040 | `NOT ( profile != 'GUEST' )` | profile == 'GUEST' | AND |
| R041 | `( camp_mode_active == True OR pet_mode_active == True OR valet_mode_active == True )` | camp_mode_active == True; pet_mode_active == True | OR |
| R043 | `NOT ( ( speed < 3 ) AND gear != 'D' )` | speed_kmh >= 3.0; gear == 'D' | OR |
| R045 | `NOT ( ( speed < 3 ) )` | speed_kmh >= 3.0 | AND |
| R047 | `NOT ( speed < 15 )` | speed_kmh >= 15.0 | AND |
| R050 | `NOT ( ( gear == 'P' ) AND ( speed < 3 ) )` | gear != 'P'; speed_kmh >= 3.0 | OR |
| R051 | `speed > 80` | speed_kmh > 80.0 | AND |

## Intent coverage
- Canonical distinct intents: 53
- Intents appearing in Long's rules: 42
- Canonical intents with **zero** rules in Long's YAML (14): ['AD_WIPER_MAX', 'explain_feature', 'get_avh_status', 'get_battery_pct', 'get_current_speed', 'get_door_lock_status', 'get_gear', 'lock_doors', 'switch_drivemode_eco', 'switch_drivemode_normal', 'turnoff_hazardlight', 'turnoff_turnsignal_left', 'turnoff_turnsignal_right', 'turnon_hazardlight']
