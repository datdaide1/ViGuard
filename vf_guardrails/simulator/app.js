// Trạng thái nội tại của xe giả lập
const vehicleState = {
    speed_kmh: 0.0,
    gear: "P",
    doors_locked: true,
    trunk_open: false,
    driver_seat_angle_deg: 95.0,
    passenger_seat_angle_deg: 95.0,
    has_passenger: false,
    ambient_light: "DAY",
    rain_sensor: false,
    battery_level: 85.0,
    tire_pressure_psi: 32.0,
    headlights_on: true // Trạng thái đèn pha khởi đầu là bật
};

// Bản đồ luật an toàn đồng bộ chính xác từ config/safety_rules.yaml
const safetyRules = {
    POL_001_OPEN_TRUNK: {
        intent: "INTENT_OPEN_TRUNK",
        evaluate: (state) => state.speed_kmh > 0.0,
        reason: "CRITICAL_SPEED_SAFETY",
        message_template: "Xe đang chạy với tốc độ {speed_kmh} km/h. Không thể mở cốp sau vì lý do an toàn."
    },
    POL_002_DRIVER_SEAT_RECLINE: {
        intent: "INTENT_RECLINE_DRIVER_SEAT",
        evaluate: (state, targetAngle) => state.speed_kmh > 0.0 && targetAngle > 110.0,
        reason: "SEAT_RECLINE_UNSAFE",
        message_template: "Xe đang di chuyển ({speed_kmh} km/h). Góc ngả ghế lái tối đa cho phép là 110° để đảm bảo an toàn."
    },
    POL_003_NIGHT_LIGHTING: {
        intent: "INTENT_TURN_OFF_HEADLIGHTS",
        evaluate: (state) => state.speed_kmh > 0.0 && state.ambient_light === "NIGHT",
        reason: "NIGHT_VISIBILITY_SAFETY",
        message_template: "Không thể tắt đèn pha khi xe đang di chuyển vào buổi tối."
    }
};

// Từ điển ánh xạ từ khóa sang Intent (Tiếng Việt)
const intentKeywords = {
    INTENT_OPEN_TRUNK: {
        actions: ["mở", "bật", "giúp mở"],
        entities: ["cốp", "cốp sau", "frunk", "khoang hành lý"]
    },
    INTENT_RECLINE_DRIVER_SEAT: {
        actions: ["ngả", "nghiêng", "hạ", "lùi", "chỉnh"],
        entities: ["ghế lái", "ghế tài", "ghế"]
    },
    INTENT_TURN_OFF_HEADLIGHTS: {
        actions: ["tắt", "tắt đi"],
        entities: ["đèn pha", "đèn trước", "đèn chiếu sáng", "đèn xe", "đèn"]
    },
    INTENT_TURN_ON_HEADLIGHTS: {
        actions: ["bật", "mở", "bật đi"],
        entities: ["đèn pha", "đèn trước", "đèn chiếu sáng", "đèn xe", "đèn"]
    }
};

// Đồng bộ trạng thái xe lên Giao diện người dùng
function syncUI() {
    // Cập nhật các hiển thị số và vị trí của Sliders
    document.getElementById('speedValue').textContent = Math.round(vehicleState.speed_kmh);
    document.getElementById('speedSlider').value = vehicleState.speed_kmh;
    document.getElementById('ambientSelect').value = vehicleState.ambient_light;
    document.getElementById('seatValue').textContent = Math.round(vehicleState.driver_seat_angle_deg);
    document.getElementById('seatSlider').value = vehicleState.driver_seat_angle_deg;

    // Cập nhật các Badges trên đầu của SVG car viewport
    document.getElementById('badgeSpeed').textContent = Math.round(vehicleState.speed_kmh);
    document.getElementById('badgeSeat').textContent = Math.round(vehicleState.driver_seat_angle_deg);

    // Cập nhật cốp sau trên badge và SVG
    const badgeTrunk = document.getElementById('badgeTrunk');
    const carSvg = document.getElementById('carSvg');
    if (vehicleState.trunk_open) {
        badgeTrunk.textContent = "OPEN";
        badgeTrunk.className = "text-rose-400 font-bold";
        carSvg.classList.add('trunk-open');
    } else {
        badgeTrunk.textContent = "CLOSED";
        badgeTrunk.className = "text-slate-400 font-bold";
        carSvg.classList.remove('trunk-open');
    }

    // Cập nhật đèn pha trên badge, chùm sáng SVG và màu sắc tương ứng
    const badgeLights = document.getElementById('badgeLights');
    const headlightBeam = document.getElementById('headlightBeam');
    if (vehicleState.headlights_on) {
        badgeLights.textContent = "ON";
        badgeLights.className = "text-yellow-400 font-bold";
        headlightBeam.classList.remove('opacity-0');
        headlightBeam.classList.add('opacity-100');
    } else {
        badgeLights.textContent = "OFF";
        badgeLights.className = "text-slate-400 font-bold";
        headlightBeam.classList.remove('opacity-100');
        headlightBeam.classList.add('opacity-0');
    }

    // Cập nhật góc ngả của lưng ghế lái SVG bằng biến CSS
    const seatAngleRotation = vehicleState.driver_seat_angle_deg - 95.0; // Góc lệch so với mặc định 95°
    document.getElementById('driverSeatBack').style.setProperty('--seat-rotate', `${seatAngleRotation}deg`);

    // Cập nhật tốc độ xoay của bánh xe
    updateWheelRotation();
}

// Cập nhật hoạt họa xoay bánh xe dựa vào tốc độ xe điện
function updateWheelRotation() {
    const rearWheel = document.getElementById('rearWheel');
    const frontWheel = document.getElementById('frontWheel');
    
    if (vehicleState.speed_kmh > 0) {
        rearWheel.classList.add('wheel-spinning');
        frontWheel.classList.add('wheel-spinning');
        
        // Thời gian xoay 360 độ tỉ lệ nghịch với tốc độ xe
        const spinDuration = Math.max(0.1, 15 / vehicleState.speed_kmh); 
        rearWheel.style.setProperty('--spin-speed', `${spinDuration}s`);
        frontWheel.style.setProperty('--spin-speed', `${spinDuration}s`);
    } else {
        rearWheel.classList.remove('wheel-spinning');
        frontWheel.classList.remove('wheel-spinning');
    }
}

// Thiết lập câu thoại mẫu khi người dùng nhấn nút gợi ý
function setSampleQuery(text) {
    document.getElementById('queryInput').value = text;
}

// Phân tích câu thoại của tài xế để nhận diện Intent và trích xuất thực thể
function analyzeIntent(query) {
    const cleanQuery = query.trim().toLowerCase();
    
    let matchedIntent = "INTENT_UNKNOWN";
    let targetValue = null;

    // Duyệt qua từ điển để khớp Intent
    for (const [intentName, patterns] of Object.entries(intentKeywords)) {
        const hasAction = patterns.actions.some(act => cleanQuery.includes(act));
        const hasEntity = patterns.entities.some(ent => cleanQuery.includes(ent));
        
        if (hasAction && hasEntity) {
            matchedIntent = intentName;
            break;
        }
    }

    // Nếu là ngả ghế lái, cố gắng tìm góc ngả bằng Regex
    if (matchedIntent === "INTENT_RECLINE_DRIVER_SEAT") {
        const angleMatch = cleanQuery.match(/(\d+)\s*(độ|deg)/);
        if (angleMatch) {
            targetValue = parseInt(angleMatch[1]);
        } else {
            targetValue = 115; // Mặc định ngả ghế xuống 115 độ nếu không nói rõ số
        }
    }

    return { intent: matchedIntent, targetValue };
}

// Đánh giá các quy tắc an toàn (Guardrail Engine)
function evaluateGuardrail(intent, targetValue) {
    let decision = { action: "PASS", reason: "NO_SAFETY_VIOLATION", message: "Yêu cầu hợp lệ và an toàn. Đang gửi lệnh thực thi..." };

    if (intent === "INTENT_OPEN_TRUNK") {
        const rule = safetyRules.POL_001_OPEN_TRUNK;
        if (rule.evaluate(vehicleState)) {
            decision.action = "BLOCK";
            decision.reason = rule.reason;
            decision.message = rule.message_template.replace("{speed_kmh}", Math.round(vehicleState.speed_kmh));
        }
    } else if (intent === "INTENT_RECLINE_DRIVER_SEAT") {
        const rule = safetyRules.POL_002_DRIVER_SEAT_RECLINE;
        if (rule.evaluate(vehicleState, targetValue)) {
            decision.action = "BLOCK";
            decision.reason = rule.reason;
            decision.message = rule.message_template.replace("{speed_kmh}", Math.round(vehicleState.speed_kmh));
        }
    } else if (intent === "INTENT_TURN_OFF_HEADLIGHTS") {
        const rule = safetyRules.POL_003_NIGHT_LIGHTING;
        if (rule.evaluate(vehicleState)) {
            decision.action = "BLOCK";
            decision.reason = rule.reason;
            decision.message = rule.message_template;
        }
    }

    return decision;
}

// Thực thi lệnh giọng nói khi bấm nút
function executeCommand() {
    const queryInput = document.getElementById('queryInput');
    const query = queryInput.value.trim();
    
    if (!query) {
        alert("Vui lòng nhập câu thoại trước khi thực hiện!");
        return;
    }

    // Hiển thị trạng thái đang xử lý
    document.getElementById('waitingState').classList.remove('hidden');
    document.getElementById('resultContent').classList.add('hidden');

    const startTime = performance.now();

    // 1. Phân tích Intent và thực thể
    const { intent, targetValue } = analyzeIntent(query);

    // 2. Chạy bộ lọc an toàn Guardrail
    const guardrailResult = evaluateGuardrail(intent, targetValue);

    // Giả lập độ trễ siêu nhỏ của local engine (0.01ms - 0.2ms) kết hợp chút thời gian render
    setTimeout(() => {
        const latencyMs = (performance.now() - startTime) + 0.012; // Cộng độ trễ nền hệ thống

        // 3. Thực thi hành động vật lý nếu PASS
        if (guardrailResult.action === "PASS") {
            if (intent === "INTENT_OPEN_TRUNK") {
                vehicleState.trunk_open = true;
            } else if (intent === "INTENT_TURN_OFF_HEADLIGHTS") {
                vehicleState.headlights_on = false;
            } else if (intent === "INTENT_TURN_ON_HEADLIGHTS") {
                vehicleState.headlights_on = true;
            } else if (intent === "INTENT_RECLINE_DRIVER_SEAT") {
                vehicleState.driver_seat_angle_deg = targetValue;
            }
            // Cập nhật lại UI sau khi thay đổi trạng thái
            syncUI();
        }

        // 4. Hiển thị kết quả lên màn hình Dashboard
        document.getElementById('waitingState').classList.add('hidden');
        const resultContent = document.getElementById('resultContent');
        resultContent.classList.remove('hidden');

        // Điền dữ liệu
        document.getElementById('resultIntent').textContent = intent;
        document.getElementById('resultLatency').textContent = `${latencyMs.toFixed(3)} ms`;
        document.getElementById('resultResponse').textContent = guardrailResult.message;

        const statusBanner = document.getElementById('statusBanner');
        const statusIcon = document.getElementById('statusIcon');
        const statusText = document.getElementById('statusText');
        const resultCard = document.getElementById('resultCard');

        if (guardrailResult.action === "BLOCK") {
            // Hiển thị Banner chặn màu đỏ
            statusBanner.className = "px-4 py-2.5 rounded-xl flex items-center space-x-2.5 text-sm font-bold tracking-wide status-block";
            statusIcon.textContent = "🛑";
            statusText.textContent = "GUARDRAIL CHẶN AN TOÀN";
            
            // Hiển thị hiệu ứng đỏ nhẹ viền ngoài kết quả
            resultCard.classList.add('ring-2', 'ring-rose-500/20');
            resultCard.classList.remove('ring-2', 'ring-emerald-500/20');
        } else {
            // Hiển thị Banner cho phép màu xanh lá
            statusBanner.className = "px-4 py-2.5 rounded-xl flex items-center space-x-2.5 text-sm font-bold tracking-wide status-pass";
            statusIcon.textContent = "🟢";
            statusText.textContent = "GUARDRAIL PASS";
            
            // Hiển thị hiệu ứng xanh nhẹ viền ngoài kết quả
            resultCard.classList.add('ring-2', 'ring-emerald-500/20');
            resultCard.classList.remove('ring-2', 'ring-rose-500/20');
        }

    }, 300); // Thêm 300ms độ trễ mô phỏng để giao diện không bị giật
}

// Thiết lập bộ lắng nghe sự kiện của Telemetry Control Panel
function setupEventListeners() {
    // Thay đổi tốc độ xe
    const speedSlider = document.getElementById('speedSlider');
    speedSlider.addEventListener('input', (e) => {
        vehicleState.speed_kmh = parseFloat(e.target.value);
        // Nếu xe bắt đầu chạy, tự động khóa cửa và đóng cốp để đảm bảo an toàn vật lý
        if (vehicleState.speed_kmh > 0) {
            vehicleState.trunk_open = false;
        }
        syncUI();
    });

    // Thay đổi ánh sáng ban ngày/ban đêm
    const ambientSelect = document.getElementById('ambientSelect');
    ambientSelect.addEventListener('change', (e) => {
        vehicleState.ambient_light = e.target.value;
        syncUI();
    });

    // Thay đổi góc ngả ghế lái trực tiếp bằng slider thủ công
    const seatSlider = document.getElementById('seatSlider');
    seatSlider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        
        // Chạy qua Guardrail khi đổi góc ghế thủ công để mô phỏng tính năng an toàn tự động
        const targetAngle = val;
        const tempState = { ...vehicleState, driver_seat_angle_deg: targetAngle };
        
        // Nếu xe đang chạy (> 0 km/h) và kéo quá 110 độ thì chặn việc kéo
        if (vehicleState.speed_kmh > 0 && targetAngle > 110.0) {
            // Hiển thị chặn ngay lập tức trên panel kết quả
            document.getElementById('waitingState').classList.add('hidden');
            const resultContent = document.getElementById('resultContent');
            resultContent.classList.remove('hidden');
            
            document.getElementById('resultIntent').textContent = "INTENT_RECLINE_DRIVER_SEAT";
            document.getElementById('resultLatency').textContent = "0.010 ms";
            
            const rule = safetyRules.POL_002_DRIVER_SEAT_RECLINE;
            document.getElementById('resultResponse').textContent = rule.message_template.replace("{speed_kmh}", Math.round(vehicleState.speed_kmh));
            
            const statusBanner = document.getElementById('statusBanner');
            statusBanner.className = "px-4 py-2.5 rounded-xl flex items-center space-x-2.5 text-sm font-bold tracking-wide status-block";
            document.getElementById('statusIcon').textContent = "🛑";
            document.getElementById('statusText').textContent = "GUARDRAIL CHẶN AN TOÀN";
            
            const resultCard = document.getElementById('resultCard');
            resultCard.classList.add('ring-2', 'ring-rose-500/20');
            resultCard.classList.remove('ring-2', 'ring-emerald-500/20');
            
            // Trả slider về 110 độ
            e.target.value = 110;
            vehicleState.driver_seat_angle_deg = 110;
        } else {
            vehicleState.driver_seat_angle_deg = targetAngle;
        }
        syncUI();
    });

    // Nút thực thi lệnh giọng nói
    const btnExecute = document.getElementById('btnExecute');
    btnExecute.addEventListener('click', executeCommand);

    // Lắng nghe phím Enter trong ô nhập câu thoại
    const queryInput = document.getElementById('queryInput');
    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            executeCommand();
        }
    });
}

// Khởi chạy khi tài liệu HTML được tải xong
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    syncUI();
});
