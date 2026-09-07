"""EVAL-02 dataset for the 70 Agent capabilities in Intents_Candidate.xlsx."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from vehicle_agent.catalog.candidate import CANDIDATE_CAPABILITIES


@dataclass(frozen=True)
class Eval02Item:
    item_id: str
    utterance: str
    intent: str
    tool: str
    arguments: Mapping[str, str]


_EXAMPLE_VALUES = MappingProxyType(
    {
        "set_regenlevel": "high",
        "set_temperature": "24 C",
        "set_fanspeed": "3",
        "set_wiperspeed": "auto",
        "set_chargelimit": "80%",
        "schedule_charging": "22:00",
        "set_cruise_speed": "80 km/h",
        "set_following_distance": "3",
        "pair_bluetooth": "Điện thoại của tôi",
        "unpair_bluetooth": "Điện thoại của tôi",
        "set_volume": "40%",
        "set_navigation_destination": "Hồ Gươm",
        "add_navigation_stop": "Nhà hát Lớn Hà Nội",
        "make_phonecall": "Mẹ",
        "set_ambientlight_color": "xanh dương",
    }
)


def build_dataset() -> tuple[Eval02Item, ...]:
    items: list[Eval02Item] = []
    for capability in CANDIDATE_CAPABILITIES:
        tool = "control_vehicle_capability"
        arguments = {"action": capability.operation, "target": capability.intent}
        if capability.intent == "turnon_LKA":
            tool = "control_driver_assistance"
            arguments = {"action": "activate", "target": "lane_keeping_assist"}
        if capability.requires_value:
            arguments["value"] = _EXAMPLE_VALUES[capability.intent]
        items.append(
            Eval02Item(
                item_id=f"candidate__{capability.intent}",
                utterance=capability.description,
                intent=capability.intent,
                tool=tool,
                arguments=MappingProxyType(arguments),
            )
        )
    return tuple(items)


DATASET = build_dataset()
