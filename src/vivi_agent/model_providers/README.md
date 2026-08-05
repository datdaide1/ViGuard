# Model provider boundary (MOD-01)

This package exposes one provider-neutral contract for tool selection and
grounded response composition. `OpenAIAdapter` serializes strict function
declarations; `GeminiAdapter` serializes native function declarations. Both
normalize their backend response to `ModelActionProposal` and never invoke a
Guardrail or vehicle handler.

## Configuration

- `AGENT_MODEL_PROVIDER=auto|openai|gemini` (default `auto`)
- `AGENT_MODEL_PROVIDER_PRIORITY` (default `openai,gemini`)
- `OPENAI_MODEL_ID` (default `gpt-5-mini`)
- `GEMINI_MODEL_ID` (default `gemini-3.6-flash`)
- `AGENT_MODEL_TIMEOUT_SECONDS` (default `10`)
- `OPENAI_API_KEY` and `GEMINI_API_KEY` (backend only)

The configuration checksum deliberately excludes secrets. Readiness requires
both a key and a configured backend transport; there is no mock fallback.

## Backend transport contract

Adapters accept a synchronous `ProviderTransport(payload, timeout_seconds)`
callable. The deployment/integration layer owns the provider SDK or HTTP
client, authentication header, retry policy below this one-attempt boundary,
and conversion of its native response to a mapping. It must not persist API
keys, provider reasoning, or thought payloads. This dependency-injection seam
keeps SDK credentials out of the domain package and permits deterministic
offline tests.

`ModelProviderRouter` makes sequential calls only. In `auto` mode it tries at
most two available providers, and only retries before any valid proposal has
been created. `TurnBinding` pins response composition to the selected provider
once a proposal exists or side-effect lifecycle begins.

Event producers should copy `proposal.metadata.to_event_metadata()`; it emits
provider, exact model ID, secret-free config checksum, and request latency.
