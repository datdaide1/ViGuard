# TASK REQUIREMENT: Create an Interactive Vehicle Simulator (HTML/CSS/JS)

## 1. Goal & Context
Create an interactive HTML/CSS/JS application split into 3 separate files in a single folder (`simulator/`) that visually simulates the behavior of a VinFast Electric Vehicle (EV) responding to voice commands evaluated by an AI Guardrail Engine. 

The simulator must NOT just print text responses; it must include a **Real-Time Visual Car Canvas/SVG** where mechanical components (trunk, headlights, driver seat) physically animate based on whether the command is `PASSED` or `BLOCKED` by the context-aware safety guardrail.

---

## 2. Technical Architecture & Component Breakdown

### A. Component 1: Visual Car Viewport (SVG/Canvas Animation Area)
* Render a sleek 2D side-view silhouette of an EV (VinFast style) using native SVG.
* **Interactive SVG Elements:**
  * **Trunk Door (`#trunkDoor`):** An animated door path at the rear. When `trunk_open == true`, apply a CSS transform rotation (`rotate(-45deg)`) to visually open the trunk.
  * **Headlight Beams (`#headlightBeam`):** A semi-transparent yellow polygon emitting from the front lights. Toggle CSS opacity (`0` for OFF, `0.6` for ON).
  * **Driver Seat (`#driverSeat`):** A seat-back vector inside the cabin. Apply CSS transform rotation based on `driver_seat_angle_deg` parameter (e.g., recline backwards from $95^\circ$ to $115^\circ$).
* **Live Telemetry Badges:** Overlay real-time indicators for `Speed (km/h)`, `Trunk Status (OPEN/CLOSED)`, and `Headlights Status (ON/OFF)`.

### B. Component 2: Telemetry Control Panel (Inputs)
Provide interactive input controls to simulate real-time vehicle state (Telemetry Data):
* **Vehicle Speed Slider:** Range `0` to `120 km/h` (Default: `0`).
* **Ambient Light Dropdown:** Options `DAY` / `NIGHT` (Default: `DAY`).
* **Driver Seat Angle Slider:** Range `90` to `130 degrees` (Default: `95`).

### C. Component 3: Voice Command & Guardrail Engine Simulation
* **Input Field:** Text input for driver query (e.g., "Mở cốp sau xe", "Tắt đèn pha", "Ngả ghế lái").
* **Execution Button:** "PHÁT LỆNH GIỌNG NÓI".
* **JavaScript Guardrail Evaluation Logic:**
  * **Intent Recognition:** Map natural language query keywords to intents (`INTENT_OPEN_TRUNK`, `INTENT_TURN_OFF_HEADLIGHTS`, `INTENT_RECLINE_DRIVER_SEAT`) tương tự logic ở Tầng 1 / Tầng 2.
  * **Safety Rules Matrix (Đồng bộ từ config/safety_rules.yaml):**
    * **POL_001_OPEN_TRUNK** (`INTENT_OPEN_TRUNK`): Chặn (`BLOCK`) nếu `speed_kmh` > 0.0. Thông báo lỗi: *"Xe đang chạy với tốc độ {speed_kmh} km/h. Không thể mở cốp sau vì lý do an toàn."* (Điền động tốc độ thực tế). Nếu được cho qua (`PASS`), kích hoạt hoạt họa mở cốp trên SVG.
    * **POL_002_DRIVER_SEAT_RECLINE** (`INTENT_RECLINE_DRIVER_SEAT`): Chặn (`BLOCK`) nếu `speed_kmh` > 0.0 VÀ `driver_seat_angle_deg` > 110.0. Thông báo lỗi: *"Xe đang di chuyển ({speed_kmh} km/h). Góc ngả ghế lái tối đa cho phép là 110° để đảm bảo an toàn."*. Nếu được cho qua (`PASS`), ngả ghế trên SVG theo góc kéo.
    * **POL_003_NIGHT_LIGHTING** (`INTENT_TURN_OFF_HEADLIGHTS`): Chặn (`BLOCK`) nếu `speed_kmh` > 0.0 VÀ `ambient_light` == "NIGHT". Thông báo lỗi: *"Không thể tắt đèn pha khi xe đang di chuyển vào buổi tối."*. Nếu được cho qua (`PASS`), tắt chùm sáng đèn pha trên SVG.

### D. Component 4: Status Output Banner
* **Passed State:** Green banner (`status-pass`), display "🟢 [GUARDRAIL PASS]", explain execution action, and update SVG elements in real-time.
* **Blocked State:** Red banner (`status-block`), display "🛑 [GUARDRAIL CHẶN AN TOÀN]", show exact violation reason, and KEEP SVG elements UNCHANGED.

---

## 3. Design & UI Specifications
* **Theme:** Dark Mode Automotive Dashboard aesthetic (Deep Slate Blue background `#0f172a`, Dark Slate Card backgrounds `#1e293b`, Electric Blue highlights `#38bdf8`).
* **Layout:** Responsive 2-column grid system (Top: Full-width Car Visual Viewport; Bottom Left: Telemetry Controls; Bottom Right: Command Input & Guardrail Result Box).
* **Dependencies:** Cho phép sử dụng các thư viện bên ngoài qua CDN (TailwindCSS, Google Fonts như Inter/Outfit, FontAwesome hoặc Lucide Icons) để xây dựng giao diện hiện đại và hoạt họa mượt mà. Các tệp giao diện, kiểu dáng và logic sẽ được tách riêng thành 3 tệp (`index.html`, `style.css`, `app.js`) trong cùng một thư mục `simulator/`.

---

## 4. Execution Step for Agent
Generate the complete code split into 3 files: `index.html`, `style.css`, and `app.js` inside the `simulator/` directory. Ensure `index.html` correctly links to `style.css` and `app.js`. Provide smooth CSS transitions for SVG animations (trunk door rotation, headlight opacity, seat recline) and functional JavaScript event handlers.