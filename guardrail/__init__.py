"""Aegis guardrail package.

Historically every entrypoint in this tree bootstraps ``sys.path`` with the
package directory and imports the siblings flat (``from policy import ...``).
That convention is unchanged; this file only exists so the the HTTP layer HTTP
service can be started with ``py -3 -m guardrail.service`` (decision P2-D5).
"""
