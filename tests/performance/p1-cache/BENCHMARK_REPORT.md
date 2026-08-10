# P1-CACHE offline benchmark report

## Scope

This benchmark measures local adapter construction, tool/workflow schema
generation, deterministic transport invocation, and output normalization. The
transport is an in-process fixture: it makes no provider or Guardrail network
request and does not measure or claim an improvement in model inference or
end-to-end turn latency. The benchmark uses only public adapter constructors
and `propose_tool()` APIs so it remains stable across router refactors.

Command:

```powershell
$env:PYTHONPATH='.;src'
E:\anaconda3\envs\cocktail-ai\python.exe tests\performance\p1-cache\benchmark.py
```

Environment: Python 3.11.15, Windows, 2,000 iterations per provider.

## Results

| Provider | Rebuild adapter + schema | Cached adapter + defensive schema clone | Speedup |
|---|---:|---:|---:|
| OpenAI | 286.037 µs/call | 283.812 µs/call | 1.008× |
| Gemini | 165.634 µs/call | 134.895 µs/call | 1.228× |

The result demonstrates a measurable Gemini preparation improvement; the
OpenAI path is effectively neutral once output normalization is included.
Absolute savings are small relative to a real network/model call, so this
optimization must not be presented as an LLM latency improvement without a
separate live-provider benchmark.

## Safety boundary

The cache contains only provider adapters and declarations derived from the
immutable tool/workflow registries. Every request still receives a defensive
schema clone. Conversation messages, model responses, Guardrail decisions,
permits, Vehicle State/PIP snapshots, execution results, and session locks are
never cached.

Provider transports are snapshotted at router construction. Runtime owners can
rotate a binding through `ModelProviderRouter.replace_transport()`, which
atomically invalidates only that provider's cached adapter.
