"""Cross-repo test bootstrap.

A few Guardrail tests (tool-map conformance, gate 2'.1) import the real
``vivi_agent`` package to prove the two services actually agree. ``vivi-agent``
is a sibling checkout, not an installed dependency (decision D1: the services
stay separate), so this fixes up ``sys.path`` the way ``vivi-agent/conftest.py``
does for its own suite:

  * both ``vivi-agent/src`` and ``vivi-agent/`` go on ``sys.path``;
  * ``vivi_agent`` has an internal ``from src.vivi_agent...`` import. The bare
    name ``src`` also matches ``vf_guardrails/src`` (the T1 classifier package),
    which would shadow it and break the import. We pin ``src`` to the
    vivi-agent tree for the test session. Nothing under ``vf_guardrails/tests``
    imports ``vf_guardrails/src`` (only the standalone eval scripts do), so this
    is safe here.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

_VIVI_AGENT = Path(__file__).resolve().parents[2] / "vivi-agent"

if _VIVI_AGENT.is_dir():
    for _p in (str(_VIVI_AGENT / "src"), str(_VIVI_AGENT)):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    if "src" not in sys.modules:
        _shim = types.ModuleType("src")
        _shim.__path__ = [str(_VIVI_AGENT / "src")]  # type: ignore[attr-defined]
        sys.modules["src"] = _shim
