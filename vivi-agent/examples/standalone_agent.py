"""Minimal CLI example for the standalone text-to-action Agent."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from vivi_agent import build_agent_runtime_from_env


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help="Vietnamese vehicle request")
    parser.add_argument("--session-id", default="cli-demo")
    parser.add_argument("--request-id")
    args = parser.parse_args()

    runtime = build_agent_runtime_from_env()
    result = runtime.handle_text(
        args.text,
        session_id=args.session_id,
        request_id=args.request_id,
    )
    print(json.dumps(_json_safe(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
