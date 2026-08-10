# P1-CACHE offline benchmark report

## Scope

This benchmark measures only CPU work performed before a model-provider
transport call: constructing an adapter and generating immutable tool/workflow
schemas. It makes no provider or Guardrail network request and does not measure
or claim an improvement in model inference or end-to-end turn latency.

Command:

```powershell
$env:PYTHONPATH='.;src'
E:\anaconda3\envs\cocktail-ai\python.exe tests\performance\p1-cache\benchmark.py
```

Environment: Python 3.11.15, Windows, 2,000 iterations per provider.

## Results

| Provider | Rebuild adapter + schema | Cached adapter + defensive schema clone | Speedup |
|---|---:|---:|---:|
| OpenAI | 299.037 µs/call | 265.030 µs/call | 1.128× |
| Gemini | 176.455 µs/call | 135.438 µs/call | 1.303× |

The result demonstrates repeatable local preparation overhead and justifies
caching immutable provider configuration. Absolute savings are small relative
to a real network/model call, so this optimization must not be presented as an
LLM latency improvement without a separate live-provider benchmark.

## Safety boundary

The cache contains only provider adapters and declarations derived from the
immutable tool/workflow registries. Every request still receives a defensive
schema clone. Conversation messages, model responses, Guardrail decisions,
permits, Vehicle State/PIP snapshots, execution results, and session locks are
never cached.
