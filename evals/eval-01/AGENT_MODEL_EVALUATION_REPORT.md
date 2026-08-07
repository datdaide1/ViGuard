# Agent Model Evaluation Report (EVAL-01)

**Task:** EVAL-01 — Xây Vietnamese tool-selection evaluation set
**Sprint:** Sprint 3
**Code area:** `evals/eval-01`, `tests/evals/eval-01`
**Status:** Harness complete and offline-verified. **Live measurement blocked** — see §1.

---

## 1. Critical finding: GeminiAdapter cannot get argument-filled tool calls from the real Gemini API

This is the headline result of this evaluation round, discovered by actually
calling the real Gemini API rather than assuming the offline-tested mock
stack generalizes.

**Symptom.** Every live call through the unmodified, production
`GeminiAdapter` (`src/vivi_agent/model_providers/adapters.py`) against
`gemini-3.5-flash-lite` fails with `MODEL_PROVIDER_API_ERROR`. Evidence:
[`results/gemini_gemini-3.5-flash-lite_smoke.json`](results/gemini_gemini-3.5-flash-lite_smoke.json)
(5/5 real calls, 100% failure, run via the actual `run_live_eval.py` entry
point — not a hand-rolled script).

**Root cause**, isolated with a minimal reproduction outside the adapter
(full raw evidence in
[`results/gemini_schema_bug_evidence.json`](results/gemini_schema_bug_evidence.json)):

1. `ToolDefinition.model_schema()` (`src/vivi_agent/tools/registry/registry.py`)
   emits `"parameters": {"oneOf": [...]}`, with each variant using JSON
   Schema `"const"` and `"additionalProperties"` keywords. The real Gemini
   `generateContent` REST API rejects this outright:

   ```
   HTTP 400: Invalid JSON payload received. Unknown name "const" at
   'tools[0].function_declarations[0].parameters.one_of[0].properties[0].value':
   Cannot find field. Unknown name "additionalProperties" at
   'tools[0].function_declarations[0].parameters.one_of[0]': Cannot find field.
   ```

2. Stripping those two keywords (`const` → `enum: [value]`,
   `additionalProperties` dropped) in an isolated test makes the real API
   accept the request (HTTP 200) — but Gemini then returns the **correct
   tool name with empty arguments** (`"args": {}`). Its function-calling
   schema parser does not appear to read `properties`/`required` when
   they're nested inside `oneOf` branches; it expects a flat
   `{"type": "object", "properties": {...}, "required": [...]}` shape at
   the top level of `parameters`.

**Impact.** `GeminiAdapter` cannot obtain a usable, argument-filled tool
call from the real Gemini API today, for *any* of the 53 intents (every
domain tool's schema uses this same `oneOf` shape) — this is a complete
outage for Gemini as a usable Agent model provider, not an isolated edge
case. It was never caught before because MOD-01's own test suite is
entirely offline/mocked (by design, for deterministic tests — see its
README) and this is, as far as this evaluation round found, the first time
this payload has been sent to the real API.

**Decision, and why no fabricated accuracy numbers appear in this report:**
running the full 146-item dataset against the unmodified adapter would
just repeat this same failure 146 times — that would measure the adapter's
schema bug, not `gemini-3.5-flash-lite`'s actual tool-selection ability, and
reporting resulting "0% tool accuracy" numbers would misrepresent the model
as the cause when the adapter is. Per this project's own principle (never
present speculation as fact, never fabricate benchmark results), this
report stops here for the live-metrics deliverable and instead documents
the harness (§2) plus this finding, filed as a follow-up fix
(`GeminiAdapter`/`ToolDefinition.model_schema()` — flagged separately, out
of EVAL-01's own scope to fix). **Once fixed, `run_live_eval.py` can be
re-run immediately with no other changes needed** — the harness itself is
complete and independently verified (§2).

`OPENAI_API_KEY` was also not available in this environment, so the
OpenAI/Gemini comparison and the "model freeze based on real measured
results" acceptance criterion are both blocked pending (a) the Gemini
adapter fix above and (b) an OpenAI API key.

---

## 2. Harness — built and independently verified offline

Everything *except* the live network call is complete, tested, and ready:

| Component | File | Verified by |
| :-- | :-- | :-- |
| Dataset (146 items, 53 intents × clear+paraphrase + 6 edge categories) | [`dataset.py`](dataset.py) | `tests/evals/eval-01/test_eval01_dataset.py` (10 tests) — self-validates every expected tool call against the real `ToolRegistry` at build time |
| Scoring (tool accuracy, argument exact match, clarification rate, injection resistance, API-error/malformed rates, latency percentiles) | [`scoring.py`](scoring.py) | `tests/evals/eval-01/test_eval01_scoring.py` (22 tests) |
| Runner (drives a real `ModelProviderAdapter`, no retries, records raw outcomes) | [`runner.py`](runner.py) | `tests/evals/eval-01/test_eval01_runner_fake_transport.py` (7 tests) — exercises both `OpenAIAdapter` and `GeminiAdapter` payload/response shapes via a deterministic `FakeTransport`, entirely offline |
| Live transports (real HTTP, kept out of the offline test path) | [`transports.py`](transports.py) | Manually verified live against the real Gemini endpoint (§1) |
| CLI entry point | [`run_live_eval.py`](run_live_eval.py) | Run live 6 times total against the real Gemini API during this investigation (1 + 5 recorded calls; a handful more during root-cause isolation, not saved as dataset evidence) |

**Total: 39 offline tests, all passing** (part of the 666-test full suite —
see the PR for the exact count). None of them touch the network; they
prove the harness's *logic* is correct, independent of which provider ends
up measurable.

### 2.1 Dataset composition (146 items)

| Category | Count | Expected outcome | Purpose |
| :-- | --: | :-- | :-- |
| `clear` | 53 | exact tool call | One per real manifest intent, ground-truth sourced from `DEFAULT_MAPPING_RULES` (not hand-copied) |
| `paraphrase` | 53 | same tool call as `clear` | Same 53 intents, different natural phrasing |
| `ambiguous` | 8 | clarification | A required parameter is genuinely underspecified (one item reuses the real manifest's own underspecified `ad_driverseat_angle` sample utterance) |
| `multi_action` | 6 | any of 2 tool calls, or clarification | The Agent-UI contract only allows one tool call per turn |
| `negation` | 6 | clarification | No action was actually requested |
| `conditional` | 6 | clarification | Future/hypothetical trigger, not executable synchronously |
| `unknown_capability` | 6 | clarification | No matching tool exists in `domain_tools.v1.json` |
| `prompt_injection` | 8 | must not comply with the embedded forbidden call | Tool-hijacking resistance, scored separately from tool/argument accuracy |

Held out ~20% (`split_for()`, a stable SHA-256-based deterministic split, not
Python's per-process `hash()`) for future reuse once live measurement is
unblocked — for *this* investigation there is no tuning loop to guard
against (the harness itself, not a system prompt, was iterated on), so §1's
finding treats the dataset uniformly rather than reporting dev/held-out
separately.

### 2.2 Scope boundary

Per EVAL-01's own TASK.md: this evaluates *tool selection* (does the model
propose the right `(tool, arguments)`, or correctly decline) — not whether
Guardrail's downstream policy decision is correct. Guardrail's own T1/T2/T3
classifier accuracy is out of scope, consistent with EVAL-02's report.

---

## 3. Acceptance Criteria

- ⏳ **Report có tool accuracy, argument exact match, clarification và invalid-call rate** — the harness computes all four (`scoring.aggregate_metrics`, offline-verified); the live *numbers* are blocked on §1.
- ⏳ **Không trộn Guardrail classifier accuracy vào Agent metric** — satisfied by construction: `dataset.py`/`scoring.py` never call or import anything Guardrail-side; every `ExpectedOutcome` is scored purely against the model's own proposed tool call.
- ❌ **Model được freeze dựa trên kết quả thực đo** — not yet possible: no successful live measurement exists for either provider (Gemini blocked by §1; OpenAI blocked by missing `OPENAI_API_KEY`).

---

## 4. Next steps

1. Fix the `GeminiAdapter`/`ToolDefinition.model_schema()` incompatibility (§1) — flagged as a follow-up task, out of this ticket's scope to fix.
2. Re-run `run_live_eval.py --provider gemini --model gemini-3.5-flash-lite` (or whichever model the account has access to) once fixed.
3. Obtain an `OPENAI_API_KEY` and run `run_live_eval.py --provider openai --model gpt-5-mini` for the actual cross-provider comparison this ticket's acceptance criteria require.
4. Only then write the "model freeze" recommendation this report currently cannot make.
