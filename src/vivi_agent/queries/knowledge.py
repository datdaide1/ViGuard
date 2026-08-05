"""Grounded VinFast Knowledge Base and Feature Explanation Responder.

This module provides deterministic knowledge lookup for VinFast vehicle features.
It does not use free-form LLM generation as a source of truth, adhering strictly
to grounded facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vivi_agent.queries.models import QueryResult, QueryResultSource, QueryStatus


@dataclass(frozen=True)
class FeatureKnowledge:
    """Grounded knowledge specification for a VinFast vehicle feature."""

    canonical_id: str
    name_vi: str
    short_description: str
    detailed_explanation: str
    aliases: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# VinFast Vehicle Feature Knowledge Inventory (14 Features)
# ---------------------------------------------------------------------------

FEATURE_KNOWLEDGE_BASE: tuple[FeatureKnowledge, ...] = (
    FeatureKnowledge(
        canonical_id="adaptive_cruise_control",
        name_vi="Kiểm soát hành trình thích ứng (AAC)",
        short_description="Tự động duy trì tốc độ và khoảng cách an toàn với xe phía trước.",
        detailed_explanation=(
            "Tính năng Kiểm soát hành trình thích ứng (AAC) tự động điều chỉnh tốc độ "
            "xe để duy trì khoảng cách an toàn với phương tiện phía trước bằng hệ thống radar và camera."
        ),
        aliases=("aac", "adaptive_cruise_control", "khiem_soat_hanh_trinh_thich_ung", "cruise_control"),
    ),
    FeatureKnowledge(
        canonical_id="auto_park",
        name_vi="Tự động đỗ xe (Autopark)",
        short_description="Hỗ trợ phát hiện và tự động điều khiển xe vào/ra vị trí đỗ.",
        detailed_explanation=(
            "Tính năng Tự động đỗ xe (Autopark) sử dụng các cảm biến siêu âm và camera xung quanh xe "
            "để quét tìm không gian đỗ xe phù hợp và tự động đánh lái, chuyển số, phanh vào chỗ đỗ."
        ),
        aliases=("autopark", "auto_park", "tu_dong_do_xe", "do_xe_tu_dong"),
    ),
    FeatureKnowledge(
        canonical_id="auto_vehicle_hold",
        name_vi="Giữ phanh tự động (AVH)",
        short_description="Tự động duy trì lực phanh khi xe dừng hẳn mà không cần giữ chân phanh.",
        detailed_explanation=(
            "Tính năng Giữ phanh tự động (AVH) tự động giữ phanh khi xe đã dừng hoàn toàn "
            "(như khi chờ đèn đỏ hoặc kẹt xe) và tự động nhả phanh khi người lái nhấn ga."
        ),
        aliases=("avh", "auto_vehicle_hold", "giu_phanh_tu_dong", "auto_hold"),
    ),
    FeatureKnowledge(
        canonical_id="automatic_high_beam",
        name_vi="Đèn pha tự động (AHB)",
        short_description="Tự động chuyển đổi giữa đèn chiếu xa và chiếu gần khi gặp xe đối diện.",
        detailed_explanation=(
            "Tính năng Đèn pha tự động (AHB) tự động bật đèn chiếu xa khi trời tối và "
            "tự động hạ xuống chiếu gần khi phát hiện ánh sáng từ phương tiện đi ngược chiều hoặc phía trước."
        ),
        aliases=("ahb", "automatic_high_beam", "den_pha_tu_dong", "pha_tudong"),
    ),
    FeatureKnowledge(
        canonical_id="camp_mode",
        name_vi="Chế độ cắm trại (Camp Mode)",
        short_description="Duy trì điều hòa, nguồn điện cabin và tắt báo động khi đỗ xe cắm trại.",
        detailed_explanation=(
            "Chế độ cắm trại (Camp Mode) duy trì thông gió, điều hòa không khí và nguồn điện sinh hoạt "
            "trong khoang xe trong khi vô hiệu hóa hệ thống báo động chống trộm khi xe đang đỗ."
        ),
        aliases=("camp_mode", "cam_trai", "che_do_cam_trai"),
    ),
    FeatureKnowledge(
        canonical_id="creep_mode",
        name_vi="Chế độ bò (Creep Mode)",
        short_description="Cho phép xe tự di chuyển chậm khi nhả phanh ở số D hoặc R.",
        detailed_explanation=(
            "Chế độ bò (Creep Mode) mô phỏng hành vi của xe số tự động truyền thống, "
            "cho phép xe di chuyển chậm khi người lái nhả chân phanh mà không cần nhấn chân ga."
        ),
        aliases=("creep_mode", "che_do_bo", "creep"),
    ),
    FeatureKnowledge(
        canonical_id="electronic_parking_brake",
        name_vi="Phanh tay điện tử (EPB)",
        short_description="Hệ thống phanh đỗ xe điều khiển điện tử thay cho cần phanh cơ.",
        detailed_explanation=(
            "Phanh tay điện tử (EPB) giữ chặt phanh đỗ xe bằng mô tơ điện tử, "
            "tự động kích hoạt khi về số P và tự động nhả khi vào số D/R kèm nhấn ga."
        ),
        aliases=("epb", "electronic_parking_brake", "phanh_tay_dien_tu", "phanh_tay"),
    ),
    FeatureKnowledge(
        canonical_id="electronic_stability_control",
        name_vi="Cân bằng điện tử (ESC)",
        short_description="Hệ thống an toàn bắt buộc giúp duy trì độ ổn định thân xe khi vào cua hoặc trơn trượt.",
        detailed_explanation=(
            "Hệ thống Cân bằng điện tử (ESC) tự động can thiệp lực phanh từng bánh xe và công suất động cơ "
            "để ngăn ngừa tình trạng thiếu lái hoặc thừa lái khi vào cua gấp hoặc mặt đường trơn trượt."
        ),
        aliases=("esc", "electronic_stability_control", "can_bang_dien_tu"),
    ),
    FeatureKnowledge(
        canonical_id="head_up_display",
        name_vi="Màn hình hiển thị trên kính lái (HUD)",
        short_description="Hiển thị thông tin vận hành quan trọng trực tiếp lên kính chắn gió.",
        detailed_explanation=(
            "Màn hình HUD (Head-Up Display) chiếu các thông tin như tốc độ, chỉ đường và cảnh báo an toàn "
            "trực tiếp lên kính chắn gió phía trước tầm mắt người lái để tăng cường sự tập trung."
        ),
        aliases=("hud", "head_up_display", "hien_thi_kinh_lai", "man_hinh_hud"),
    ),
    FeatureKnowledge(
        canonical_id="highway_drive_assist",
        name_vi="Hỗ trợ lái trên cao tốc (HDA)",
        short_description="Kết hợp AAC và giữ làn để hỗ trợ lái xe bán tự động trên đường cao tốc.",
        detailed_explanation=(
            "Tính năng Hỗ trợ lái trên cao tốc (HDA) kết hợp kiểm soát hành trình thích ứng (AAC) "
            "và hỗ trợ định tâm làn đường (LKA) để hỗ trợ điều khiển tốc độ và hướng di chuyển của xe trên cao tốc."
        ),
        aliases=("hda", "highway_drive_assist", "ho_tro_lai_cao_toc"),
    ),
    FeatureKnowledge(
        canonical_id="lane_keeping_assist",
        name_vi="Hỗ trợ giữ làn đường (LKA)",
        short_description="Cảnh báo và tự động can thiệp vô lăng khi xe có dấu hiệu chệch làn đường.",
        detailed_explanation=(
            "Tính năng Hỗ trợ giữ làn đường (LKA) sử dụng camera theo dõi vạch kẻ đường, "
            "cảnh báo người lái và can thiệp nhẹ vào lực lái nếu xe có nguy cơ rời khỏi làn đường mà không bật xi-nhan."
        ),
        aliases=("lka", "lane_keeping_assist", "ho_tro_giu_lan", "giu_lan"),
    ),
    FeatureKnowledge(
        canonical_id="pet_mode",
        name_vi="Chế độ thú cưng (Pet Mode)",
        short_description="Duy trì nhiệt độ khoang xe an toàn và hiển thị thông báo cho thú cưng khi chủ rời xe.",
        detailed_explanation=(
            "Chế độ thú cưng (Pet Mode) duy trì điều hòa cabin ở nhiệt độ dễ chịu "
            "và hiển thị thông báo trên màn hình trung tâm để người bên ngoài biết thú cưng vẫn an toàn."
        ),
        aliases=("pet_mode", "thu_cung", "che_do_thu_cung"),
    ),
    FeatureKnowledge(
        canonical_id="traction_control",
        name_vi="Kiểm soát lực kéo (TCS)",
        short_description="Ngăn ngừa hiện tượng bánh xe bị trượt quay khi tăng tốc trên đường trơn.",
        detailed_explanation=(
            "Hệ thống Kiểm soát lực kéo (TCS) phát hiện và điều chỉnh mô-men xoắn đến bánh xe bị trượt, "
            "giúp xe duy trì độ bám đường tối đa khi khởi hành hoặc tăng tốc."
        ),
        aliases=("tcs", "traction_control", "kiem_soat_luc_keo"),
    ),
    FeatureKnowledge(
        canonical_id="valet_mode",
        name_vi="Chế độ Valet (Valet Mode)",
        short_description="Khóa thông tin cá nhân và giới hạn tính năng khi giao xe cho người khác đỗ.",
        detailed_explanation=(
            "Chế độ Valet (Valet Mode) bảo vệ riêng tư bằng cách khóa màn hình trung tâm, "
            "ẩn thông tin cá nhân, định vị và giới hạn tốc độ tối đa khi giao xe cho nhân viên đỗ xe."
        ),
        aliases=("valet_mode", "valet", "che_do_valet"),
    ),
)

# Index for O(1) alias lookup
_ALIAS_TO_FEATURE: dict[str, FeatureKnowledge] = {}
for _fk in FEATURE_KNOWLEDGE_BASE:
    _ALIAS_TO_FEATURE[_fk.canonical_id.lower()] = _fk
    for _alias in _fk.aliases:
        _ALIAS_TO_FEATURE[_alias.lower()] = _fk


def lookup_feature_knowledge(query_str: str) -> FeatureKnowledge | None:
    """Find a FeatureKnowledge record by canonical ID or alias."""
    if not query_str or not isinstance(query_str, str):
        return None
    key = query_str.strip().lower()
    return _ALIAS_TO_FEATURE.get(key)


class ExplainFeatureResponder:
    """Responder for the ``explain_feature`` knowledge query intent."""

    intent_id = "explain_feature"

    def __call__(self, proposal: Mapping[str, Any], state: Any = None) -> QueryResult:
        params = proposal.get("parameters") or proposal.get("arguments") or proposal
        target = None
        if isinstance(params, Mapping):
            target = params.get("feature") or params.get("target") or params.get("item")

        if not target or not isinstance(target, str):
            return QueryResult(
                intent_id=self.intent_id,
                status=QueryStatus.UNKNOWN,
                facts={"error": "MISSING_FEATURE_PARAMETER"},
                response_text="Vui lòng cung cấp tên tính năng bạn muốn tìm hiểu (ví dụ: HDA, AVH, Autopark).",
                source=QueryResultSource.KNOWLEDGE_BASE,
            )

        info = lookup_feature_knowledge(target)
        if info is None:
            return QueryResult(
                intent_id=self.intent_id,
                status=QueryStatus.UNKNOWN,
                facts={"query_target": target, "found": False},
                response_text=f"Hiện chưa có thông tin chi tiết về tính năng {target!r}.",
                source=QueryResultSource.KNOWLEDGE_BASE,
            )

        return QueryResult(
            intent_id=self.intent_id,
            status=QueryStatus.ANSWER,
            facts={
                "canonical_id": info.canonical_id,
                "name_vi": info.name_vi,
                "short_description": info.short_description,
                "detailed_explanation": info.detailed_explanation,
            },
            response_text=f"{info.name_vi}: {info.detailed_explanation}",
            source=QueryResultSource.KNOWLEDGE_BASE,
        )
