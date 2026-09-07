"""Entrypoint: ``py -3 -m vf_guardrails.service`` (P2-D5).

Follows the repo convention (every entrypoint bootstraps ``sys.path`` with the
``vf_guardrails/`` directory, then imports the flat modules ``policy`` /
``classifier`` / ``service``).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_VF_DIR = Path(__file__).resolve().parents[1]
if str(_VF_DIR) not in sys.path:
    sys.path.insert(0, str(_VF_DIR))

from service.app import GuardrailService  # noqa: E402
from service.http import create_server  # noqa: E402
from service.trace import TraceRecorder  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vf_guardrails.service", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--trace-file", default=None, help="append every trace event as JSONL")
    args = parser.parse_args(argv)

    svc = GuardrailService()
    if args.trace_file:
        svc.trace = TraceRecorder(
            policy_checksum=svc.engine.policy_checksum, sink_path=args.trace_file
        )
    server = create_server(args.host, args.port, service=svc)
    host, port = server.server_address[:2]
    print(f"guardrail service listening on http://{host}:{port}  (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down", flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
