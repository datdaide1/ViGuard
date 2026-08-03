# ViVi Vehicle Agent Simulator — Product and Architecture Specification

**Status:** Proposed  
**Date:** 03/08/2026  
**Owner:** Project Manager  
**Reviewers:** AI Engineering, Safety/Policy, Backend, Frontend, QA  
**Applies to:** Local software simulator; no connection to a real vehicle

## 1. Executive decision

ViVi Vehicle Agent Simulator is an LLM-based vehicle agent that can understand a Vietnamese user request, propose a structured vehicle tool call, obtain a state-aware decision from ViGuard, and execute the authorized action against a simulated vehicle.

The agent is allowed to **choose and call tools**, but it is never allowed to authorize its own tool calls. Every state-changing call must pass through the ViGuard Action Gateway immediately before execution. The gateway reads the current vehicle state from the simulator, evaluates policy, and returns `ALLOW`, a block outcome, or `CONFIRM`. Only an `ALLOW` decision or a valid one-time confirmation permit can reach the Vehicle Tool Gateway.

The product must demonstrate two capability sets:

1. Complete observable behavior for all **53 existing intents** in `Driver_constraints.xlsx`.
2. A coherent simulated vehicle that can power on, start moving, accelerate, brake, stop, shift gear and change environmental conditions so state-dependent and continuous-monitoring policies can be demonstrated.

The second capability set expands beyond the existing 53-intent policy catalog. Those driving actions must not be exposed to the agent until their intent definitions and safety policies have been approved and loaded by ViGuard.

## 2. Relationship to existing specifications

This document extends, rather than replaces:

- [`../prd/PRD_Guardrail_FINAL.md`](../prd/PRD_Guardrail_FINAL.md), which defines the Guardrail product, 53-intent scope and seven outcomes.
- [`../architecture/Architecture_Guardrail_FINAL.md`](../architecture/Architecture_Guardrail_FINAL.md), which defines classification, policy evaluation, confirmation, monitor and mock execution boundaries.
- [`../../Driver_constraints.xlsx`](../../Driver_constraints.xlsx), which is the runtime source of truth for 109 policy rules `R001`–`R109`.

This specification changes one simplifying assumption in the existing architecture. The old flow models ViVi as a thin consumer of a completed `GuardrailDecision`. The target simulator must model a realistic agent: ViVi receives the user request, plans a tool call, and submits that call to ViGuard for authorization. ViGuard remains the mandatory decision and enforcement boundary.

### 2.1. Assumed starting point

The implementation may assume that the following already exist and conform to the linked specifications:

- ViGuard text checks, intent classification and constraint evaluation;
- policy loader and closed-AST evaluator;
- Vehicle State UI and state versioning;
- confirmation and monitor primitives;
- Guardrail decision and trace panels.

This document specifies the missing ViVi agent, vehicle tools, simulated vehicle behavior and their integration with those components.

## 3. Problem statement

A guardrail demonstration is incomplete if the “agent” merely displays a policy outcome. A real vehicle agent must interpret a user goal, choose an operation, call a vehicle capability, observe the result and communicate the outcome. At the same time, allowing an LLM to call simulator actuators directly would create the exact bypass path ViGuard is intended to prevent.

The product therefore needs a realistic but controlled agent loop in which agent autonomy exists at the planning and tool-selection layer, while authority remains with deterministic policy enforcement at the action boundary.

## 4. Goals

| ID | Goal | Verification target |
|---|---|---|
| G-01 | ViVi can produce and execute observable behavior for the complete current catalog | 53/53 intents have a tested response or action behavior |
| G-02 | ViVi can control a coherent simulated vehicle | Power, motion, speed, braking, stop, gear and environment transitions work end-to-end |
| G-03 | No LLM output can bypass state-aware authorization | 0 unauthorized actuator calls in automated adversarial tests |
| G-04 | Every action is explainable and replayable | Each request links user text, proposed tool, policy decision, state version and execution result |
| G-05 | Confirmation and monitoring reflect fresh state | 100% confirmation re-evaluations use a newer/current snapshot; all five monitor rules have stop scenarios |
| G-06 | The demo remains usable if the language model is unavailable | Deterministic error/retry paths work; simulator and Guardrail remain inspectable |

## 5. Non-goals

| Non-goal | Reason |
|---|---|
| Control of a physical vehicle, CAN bus or ECU | The simulator cannot establish real-vehicle safety or actuator compatibility |
| OEM or regulatory certification | Policy correctness for a physical model requires OEM evidence and a formal safety case |
| Open-domain assistant behavior | The pilot is bounded to approved vehicle intents and simulator operations |
| Autonomous driving or route planning | Longitudinal/lateral controls exist only to create observable simulation state |
| Speech recognition and speech synthesis | Text remains the canonical input/output for this phase |
| Model-generated tool definitions or executable code | Tools and schemas must be registered and reviewed before startup |
| Production-grade capability security | The local pilot uses in-process one-time permits; hardware-backed production enforcement is separate |

## 6. Users and jobs to be done

### 6.1. Driver/demo participant

> When I ask ViVi to perform a vehicle operation, I want it to act like a real assistant and clearly tell me whether the operation succeeded, needs confirmation or cannot be performed in the current state.

### 6.2. Demo operator

> When I demonstrate ViGuard, I want to move the simulated car through realistic states so the same request can be allowed, blocked or stopped by monitoring in a repeatable scenario.

### 6.3. Safety and technical reviewer

> When ViVi calls a vehicle tool, I want to prove which state and policy rule authorized it and verify that no blocked path reached the actuator.

### 6.4. Agent developer

> When I add or modify an agent behavior, I want a closed tool contract, clear failure modes and coverage checks that detect missing handlers or policy mappings before launch.

## 7. Product principles

1. **The model proposes; ViGuard decides; the vehicle gateway executes.**
2. **Current state is authoritative.** State mentioned in user text or emitted by the model is never trusted for authorization.
3. **Every side effect is registered.** No dynamic tool creation, arbitrary code execution or direct state mutation by the model.
4. **Simulation must be coherent.** State transitions enforce invariants instead of exposing unrelated editable fields.
5. **Every action is visible.** A successful call produces a state transition, animation, active action or explicit one-shot event.
6. **Failure is a first-class outcome.** Tool rejection, actuator failure, timeout and model failure must not be reported as success.
7. **The simulator does not overclaim.** It proves software conformance to mock state and policy, not safety on a real vehicle.

## 8. Scope and capability inventory

### 8.1. Existing 53-intent baseline

The current workbook contains 47 action/UI intents and six query intents. Every intent must have exactly one registered behavior category.

| # | Intent | Category | Required observable behavior |
|---:|---|---|---|
| 1 | `open_door` | Access mutation | Open the configured door and unlock it if execution succeeds |
| 2 | `open_trunk` | Access mutation | Open trunk |
| 3 | `open_chargeport` | Access mutation | Open charge port |
| 4 | `turnoff_highbeam` | Toggle | Set high beam off |
| 5 | `turnon_highbeam` | Toggle | Set high beam on |
| 6 | `turnoff_lowbeam` | Toggle | Set low beam off |
| 7 | `turnon_lowbeam` | Toggle | Set low beam on |
| 8 | `lock_doors` | Access mutation | Lock all closed doors |
| 9 | `unlock_doors` | Access mutation | Unlock doors |
| 10 | `OPEN_BONNET` | Access mutation | Open bonnet |
| 11 | `AD_WIPER_MAX` | Enum mutation | Set wiper level to maximum |
| 12 | `switch_drivemode_sport` | Enum mutation | Set drive mode to Sport |
| 13 | `switch_drivemode_eco` | Enum mutation | Set drive mode to Eco |
| 14 | `switch_drivemode_normal` | Enum mutation | Set drive mode to Normal |
| 15 | `activate_creepmode` | Toggle | Activate creep mode |
| 16 | `turnoff_LKA` | Toggle | Deactivate lane-keeping assistance |
| 17 | `activate_campmode` | Active mode | Activate Camp mode and create monitor session where applicable |
| 18 | `activate_petmode` | Active mode | Activate Pet mode and create monitor session where applicable |
| 19 | `activate_valetmode` | Active mode | Activate Valet mode |
| 20 | `SHIFT_GEAR_REVERSE` | Enum mutation | Shift to Reverse through transmission state machine |
| 21 | `ad_steeringwheel` | Position mutation | Adjust steering wheel position |
| 22 | `activate_autopark` | Active action | Start simulated autopark and monitor it |
| 23 | `fold_backseat` | Timed mutation | Fold rear seat with transition event |
| 24 | `open_sunroof` | Position mutation | Open sunroof |
| 25 | `ad_driverseat_angle` | Position mutation | Adjust driver-seat angle |
| 26 | `ad_driverseat_pos` | Position mutation | Adjust driver-seat position |
| 27 | `open_window` | Position mutation | Open selected/configured window |
| 28 | `restore_driverseat_pos` | Compound mutation | Restore saved driver-seat position |
| 29 | `activate_epb` | Toggle | Engage electronic parking brake |
| 30 | `deactivate_hud` | Toggle | Deactivate HUD |
| 31 | `activate_aac` | Active action | Start adaptive cruise action and monitoring |
| 32 | `activate_hda` | Active action | Start HDA action and monitoring |
| 33 | `shift_gear_park` | Enum mutation | Shift to Park through transmission state machine |
| 34 | `fold_mirrors` | Timed mutation | Fold mirrors |
| 35 | `activate_ahb` | Toggle | Activate automatic high beam |
| 36 | `turnon_turnsignal_right` | Toggle | Turn right signal on |
| 37 | `turnon_turnsignal_left` | Toggle | Turn left signal on |
| 38 | `turnoff_turnsignal_right` | Toggle | Turn right signal off |
| 39 | `turnoff_turnsignal_left` | Toggle | Turn left signal off |
| 40 | `turnon_hazardlight` | Compound toggle | Activate both hazard indicators |
| 41 | `turnoff_hazardlight` | Compound toggle | Deactivate hazard indicators |
| 42 | `turnon_corneringlight` | Toggle | Activate cornering light |
| 43 | `turnon_interiorlight` | Toggle | Activate interior light |
| 44 | `activate_tcs` | Toggle | Activate traction control |
| 45 | `deactivate_esc` | Refused action | Never execute by voice; show manual-operation guidance |
| 46 | `activate_avh` | Toggle | Activate auto vehicle hold |
| 47 | `open_noti_center` | UI event | Open the simulated notification center |
| 48 | `get_current_speed` | State query | Answer from current speed snapshot |
| 49 | `get_battery_pct` | State query | Answer battery percentage or `UNKNOWN` |
| 50 | `get_gear` | State query | Answer current gear or `UNKNOWN` |
| 51 | `get_door_lock_status` | State query | Answer current lock status or `UNKNOWN` |
| 52 | `get_avh_status` | State query | Answer AVH state or `UNKNOWN` |
| 53 | `explain_feature` | Knowledge query | Answer from the approved local knowledge map or `UNKNOWN` |

Names and casing above follow the current workbook and must not be silently normalized in policy data. A separate canonical alias may be used internally only if trace output retains the source intent.

### 8.2. Vehicle dynamics required by the simulator

The simulator must support the following capabilities to create meaningful state transitions and monitor scenarios:

- power vehicle on/off;
- start moving;
- accelerate toward a target speed;
- decelerate toward a target speed;
- apply service brake;
- stop the vehicle;
- apply emergency stop in the simulator;
- shift among `P`, `R`, `N` and `D`;
- set road/environment conditions such as rain, daylight and obstacle state;
- advance simulation time or execute a deterministic tick.

These capabilities have two exposure modes:

1. **Operator mode:** available from the Simulation Console to set up a demo state.
2. **Agent mode:** available to ViVi only after a corresponding intent, parameter schema and policy rule set have been approved and loaded.

Agent mode must fail closed when policy coverage is absent. The implementation must not treat “it is only a simulator” as permission to bypass ViGuard.

## 9. Core user journeys

### 9.1. Authorized action

1. User asks ViVi to open the door.
2. Agent maps the request to a registered `control_access` tool call.
3. ViGuard canonicalizes the call to `open_door`, reads a fresh state snapshot and evaluates policy.
4. ViGuard returns `ALLOW` and a one-time execution permit.
5. Vehicle Tool Gateway validates and consumes the permit.
6. Door handler updates the state and emits an execution event.
7. Agent observes the result and reports success.

### 9.2. Blocked action

1. Simulated vehicle is moving.
2. User asks to open the door.
3. Agent proposes `control_access(action=open, target=driver_door)`.
4. ViGuard returns `BLOCK_UNSAFE` from current simulator state.
5. No permit is issued and actuator call count remains zero.
6. Agent explains the relevant state and safe recovery step.

### 9.3. Confirmation with fresh-state evaluation

1. Agent proposes a tool call whose policy outcome is `CONFIRM`.
2. Agent shows a persistent confirmation prompt; no action occurs.
3. User confirms.
4. ViGuard reads a fresh state snapshot and re-evaluates the tool call.
5. Execution occurs once only if the new decision permits it.
6. Replay, expiration or changed unsafe state causes rejection.

### 9.4. Active action stopped by monitoring

1. Agent starts HDA, AAC or another monitored action after authorization.
2. Simulator creates an `ActiveAction` and Monitor Engine subscription.
3. Vehicle state changes through operator input, agent-authorized action or simulation tick.
4. Monitor Engine evaluates the monitor rule on the new snapshot.
5. A block result routes through the same execution boundary to `stop()` the active action.
6. Agent and trace report why the action was disengaged.

### 9.5. Agent-controlled stop

1. User asks ViVi to stop the simulated vehicle.
2. Agent proposes `control_motion(action=stop)`.
3. ViGuard looks up the approved stop intent and evaluates its dedicated policy.
4. Vehicle Dynamics Controller applies a deterministic deceleration profile.
5. Each tick publishes new speed/state and invokes monitors.
6. The action completes only when speed reaches zero and the simulator reports `STOPPED`.

If the stop intent or policy is not yet loaded, the system rejects the agent call and tells the demo operator that the capability is not authorized. Operator emergency-stop control remains separate and visibly labeled.

## 10. Functional requirements

### 10.1. P0 — ViVi agent runtime

#### FR-A01 — Model-based tool selection

ViVi must use an instruction-tuned language model to map Vietnamese user requests into registered tool calls or a clarification response.

Acceptance criteria:

- The model can only emit tools present in the runtime registry.
- Tool arguments pass strict JSON Schema validation before authorization.
- Invalid, ambiguous or incomplete calls cause clarification or a typed error, never best-effort execution.
- Model output cannot directly contain `ALLOW`, an execution permit or an actuator success result.

#### FR-A02 — Agent model providers

The Agent uses a provider-neutral `ModelProviderAdapter` with two supported API backends:

- OpenAI, default model `gpt-5-mini`;
- Google Gemini, default model `gemini-3.6-flash`.

Provider selection is configuration-driven:

```yaml
agent_model:
  provider: auto # auto | openai | gemini
  provider_priority: [openai, gemini]
  openai_model: gpt-5-mini
  gemini_model: gemini-3.6-flash
  maximum_tool_calls_per_turn: 1
  parallel_tool_calls: false
```

In `auto` mode, the runtime chooses the first configured provider whose API key is present, following `provider_priority`. The default priority selects OpenAI when `OPENAI_API_KEY` exists; otherwise it selects Gemini when `GEMINI_API_KEY` exists. If neither key exists, Agent readiness fails and no action is proposed or executed.

The runtime must not race providers. A one-time failover to the next configured provider is allowed only when the first provider fails before producing a valid `ActionProposal`. After a valid proposal exists, or after Guardrail authorization/execution starts, the turn is pinned to that provider and cannot be replayed through another model.

Acceptance criteria:

- Model startup is health-checked before the Agent endpoint becomes ready.
- Generation uses bounded context, output length and timeout.
- The system records provider, model identifier, configuration checksum and latency without logging hidden reasoning.
- A model timeout or malformed output creates no tool execution.
- Both providers implement the same internal tool-call and response-plan contracts.
- Provider-specific payloads do not leak beyond `ModelProviderAdapter`.

#### FR-A03 — Agent loop

The agent loop may clarify, propose a tool, receive authorization, observe execution and compose a final response. It must have explicit limits on turns, retries and tool calls.

Reference limits for the first implementation:

- maximum one state-changing tool proposal per user turn unless executing an approved predefined workflow;
- maximum two clarification turns;
- no automatic retry of a state-changing tool after uncertain execution status;
- no parallel state-changing tool calls.

#### FR-A04 — Structured response plan

User-facing output must be grounded in typed facts from Guardrail or execution results. The model may verbalize those facts but may not invent vehicle state, policy reasons or success.

### 10.2. P0 — Tool and authorization boundary

#### FR-T01 — Registered domain tools

The agent sees a small domain-oriented tool set rather than arbitrary functions. Initial tools are:

```text
control_access(action, target)
control_light(action, target)
control_cabin(action, target, value?)
set_drive_mode(mode)
control_transmission(action, gear?)
control_driver_assistance(feature, action, value?)
control_special_mode(mode, action)
control_vehicle_motion(action, target_speed?, intensity?)
query_vehicle_state(field)
explain_vehicle_feature(feature)
```

Each valid argument combination maps to one canonical policy intent. Unsupported combinations are rejected before policy evaluation.

#### FR-T02 — Action proposal

The LLM produces an `ActionProposal`, not an executable command:

```json
{
  "proposal_id": "prop-001",
  "session_id": "demo-01",
  "tool": "control_access",
  "arguments": {
    "action": "open",
    "target": "driver_door"
  },
  "model_provider": "openai",
  "model_id": "gpt-5-mini",
  "source_turn_id": "turn-001"
}
```

#### FR-T03 — ViGuard Action Gateway

Every state-changing proposal must be sent to ViGuard. The gateway must:

1. validate tool and arguments;
2. canonicalize the proposal into a policy intent;
3. obtain the current immutable state snapshot itself;
4. evaluate the relevant gate rules;
5. return a typed decision;
6. issue a one-time permit only for an executable `ALLOW` path.

#### FR-T04 — Execution permit

The local pilot uses an immutable, in-process `ActionPermit`:

```json
{
  "permit_id": "permit-001",
  "proposal_digest": "sha256:...",
  "intent": "open_door",
  "rule_id": "R001",
  "state_version": 12,
  "policy_checksum": "sha256:...",
  "issued_at": "2026-08-03T10:00:00Z",
  "expires_at": "2026-08-03T10:00:02Z",
  "single_use": true
}
```

The permit is not a production security token. It exists to make authorization flow and replay prevention testable in the simulator.

#### FR-T05 — Vehicle Tool Gateway

Vehicle Tool Gateway is the only module allowed to call action handlers. It validates proposal digest, intent, expiry, use status and current execution context before consuming the permit.

No UI, LLM adapter, Agent Orchestrator, Guardrail classifier or response component may import or call action handlers directly.

### 10.3. P0 — Vehicle simulation

#### FR-V01 — Vehicle state model

State must be typed, versioned and grouped into at least:

- power and charging;
- motion and speed;
- transmission;
- access and locks;
- exterior/interior lighting;
- cabin positions;
- driving assistance;
- special modes;
- environment and occupancy;
- UI state;
- active actions.

#### FR-V02 — State invariants

The state machine must enforce coherent relationships, including:

- `gear == P` implies `speed == 0`;
- `speed > 0` implies `motion_state == MOVING`;
- an open door cannot simultaneously be reported locked;
- powered-off vehicle cannot keep AAC, HDA or autopark active;
- every successful atomic transition increments `state_version` exactly once;
- invalid compound transitions commit nothing.

#### FR-V03 — Dynamics controller

Accelerate, brake and stop are time-based deterministic transitions rather than instantaneous arbitrary edits. Each simulation tick emits state change events and invokes monitoring.

#### FR-V04 — Action handler registry

The implementation should use generic handlers rather than one class per intent:

- toggle;
- enum setter;
- access actuator;
- position actuator;
- timed transition;
- one-shot event;
- active action;
- compound action.

Startup validation must prove that all 47 action/UI intents have a handler or explicit refusal behavior, and all six query intents have no actuator handler.

#### FR-V05 — Operator Simulation Console

The UI must provide operator controls for power, speed, acceleration, braking, gear, environment and deterministic presets. Operator calls must be labeled and traced separately from agent calls.

#### FR-V06 — Observable execution

Each successful action must produce at least one of:

- visible state change;
- animation/transition;
- one-shot UI event;
- active action with status;
- query response grounded in state or approved knowledge.

### 10.4. P0 — Confirmation, monitoring and failure

#### FR-C01 — Confirmation

Confirmation records the proposal but does not grant live execution authority. On confirm, ViGuard reads fresh state and creates a new decision/permit. Confirmation is expiring, single-use and non-replayable.

#### FR-M01 — Continuous monitoring

All five existing monitor rules must be wired to state-change and manual-tick events. A monitor block or monitor evaluation error stops the active action fail-safe.

#### FR-E01 — Failure semantics

At minimum, the system distinguishes:

- model unavailable/timeout;
- malformed or unknown tool proposal;
- unsupported tool-to-intent mapping;
- policy unavailable/invalid;
- policy no-match/ambiguous;
- confirmation expired/replayed;
- permit invalid/expired/consumed;
- actuator rejected/failed/uncertain;
- monitor failure.

No error path may synthesize an `ALLOW` outcome or a success response.

### 10.5. P1 — Experience improvements

- Streaming response and action progress.
- Vietnamese ViVi persona with deterministic grounded fallback templates.
- Scenario library: parked, city, highway, rain, charging, HDA degradation and emergency stop.
- Visual vehicle representation with animated doors, lights, mirrors, windows and active ADAS indicators.
- Agent explanation showing proposed tool and why it was blocked, with technical detail collapsed by default.
- Parameter clarification for target door/window/seat when the user request is ambiguous.

### 10.6. P2 — Future considerations

- Speech input/output.
- Multimodal cabin/road input.
- Production RAG for feature explanations.
- Hardware-in-the-loop simulator.
- Signed or hardware-backed action capabilities.
- Formal workflow planner for multi-step vehicle tasks.
- OEM-approved policies for additional longitudinal/lateral control intents.

## 11. Architecture

### 11.1. Chosen design

```text
User / ViVi UI
      |
      v
Agent API
      |
      v
ViVi Agent Orchestrator -----> ModelProviderAdapter
      |                            |-- OpenAI: gpt-5-mini
      |                            `-- Gemini: gemini-3.6-flash
      |<------ ActionProposal -----|
      |
      v
ViGuard Action Gateway
      |-- Tool Schema + Intent Mapping
      |-- Vehicle State Snapshot
      |-- Constraint Engine
      |-- Confirmation Manager
      `-- ActionPermit Issuer
      |
      | ALLOW + one-time permit only
      v
Vehicle Tool Gateway
      |
      v
Action Handler Registry ---> Vehicle State Machine
      |                            |
      |                            `--> state_changed
      v                                     |
Execution Event                              v
      |                               Monitor Engine
      `----------> Agent Orchestrator <------'
                         |
                         v
                 Grounded ViVi response
```

### 11.2. Module boundaries

| Module | Input | Output | Must not do |
|---|---|---|---|
| Agent API | User message/session | Agent response/events | Call handlers directly |
| Agent Orchestrator | User turn, prior typed events | Clarification or action proposal | Authorize its own proposal |
| ModelProviderAdapter | Bounded prompt, tool schemas, provider config | Provider-neutral structured output | Access state store or actuator |
| Tool Mapper | Valid tool + arguments | Canonical intent + normalized args | Read user prose to invent an intent |
| ViGuard Action Gateway | Action proposal | Decision/error/permit | Execute an action |
| Permit Issuer | Allow decision + proposal digest | One-time permit | Issue on block/confirm/error |
| Vehicle Tool Gateway | Proposal + permit | Execution result | Accept raw LLM output |
| Handler Registry | Authorized command | State/event changes | External side effects |
| Vehicle State Machine | Valid transition | Versioned state/events | Accept partial invalid mutation |
| Monitor Engine | Active action + snapshot | Continue/stop decision | Continue after evaluation error |
| Response Composer | Typed decision/result facts | Vietnamese user response | Invent state or execution success |

### 11.3. Dependency rule

```text
LLM -> ActionProposal -> ViGuard -> ActionPermit -> Vehicle Tool Gateway
```

The permitted dependency direction is one-way. Vehicle handlers are not linked into the LLM adapter or Agent Orchestrator. Tests must scan imports and use an actuator spy to enforce this boundary.

### 11.4. Runtime sequence

```text
User -> Agent: "Mở cửa ghế lái"
Agent -> Model: message + registered tool schemas
Model --> Agent: control_access(open, driver_door)
Agent -> ViGuard: ActionProposal
ViGuard -> StateStore: snapshot()
ViGuard -> ConstraintEngine: evaluate(open_door, snapshot)
ConstraintEngine --> ViGuard: ALLOW + R001
ViGuard --> Agent: decision + one-time permit
Agent -> VehicleToolGateway: execute(proposal, permit)
VehicleToolGateway -> DoorHandler: execute authorized command
DoorHandler -> StateMachine: atomic mutation
StateMachine --> VehicleToolGateway: state@new_version
VehicleToolGateway --> Agent: ExecutionResult(SUCCEEDED)
Agent --> User: grounded success response
```

### 11.5. Model boundary

OpenAI and Gemini are interchangeable language/tool-selection providers, not safety components. Through the shared adapter, the selected model may:

- select a registered tool;
- fill schema-bound parameters;
- ask for clarification;
- choose among predefined workflows;
- verbalize typed outcomes and observations.

It may not:

- declare policy outcomes;
- mint or modify permits;
- provide authoritative vehicle state;
- execute Python/code;
- access network or arbitrary files;
- call an unregistered tool;
- claim action success before receiving `ExecutionResult`.

## 12. Domain model and contracts

### 12.1. Core entities

```text
AgentTurn
  turn_id, session_id, user_text, status, model_id, created_at

ActionProposal
  proposal_id, turn_id, tool, arguments, proposal_digest

CanonicalAction
  intent, normalized_arguments, behavior_id, policy_required

GuardrailDecision
  request_id, intent, outcome, rule_id, state_version,
  policy_checksum, reason_code, latency_ms

ActionPermit
  permit_id, proposal_digest, intent, rule_id, state_version,
  issued_at, expires_at, status

ExecutionResult
  execution_id, proposal_id, intent, handler, status,
  state_before_version, state_after_version, events, error

ActiveAction
  action_id, intent, status, started_at, last_monitor_rule,
  last_state_version
```

### 12.2. Action proposal to intent mapping

Mappings are configuration/code reviewed at startup. Examples:

| Tool call | Canonical intent |
|---|---|
| `control_access(open, driver_door)` | `open_door` |
| `control_access(open, trunk)` | `open_trunk` |
| `control_light(on, high_beam)` | `turnon_highbeam` |
| `set_drive_mode(sport)` | `switch_drivemode_sport` |
| `control_driver_assistance(hda, activate)` | `activate_hda` |
| `query_vehicle_state(speed)` | `get_current_speed` |
| `explain_vehicle_feature(hda)` | `explain_feature` |

Every current policy intent must be reachable through at least one mapping, and every mapping must resolve to exactly one policy intent.

### 12.3. Execution status

Execution uses a separate status namespace from policy outcomes:

```text
PENDING | RUNNING | SUCCEEDED | FAILED | REJECTED | STOPPED | UNCERTAIN
```

`ALLOW` means execution is authorized; it does not mean execution succeeded.

## 13. API proposal

### 13.1. Agent message

`POST /api/v1/agent/messages`

```json
{
  "session_id": "demo-01",
  "text": "mở cửa ghế lái"
}
```

Response:

```json
{
  "turn_id": "turn-001",
  "status": "COMPLETED",
  "message": "Vivi đã mở cửa ghế lái.",
  "proposal": {
    "tool": "control_access",
    "arguments": {"action": "open", "target": "driver_door"}
  },
  "decision": {
    "intent": "open_door",
    "outcome": "ALLOW",
    "rule_id": "R001",
    "state_version": 12
  },
  "execution": {
    "status": "SUCCEEDED",
    "state_after_version": 13
  }
}
```

### 13.2. Confirmation

- `POST /api/v1/agent/confirmations/{id}/confirm`
- `POST /api/v1/agent/confirmations/{id}/cancel`

### 13.3. Vehicle simulation

- `GET /api/v1/simulation/state`
- `POST /api/v1/simulation/operator/actions`
- `POST /api/v1/simulation/presets/{preset_id}`
- `POST /api/v1/simulation/tick`
- `GET /api/v1/simulation/actions/active`

Operator actions and agent actions must use distinct caller metadata and trace event types.

### 13.4. Agent diagnostics

- `GET /api/v1/agent/tools`
- `GET /api/v1/agent/capabilities`
- `GET /api/v1/agent/turns/{turn_id}/trace`
- `GET /api/v1/agent/coverage`

The coverage endpoint reports at least intent mapping, policy coverage, handler/responder coverage and test scenario coverage.

## 14. Security and safety design

### 14.1. Threat model

Untrusted inputs include user text, model output, tool arguments and UI state edits. The workbook is controlled configuration but still parsed as untrusted data. The model process is not trusted with execution authority.

Primary threats:

- prompt injection causes the model to request an unauthorized tool;
- model fabricates vehicle state or policy approval;
- malformed arguments exploit handler behavior;
- stale state is used after confirmation;
- permit is replayed or used for a different proposal;
- UI or developer code calls handlers directly;
- handler partially mutates state and then fails;
- monitor failure leaves an action active.

### 14.2. Controls

- closed tool registry and JSON Schema validation;
- exact proposal-to-intent mapping;
- fresh state snapshot owned by ViGuard;
- closed policy AST with fail-closed semantics;
- one-time proposal-bound permit;
- single Vehicle Tool Gateway;
- atomic state transitions;
- no external network for handlers;
- append-only typed trace;
- stop-on-error monitor behavior;
- startup coverage validation;
- actuator spy and dependency-boundary tests.

## 15. Evaluation strategy

### 15.1. Agent tool-selection evaluation

Dataset categories:

- clear Vietnamese commands for all 53 intents;
- paraphrases and informal speech;
- ambiguous target/parameter requests;
- negation, future and conditional requests;
- multi-action requests;
- prompt injection and fake-state claims;
- requests for unknown/unregistered capabilities;
- driving-control commands after the expanded policy is added.

Metrics:

- exact canonical intent accuracy;
- tool name accuracy;
- argument exact match;
- clarification precision/recall;
- invalid tool-call rate;
- unauthorized execution rate;
- end-to-end task completion rate;
- model and end-to-end latency.

Ship gates:

- 100% test coverage across the 53 catalog intents;
- 0 unauthorized actuator calls;
- 0 block-path actuator calls;
- 0 model-fabricated execution successes accepted by the system;
- tool-selection quality threshold must be set from a held-out project dataset before model acceptance.

No unmeasured accuracy claim is made in this document.

### 15.2. Vehicle behavior evaluation

- one allow and one non-allow scenario where policy supports both for each applicable intent;
- successful observable behavior for all 47 action/UI intents;
- grounded responses for all six query intents;
- state invariant property tests;
- atomic rollback tests for handler failure;
- deterministic dynamics tests for acceleration/braking/stop;
- all five monitor start/continue/stop paths;
- restart clears pending permits, confirmations and active actions.

### 15.3. Model comparison gate

`gpt-5-mini` and `gemini-3.6-flash` must be evaluated on the same Vietnamese held-out set. The release configuration chooses a primary provider based on measured tool/argument accuracy, access to a valid API key, latency and demo reliability. The comparison prioritizes tool/argument accuracy and failure safety over conversational style. The product must remain provider-neutral even if only one provider is enabled in a particular environment.

## 16. Success metrics

### 16.1. Leading metrics

| Metric | Initial target |
|---|---:|
| Intent behavior coverage | 53/53 |
| Action/UI handler or explicit refusal coverage | 47/47 |
| Query responder coverage | 6/6 |
| Existing rule load coverage | 109/109 |
| Monitor scenario coverage | 5/5 |
| Block-path actuator violations | 0 |
| Unregistered tool executions | 0 |
| Confirmation replay successes | 0 |
| Trace completeness for executed actions | 100% |

### 16.2. Diagnostic metrics

- model tool-selection accuracy and argument exact match;
- clarification rate;
- block/confirm/allow/query distribution;
- proposal-to-policy latency;
- model latency and total turn latency;
- execution success/failure/uncertain rate;
- permit rejection reasons;
- active actions stopped by monitoring;
- operator versus agent state mutation count.

## 17. Architecture options considered

### Option A — Thin deterministic agent after Guardrail

The Guardrail classifies and decides before ViVi receives anything; ViVi only routes outcomes.

**Advantages:** simplest, deterministic, easy to test.  
**Disadvantages:** does not realistically demonstrate an agent selecting and calling vehicle tools.

### Option B — LLM agent with direct simulator tools

The model receives tools and directly invokes handlers.

**Advantages:** natural agent behavior and minimal integration.  
**Disadvantages:** creates an authorization bypass, conflates intent with permission and undermines the ViGuard product claim.

### Option C — LLM action proposal with mandatory ViGuard enforcement

The model chooses a tool, but every tool call is intercepted, canonicalized, evaluated against fresh state and permitted once before execution.

**Advantages:** realistic agent control, enforceable safety boundary, complete traceability and independent agent/guardrail evaluation.  
**Disadvantages:** adds tool mapping, permit lifecycle and two separate error domains.

**Decision:** Adopt Option C.

## 18. Consequences and trade-offs

What becomes easier:

- demonstrating that a real agent can control the simulated vehicle without owning safety authority;
- testing model tool selection independently from policy correctness;
- proving that blocked actions cannot reach handlers;
- changing the model without changing safety policy;
- adding vehicle behaviors through a reviewed registry.

What becomes harder:

- coordinating agent errors, policy outcomes and execution statuses;
- maintaining exact tool-to-intent mappings;
- designing policies for new driving actions;
- keeping the simulator state coherent during timed transitions;
- explaining why an apparently correct tool proposal was denied.

## 19. Delivery plan and acceptance gates

### Phase 0 — Contract reconciliation

- Freeze exact 53-intent and 109-rule baseline from the workbook.
- Define tool schemas and exact tool-to-intent mappings.
- Define vehicle state schema and invariants.
- Decide which new dynamics intents the PM and safety owner approve.

**Gate:** all 53 intents have one mapping and behavior classification; no tool mapping is ambiguous.

### Phase 1 — Vehicle simulation foundation

- Vehicle State Machine and versioning.
- Generic handler registry.
- Power, transmission and deterministic motion controller.
- Operator Simulation Console endpoints and presets.

**Gate:** invariant, transition and rollback tests pass; operator can run, accelerate, brake and stop the vehicle.

### Phase 2 — Guarded action execution

- ActionProposal, Tool Mapper and ViGuard Action Gateway.
- One-time permit and Vehicle Tool Gateway.
- 47 action/UI behaviors and six query responders.

**Gate:** 53/53 behavior coverage; all blocked paths have zero handler calls.

### Phase 3 — ViVi model agent

- Provider-neutral adapter for OpenAI and Gemini, with deterministic auto-selection.
- Structured tool calls, clarification and grounded response composition.
- Vietnamese evaluation set and model comparison.

**Gate:** model meets the agreed held-out quality threshold; malformed/model-timeout paths execute nothing.

### Phase 4 — Confirmation, monitor and demo readiness

- Fresh-state confirmation flow.
- Five monitor scenarios.
- Animation/events, scenario library and full trace.
- Performance benchmark and demo rehearsal.

**Gate:** all P0 acceptance criteria pass on the target demo machine.

## 20. Definition of done

The ViVi Vehicle Agent Simulator is complete when:

- all 53 existing intents are reachable through the Agent and have observable behavior;
- all 109 existing policy rules load and retain source rule IDs;
- all 47 action/UI intents have a handler or the explicit `NOT_VOICE_ACTIONABLE` refusal behavior;
- all six query intents return grounded answers or `UNKNOWN` without an actuator call;
- the simulated vehicle can power on, move, accelerate, brake, stop and shift gear coherently;
- agent exposure of new driving actions is blocked until corresponding policy coverage exists;
- every state-changing model proposal passes through ViGuard and the Vehicle Tool Gateway;
- no block, error or unconfirmed path calls an action handler;
- confirmation uses fresh state and cannot be replayed;
- all five monitor rules can stop the associated active action;
- state mutations are atomic, versioned and traceable;
- the agent never reports success without a successful execution result;
- model failure cannot create a side effect;
- UI clearly labels the environment as a simulation;
- automated coverage, safety, integration and end-to-end tests pass on the target machine.

## 21. Open decisions

### Blocking before dynamics tools are exposed to the agent

1. **PM + Safety:** Which new intents represent start, accelerate, brake, stop and emergency stop?
2. **PM + Safety:** Are these actions voice-actionable, confirmation-required or operator-only?
3. **Safety:** What mock constraints and monitor conditions apply to each new dynamics intent?
4. **Engineering:** What maximum simulated acceleration/deceleration values keep scenarios clear and deterministic?

### Non-blocking during implementation

1. **AI Engineering:** Final provider priority and exact model IDs after the Vietnamese evaluation and API-key availability check.
2. **Design:** Visual representation of vehicle transitions and active ADAS actions.
3. **QA:** Size and composition of the held-out Vietnamese tool-selection set.
4. **Product:** Whether compound user requests are rejected, clarified or supported through predefined workflows in the first release.

## 22. Explicit claim boundary

This implementation can demonstrate that:

- an LLM agent selects and requests vehicle tools;
- every request is evaluated against mock vehicle state and the loaded policy;
- blocked or unconfirmed requests do not reach the mock actuator;
- authorized requests produce coherent simulated behavior;
- decisions and actions are traceable end to end.

It cannot demonstrate that:

- the policy values are correct for a physical VinFast vehicle;
- the model is safe for unrestricted real-world vehicle control;
- the in-process permit resists a malicious production developer;
- the simulator behavior matches CAN/ECU timing or failure characteristics;
- the system satisfies an automotive safety standard or regulatory approval.
