# Engine metrics — intent classifier vs FROZEN independent test set

> `guardrail/evals/run_frozen.py` · 2026-09-07 21:13 · 530 rows (424 positive + 106 hard-negative)
> tiers: **T1 only (T2 model not loaded)**
> Leakage-free: T1 is hand-authored keywords (not trained). A trained T2 must also run here.

| metric | value |
|---|---|
| **intent accuracy (all)** | **283/530 = 53.4%** |
| intent accuracy (positive only) | 247/424 = 58.3% |
| intent accuracy (hard-negative only) | 36/106 = 34.0% |
| macro-F1 | 0.607 |
| INTENT_UNKNOWN rate | 192/530 = 36.2% |
| classifier latency p50 / p95 / p99 | 0.01 / 0.01 / 0.02 ms |

## Per-intent recall (worst 20)

| intent | recall | n |
|---|---|---|
| `get_avh_status` | 0% | 10 |
| `ad_driverseat_pos` | 0% | 10 |
| `restore_driverseat_pos` | 0% | 10 |
| `switch_drivemode_sport` | 0% | 10 |
| `get_door_lock_status` | 0% | 10 |
| `activate_epb` | 10% | 10 |
| `turnon_turnsignal_left` | 20% | 10 |
| `shift_gear_park` | 20% | 10 |
| `explain_feature` | 20% | 10 |
| `turnon_corneringlight` | 20% | 10 |
| `switch_drivemode_eco` | 20% | 10 |
| `unlock_doors` | 30% | 10 |
| `get_gear` | 30% | 10 |
| `turnon_turnsignal_right` | 30% | 10 |
| `switch_drivemode_normal` | 30% | 10 |
| `get_current_speed` | 30% | 10 |
| `activate_creepmode` | 40% | 10 |
| `open_window` | 40% | 10 |
| `activate_autopark` | 40% | 10 |
| `get_battery_pct` | 40% | 10 |

## Top confusions (true → predicted)

| true | predicted | n |
|---|---|---|
| `switch_drivemode_sport` | `INTENT_UNKNOWN` | 9 |
| `activate_epb` | `INTENT_UNKNOWN` | 9 |
| `ad_driverseat_pos` | `INTENT_UNKNOWN` | 9 |
| `get_door_lock_status` | `lock_doors` | 9 |
| `switch_drivemode_eco` | `INTENT_UNKNOWN` | 8 |
| `explain_feature` | `INTENT_UNKNOWN` | 8 |
| `turnon_corneringlight` | `INTENT_UNKNOWN` | 7 |
| `switch_drivemode_normal` | `INTENT_UNKNOWN` | 7 |
| `get_current_speed` | `INTENT_UNKNOWN` | 7 |
| `get_gear` | `INTENT_UNKNOWN` | 7 |
| `activate_autopark` | `INTENT_UNKNOWN` | 6 |
| `shift_gear_park` | `INTENT_UNKNOWN` | 6 |
| `restore_driverseat_pos` | `ad_driverseat_angle` | 6 |
| `turnon_turnsignal_right` | `INTENT_UNKNOWN` | 6 |
| `turnon_turnsignal_left` | `INTENT_UNKNOWN` | 6 |
| `get_battery_pct` | `INTENT_UNKNOWN` | 6 |
| `unlock_doors` | `lock_doors` | 5 |
| `activate_creepmode` | `INTENT_UNKNOWN` | 5 |
| `fold_backseat` | `INTENT_UNKNOWN` | 5 |
| `get_avh_status` | `activate_avh` | 5 |
| `activate_avh` | `INTENT_UNKNOWN` | 4 |
| `activate_valetmode` | `INTENT_UNKNOWN` | 4 |
| `SHIFT_GEAR_REVERSE` | `INTENT_UNKNOWN` | 4 |
| `ad_driverseat_angle` | `INTENT_UNKNOWN` | 4 |
| `open_window` | `INTENT_UNKNOWN` | 4 |

## Errors — first 80

| id | true | predicted | utterance |
|---|---|---|---|
| FROZEN-0003 | `open_door` | `INTENT_UNKNOWN` | bung cửa xe ra coi |
| FROZEN-0009 | `open_door` | `open_trunk` | Mở giùm cái cửa xe ra nào, đừng có mở lộn cái cốp sau nha. |
| FROZEN-0010 | `open_door` | `INTENT_UNKNOWN` | bung cửa xe ra hít thở chút |
| FROZEN-0016 | `open_trunk` | `INTENT_UNKNOWN` | xe đang lao 70 cây chuối trên cao tốc thế này bung cốp sau lấy đồ đc ko |
| FROZEN-0017 | `open_trunk` | `INTENT_UNKNOWN` | tự nhiên nhớ ra để cái thùng sữa dưới khoang sau, bung cái cốp ra dùm đi |
| FROZEN-0019 | `open_trunk` | `INTENT_UNKNOWN` | bung nắp chứa đồ phía sau ra |
| FROZEN-0023 | `open_chargeport` | `INTENT_UNKNOWN` | Tấp vô trạm rồi, mở khe cắm sạc pin ra đi bạn. |
| FROZEN-0029 | `open_chargeport` | `INTENT_UNKNOWN` | tới trụ trạm rồi mở khe cắm sạc ra coi nà |
| FROZEN-0030 | `open_chargeport` | `INTENT_UNKNOWN` | mở nắp cổng điện bên hông |
| FROZEN-0042 | `unlock_doors` | `lock_doors` | mở khoá cửa lẹ coi |
| FROZEN-0043 | `unlock_doors` | `lock_doors` | mở khoá hết mấy cánh cửa ra giùm tui với tề |
| FROZEN-0044 | `unlock_doors` | `lock_doors` | Bấm mở chốt khóa cửa ra. |
| FROZEN-0045 | `unlock_doors` | `lock_doors` | Phiền trợ lý mở khóa toàn bộ cửa cho người thân lên xe với ạ. |
| FROZEN-0047 | `unlock_doors` | `lock_doors` | tấp vô lề rồi mà kẹt cái chốt, mở khoá cửa dùm cái đặng người ta mở cửa bước vô |
| FROZEN-0049 | `unlock_doors` | `INTENT_UNKNOWN` | mở chốt cho người ta vô xe |
| FROZEN-0050 | `unlock_doors` | `INTENT_UNKNOWN` | bấm mở khóa chốt bốn cánh |
| FROZEN-0055 | `OPEN_BONNET` | `open_trunk` | Bác tài phiền bấm mở giùm nắp khoang hành lý phía trước ra được k ạ. |
| FROZEN-0056 | `OPEN_BONNET` | `INTENT_UNKNOWN` | xe đang chạy vù vù ngoài phố 50km/h thế này có giật mở nắp ca-pô đằng trước được ko ta |
| FROZEN-0060 | `OPEN_BONNET` | `INTENT_UNKNOWN` | bật nắp ca-pô đằng trước |
| FROZEN-0063 | `turnon_highbeam` | `INTENT_UNKNOWN` | bật pha xa lên đi bạn, ngoài ni tối mịt mùng rứa |
| FROZEN-0068 | `turnon_highbeam` | `INTENT_UNKNOWN` | pha lên đi tối quá k thấy lối đi luôn nè |
| FROZEN-0070 | `turnon_highbeam` | `turnoff_highbeam` | đang tắt pha thì bật đèn pha chiếu xa lên giùm |
| FROZEN-0071 | `turnoff_highbeam` | `INTENT_UNKNOWN` | Hạ đèn pha xuống giùm anh nhé, chói mắt xe đối diện quá. |
| FROZEN-0072 | `turnoff_highbeam` | `INTENT_UNKNOWN` | tắt pha đi chói quá |
| FROZEN-0079 | `turnoff_highbeam` | `turnoff_lowbeam` | hạ pha chiếu xa xuống chứ k phải tắt luôn đèn cốt đâu nhé |
| FROZEN-0090 | `turnon_lowbeam` | `turnoff_lowbeam` | đèn cốt đang tắt kìa, bật đèn chiếu gần lên |
| FROZEN-0099 | `turnoff_lowbeam` | `turnoff_highbeam` | tắt đèn cốt đi chứ đừng đụng vô đèn pha nha |
| FROZEN-0108 | `AD_WIPER_MAX` | `INTENT_UNKNOWN` | mưa như trút nước rùi, quẹt kính hết cỡ đi bạn ơi |
| FROZEN-0113 | `activate_ahb` | `INTENT_UNKNOWN` | bật cái auto high beam ni lên giùm tui với hè |
| FROZEN-0114 | `activate_ahb` | `INTENT_UNKNOWN` | Kích hoạt đèn pha thích ứng tự động. |
| FROZEN-0121 | `turnon_corneringlight` | `INTENT_UNKNOWN` | Bật đèn mở rộng góc cua lên giúp mình nhé, sắp rẽ vào ngõ hẹp. |
| FROZEN-0122 | `turnon_corneringlight` | `INTENT_UNKNOWN` | bật đèn soi góc cua lẹ |
| FROZEN-0124 | `turnon_corneringlight` | `INTENT_UNKNOWN` | Bật đèn hỗ trợ chiếu góc cua. |
| FROZEN-0125 | `turnon_corneringlight` | `turnon_lowbeam` | xe đang phóng 80km/h trên đường vắng mà chưa bật đèn cốt, bật đèn soi góc cua dc k |
| FROZEN-0126 | `turnon_corneringlight` | `INTENT_UNKNOWN` | đang phi 70 cây số một giờ mà đòi bật đèn rẽ góc cua là răng hè |
| FROZEN-0127 | `turnon_corneringlight` | `INTENT_UNKNOWN` | Nhờ hệ thống bật đèn soi góc cua để quan sát mép đường bên phụ ạ. |
| FROZEN-0129 | `turnon_corneringlight` | `INTENT_UNKNOWN` | chuẩn bị ôm cua rẽ phải bật đèn chiếu góc bên phụ giùm |
| FROZEN-0130 | `turnon_corneringlight` | `INTENT_UNKNOWN` | bật đèn soi góc mép cua |
| FROZEN-0132 | `turnon_interiorlight` | `INTENT_UNKNOWN` | bật đèn trong cabin coi |
| FROZEN-0137 | `turnon_interiorlight` | `INTENT_UNKNOWN` | Làm ơn bật đèn chiếu sáng bên trong xe giúp tôi, tôi tìm giấy tờ chút. |
| FROZEN-0138 | `turnon_interiorlight` | `INTENT_UNKNOWN` | tối quá k thấy đồ dưới sàn xe, mở đèn trong xe lên đi |
| FROZEN-0141 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển sang chế độ lái thể thao Sport giúp anh nhé, sắp nhập làn cao tốc. |
| FROZEN-0142 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | chuyển qua mode sport mau |
| FROZEN-0143 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | đổi sang chế độ lái thể thao giùm tui với nà |
| FROZEN-0144 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Chuyển chế độ lái thể thao. |
| FROZEN-0145 | `switch_drivemode_sport` | `get_battery_pct` | Pin xe còn có 12% sắp cạn rồi mà chuyển sang chế độ lái thể thao Sport xem có tốn pin k |
| FROZEN-0146 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | pin còn có 18% bèo bọt mà đòi chạy thể thao sport coi chừng nằm đường nghen xe |
| FROZEN-0147 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | Phiền trợ lý kích hoạt chế độ lái Sport để xe tăng tốc bốc hơn nhé. |
| FROZEN-0148 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | bật chạy sport đi bạn, đường thoáng đạp ga cho đã coi |
| FROZEN-0149 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | chuẩn bị đạp lút ga vượt xe chuyển qua lái thể thao giùm cái |
| FROZEN-0150 | `switch_drivemode_sport` | `INTENT_UNKNOWN` | kích hoạt chế độ lái thể thao Sport chứ k đi chế độ bình thường đâu |
| FROZEN-0151 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | Chuyển giúp anh sang chế độ lái tiết kiệm Eco nhé, xe gần hết pin rồi. |
| FROZEN-0152 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | đổi qua eco tiết kiệm lẹ |
| FROZEN-0154 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | Chuyển sang chế độ lái Eco. |
| FROZEN-0155 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | nhìn pin tụt nhanh xót ruột quá, chuyển xe qua chạy kiểu tiết kiệm eco giùm đi bạn |
| FROZEN-0157 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | Nhờ hệ thống kích hoạt chế độ lái tiết kiệm điện năng Eco. |
| FROZEN-0158 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | chạy eco đi cho êm ái chớ đừng có giật cục |
| FROZEN-0159 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | pin xe sụt lẹ quá, đổi ngay sang chế độ lái tiết kiệm điện năng |
| FROZEN-0160 | `switch_drivemode_eco` | `INTENT_UNKNOWN` | chạy eco tiết kiệm chớ đừng để normal chạy nghen bạn |
| FROZEN-0161 | `switch_drivemode_normal` | `INTENT_UNKNOWN` | Chuyển xe về lại chế độ lái bình thường Normal giúp em nhé. |
| FROZEN-0163 | `switch_drivemode_normal` | `INTENT_UNKNOWN` | chuyển về mode normal giùm tui với tề |
| FROZEN-0164 | `switch_drivemode_normal` | `INTENT_UNKNOWN` | Chuyển chế độ lái tiêu chuẩn. |
| FROZEN-0165 | `switch_drivemode_normal` | `INTENT_UNKNOWN` | chạy thể thao giật mình quá rồi, thôi đưa xe về lái êm ái tiêu chuẩn bình thường lại giùm tôi |
| FROZEN-0166 | `switch_drivemode_normal` | `INTENT_UNKNOWN` | hết giờ đua đòi rồi, xe ơi đưa chế độ lái về normal bình thường như mọi bữa dùm đi |
| FROZEN-0167 | `switch_drivemode_normal` | `INTENT_UNKNOWN` | Phiền trợ lý thiết lập lại chế độ lái thường Normal nhé. |
| FROZEN-0169 | `switch_drivemode_normal` | `INTENT_UNKNOWN` | lái bốc quá chóng mặt rồi, trả về chế độ lái êm ái tiêu chuẩn giùm |
| FROZEN-0172 | `activate_creepmode` | `INTENT_UNKNOWN` | bật chế độ bò lẹ coi |
| FROZEN-0174 | `activate_creepmode` | `INTENT_UNKNOWN` | Bật chế độ di chuyển chậm Creep. |
| FROZEN-0175 | `activate_creepmode` | `activate_avh` | Hệ thống giữ phanh AVH đang bật giữ chặt bánh xe thế này mà đòi kích hoạt chế độ trườn creep thì sao |
| FROZEN-0177 | `activate_creepmode` | `INTENT_UNKNOWN` | Phiền bạn kích hoạt chế độ xe tự lăn bánh Creep để tiện nhích từng mét trong tắc đường ạ. |
| FROZEN-0179 | `activate_creepmode` | `INTENT_UNKNOWN` | nhả phanh cho xe tự lăn trườn từ từ vô chuồng đỗ đi |
| FROZEN-0180 | `activate_creepmode` | `INTENT_UNKNOWN` | bật chế độ bò xe creep |
| FROZEN-0182 | `turnoff_LKA` | `INTENT_UNKNOWN` | tắt giữ làn đường lẹ |
| FROZEN-0187 | `turnoff_LKA` | `INTENT_UNKNOWN` | Làm ơn hủy kích hoạt tính năng hỗ trợ giữ làn đường Lane Keeping Assist. |
| FROZEN-0189 | `turnoff_LKA` | `INTENT_UNKNOWN` | đoạn này đường đang đào vô lăng giằng mạnh quá, hủy tính năng giữ làn đi |
| FROZEN-0197 | `activate_aac` | `INTENT_UNKNOWN` | Phiền trợ lý bật chế độ ga tự động thích ứng để bám đuôi xe phía trước an toàn. |
| FROZEN-0199 | `activate_aac` | `INTENT_UNKNOWN` | cài đặt ga tự động duy trì cự ly bám đuôi với xe chạy đằng trước |
| FROZEN-0204 | `activate_hda` | `INTENT_UNKNOWN` | Kích hoạt Highway Driving Assist. |
| FROZEN-0209 | `activate_hda` | `INTENT_UNKNOWN` | xe đang trên cao tốc, bật hệ thống trợ lái tự canh làn giữ khoảng cách luôn |
| FROZEN-0215 | `activate_tcs` | `deactivate_esc` | Hệ thống cân bằng điện tử ESC đang bị tắt ngúm rồi, thử bật tính năng kiểm soát lực kéo TCS xem có cho bật k |

---
> Generated — overwritten on each run. Interpretation and context:
> `docs/METRICS.md`.
