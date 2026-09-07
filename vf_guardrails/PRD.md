# PRODUCT REQUIREMENT DOCUMENT (PRD) & TECHNICAL SPECIFICATION
## System Name: VinFast Context-Aware AI Guardrail Engine (Local Embedded)
## Target Platform: Python 3.10+ Local Simulation System
## Execution Model: Single-process Embedded Python Package (Zero HTTP Overhead)

---

### 1. OVERVIEW & OBJECTIVES
Building a lightweight, high-performance, context-aware AI Guardrail engine designed specifically for VinFast Electric Vehicle (EV) voice assistant systems. 

Unlike standard text-based LLM guardrails, this system is a Cyber-Physical Operational Guardrail. It evaluates driver intent extracted from natural language queries against real-time vehicle telemetry (VehicleState) to enforce safety constraints before commands reach the vehicle's execution logic or CAN-Bus.

* Primary Scope: Context-Aware Safety Rules Evaluation (Intent + Vehicle State Matrix).
* Key Technical Targets:
    * Latency Overhead: < 10ms (Deterministic In-Memory Execution).
    * Architecture: Native Python Engine (Declarative YAML Rules + Hybrid Intent Classifier + State Engine).
    * Environment: 100% Local / Embedded System.

---

### 2. REPOSITORY STRUCTURE TO GENERATE

Generate the project according to the following strict Directory Tree:

vinfast-guardrail-local/
├── config/                          # Declarative Policy & Pattern Configs
│   ├── safety_rules.yaml            # Safety Rules Policy Matrix (Intent + Vehicle State)
│   └── intent_keywords.json         # Keyword mapping for Aho-Corasick Classifier
├── data/                            # Test Datasets
│   └── vinfast_test_data.json       # 2,000 synthetic test samples
├── src/                             # Core Source Code
│   ├── __init__.py
│   ├── models.py                    # Pydantic Schemas (VehicleState, GuardrailResult)
│   ├── intent_classifier.py         # Hybrid Intent Classifier (Aho-Corasick + Fallback)
│   ├── safety_engine.py             # Deterministic Rule Evaluation Engine
│   └── guardrail.py                 # Main Wrapper Facade Class (VinFastGuardrail)
├── tests/                           # Testing & Benchmark Suite
│   ├── test_guardrail.py            # Pytest Unit Tests
│   └── run_benchmark.py             # Benchmark Script for 2,000 samples
├── app_sim.py                       # Interactive CLI Local Simulation App
├── requirements.txt                 # Lightweight dependencies
└── README.md                        # Documentation & Quickstart

---

### 3. DETAILED DATA MODELS & SCHEMAS (src/models.py)

Implement Pydantic v2 schemas:

from pydantic import BaseModel, Field

class VehicleState(BaseModel):
    # Dynamics & Drive System
    speed_kmh: float = Field(default=0.0, description="Vehicle speed in km/h")
    gear: str = Field(default="P", description="Gear position: P, R, N, D")
    doors_locked: bool = Field(default=True, description="Door lock status")
    trunk_open: bool = Field(default=False, description="Trunk status")
    
    # Seats & Interior Configuration (Anti-Submarining & Comfort)
    driver_seat_angle_deg: float = Field(default=95.0, description="Driver seat recline angle in degrees")
    passenger_seat_angle_deg: float = Field(default=95.0, description="Passenger seat recline angle in degrees")
    has_passenger: bool = Field(default=False, description="Passenger presence sensor")
    
    # Environment & Battery
    ambient_light: str = Field(default="DAY", description="Environmental light: DAY or NIGHT")
    rain_sensor: bool = Field(default=False, description="Rain detection sensor")
    battery_level: float = Field(default=85.0, description="Battery state of charge (%)")
    tire_pressure_psi: float = Field(default=32.0, description="Average tire pressure in PSI")

class GuardrailResult(BaseModel):
    intent: str
    action: str          # "PASS" or "BLOCK"
    response: str        # Human-readable response / safety mitigation prompt
    reason: str          # Structured Reason Code
    latency_ms: float    # Execution time in milliseconds

---

### 4. DECLARATIVE SAFETY POLICY MATRIX (config/safety_rules.yaml)

Define at least 36 Automotive Intent Rules. Implement in YAML format using the following structure:

version: "1.0"
domain: "vinfast_automotive_safety"

policies:
  - id: POL_001_OPEN_TRUNK
    intent: INTENT_OPEN_TRUNK
    description: "Block trunk opening while vehicle is moving"
    target_state:
      speed_kmh: { operator: ">", value: 0 }
    logic: OR
    enforcement:
      action: BLOCK
      reason: CRITICAL_SPEED_SAFETY
      message_template: "Xe đang chạy với tốc độ {speed_kmh} km/h. Không thể mở cốp sau vì lý do an toàn."

  - id: POL_002_DRIVER_SEAT_RECLINE
    intent: INTENT_RECLINE_DRIVER_SEAT
    description: "Restrict driver seat angle > 110 deg when moving"
    target_state:
      speed_kmh: { operator: ">", value: 0 }
      driver_seat_angle_deg: { operator: ">", value: 110 }
    logic: AND
    enforcement:
      action: BLOCK
      reason: SEAT_RECLINE_UNSAFE
      message_template: "Xe đang di chuyển ({speed_kmh} km/h). Góc ngả ghế lái tối đa cho phép là 110° để đảm bảo an toàn."

  - id: POL_003_NIGHT_LIGHTING
    intent: INTENT_TURN_OFF_HEADLIGHTS
    description: "Prevent turning off headlights at night while driving"
    target_state:
      speed_kmh: { operator: ">", value: 0 }
      ambient_light: { operator: "==", value: "NIGHT" }
    logic: AND
    enforcement:
      action: BLOCK
      reason: NIGHT_VISIBILITY_SAFETY
      message_template: "Không thể tắt đèn pha khi xe đang di chuyển vào buổi tối."

  # (Implement remaining intents including INTENT_OPEN_DOOR, INTENT_ACTIVATE_HANDBRAKE, INTENT_ENABLE_CAMP_MODE, INTENT_OPEN_CHARGE_PORT, etc.)

---

### 5. CORE MODULE REQUIREMENTS

#### A. src/intent_classifier.py (Hybrid Fast-Path Classifier)
* Layer 1 (Fast-Path): Use pyahocorasick to match query keywords against config/intent_keywords.json. Execution time must be < 2ms.
* Layer 2 (Fallback Placeholder): If Layer 1 yields no match, return "INTENT_UNKNOWN" gracefully without crashing.

#### B. src/safety_engine.py (Deterministic Safety Engine)
* Loads config/safety_rules.yaml upon initialization.
* Evaluates input intent and VehicleState by checking numerical and categorical conditions (>, <, ==, !=).
* Supports both AND and OR multi-condition logic.
* Formats the message_template dynamically using current VehicleState attributes.

#### C. src/guardrail.py (Main Facade Wrapper)
* Provides class VinFastGuardrail with method .process(user_query: str, state: VehicleState) -> GuardrailResult.
* Uses time.perf_counter() to measure execution latency down to sub-millisecond precision.

#### D. app_sim.py (Interactive Simulation CLI)
* A clean CLI interface simulating the car's voice assistant loop.
* Displays real-time vehicle state at startup.
* Allows live driver query input, prints detected Intent, Latency (ms), Decision (BLOCK/PASS), and Guardrail response.

#### E. tests/run_benchmark.py (Automated Benchmark Engine)
* Loads 2,000 synthetic test cases from data/vinfast_test_data.json.
* Executes queries through VinFastGuardrail.
* Calculates and prints formatted summary report: Total Samples, Block Rate (%), False Positive Rate (FPR %), and Average Latency (ms).

---

### 6. DEPENDENCIES (requirements.txt)

Keep runtime dependencies minimal and lightweight:

pydantic>=2.0.0
pyahocorasick>=2.0.0
pyyaml>=6.0.0
pytest>=7.0.0

---

### 7. EXECUTION INSTRUCTIONS FOR CODING AGENT

1. Create all directories and files specified in the tree structure.
2. Populate config/safety_rules.yaml with comprehensive rules covering all key vehicle intents.
3. Write clean, type-annotated, production-grade Python code for all src/ modules.
4. Implement app_sim.py and tests/run_benchmark.py.
5. Ensure zero external network calls; everything must run 100% locally with latency under 10ms.