"""ViGuard guardrail package.

Historically every entrypoint in this tree bootstraps ``sys.path`` with the
package directory and imports the siblings flat (``from policy import ...``).
That convention is unchanged; this file only exists so the Phase 2' HTTP
service can be started with ``py -3 -m vf_guardrails.service`` (decision P2-D5).
"""
