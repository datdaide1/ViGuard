# Product Requirements Document (PRD): ViGuard cho ViVi Agent Simulator

## 1. Tóm tắt điều hành

ViGuard là một lớp bảo vệ và ra quyết định **nằm trước, độc lập với ViVi Agent**. Sản phẩm trong phạm vi tài liệu này là một hệ thống mô phỏng ViVi Agent nhận đầu vào văn bản: giao diện gửi câu lệnh như “mở cửa xe” vào Guardrail; Guardrail xác định ý định qua ba tầng T1/T2/T3, đọc trạng thái xe mô phỏng, đối chiếu điều kiện ràng buộc và trả một trong bảy kết quả; chỉ sau đó ViVi Agent mới phản hồi hoặc thực thi một hành động giả lập.

Mục tiêu của pilot không phải tạo một trợ lý hội thoại hoàn chỉnh hay điều khiển xe thật. Pilot phải chứng minh bằng phần mềm chạy được rằng:

1. Guardrail có thể nhận diện đủ danh mục **53 ý định** trước khi yêu cầu tới Agent.
2. Một câu lệnh hợp lệ về ngôn ngữ chưa chắc được phép thực hiện; quyết định cuối cùng phải dựa trên trạng thái xe.
3. Toàn bộ **109 rule policy** có thể được nạp, kiểm tra và thực thi nhất quán.
4. Mọi đường bị chặn đều không gọi bộ thực thi.
5. Người xem demo có thể quan sát toàn bộ chuỗi nguyên nhân từ text tới kết quả cuối.

### 1.1. Cách đọc tài liệu

Người cần hiểu sản phẩm nên đọc phần 2 đến phần 8 để nắm bài toán, phạm vi và trải nghiệm demo. Nhóm triển khai dùng phần 10 đến phần 14 làm nguồn yêu cầu và tiêu chí nghiệm thu. Nhóm đánh giá dùng phần 15 đến phần 18 để hiểu cách đo và giới hạn của bằng chứng. Tài liệu kiến trúc liên kết ở đầu trang giải thích cách hiện thực các yêu cầu này; PRD không thay thế thiết kế kỹ thuật.

## 2. Mô tả bài toán

### 2.1. Vấn đề sản phẩm

Nếu một ViVi-like agent chỉ dùng LLM để hiểu và làm theo câu lệnh, nó có thể gặp ba nhóm rủi ro:

- **Rủi ro ngôn ngữ:** prompt injection, jailbreak hoặc câu mơ hồ khiến agent hiểu sai intent.
- **Rủi ro trạng thái:** câu “mở cửa xe” đúng về ngôn ngữ nhưng có thể nguy hiểm khi xe đang chạy.
- **Rủi ro thực thi:** agent gọi action dù policy đã block, hoặc thực thi trước khi người dùng xác nhận.

Một bộ phân loại độc lập cũng chưa đủ. Nó chỉ trả lời “người dùng muốn gì”, không trả lời “có được làm trong trạng thái hiện tại không”. Vì vậy Guardrail gồm hai giai đoạn nối tiếp: **xác định ý định** bằng T1/T2/T3, rồi **đánh giá điều kiện ràng buộc** bằng cặp `(ý định, trạng thái xe)`. ViVi Agent đứng sau Guardrail và không tự đưa ra quyết định cho phép hay từ chối.

### 2.2. Cơ hội

Một demo end-to-end có thể biến luận điểm kiến trúc thành bằng chứng quan sát được: cùng một câu lệnh, khi thay Vehicle State, hệ thống tạo outcome khác nhau; khi block thì actuator không chạy; khi allow thì UI phản ánh action đã được thực thi. Đây là giá trị cốt lõi cần chứng minh trước giám khảo, mentor và đội kỹ thuật.

### 2.3. Tuyên bố sản phẩm

> ViGuard ViVi Agent Simulator là môi trường demo và đánh giá local trong đó text luôn đi qua Guardrail trước ViVi Agent; Guardrail phân loại đủ 53 intent, đánh giá 109 constraint theo Vehicle State và trả đúng một trong bảy outcome để Agent phản hồi hoặc thực thi.

## 3. Mục tiêu và kết quả mong đợi

### 3.1. Mục tiêu người dùng

- Người demo có thể nhập câu lệnh tự nhiên và hiểu ngay hệ thống đã xử lý qua những bước nào.
- Người demo có thể thay đổi state để thấy cùng intent bị allow hoặc block khác nhau.
- Khi bị block, người dùng nhận thông báo tiếng Việt dễ hiểu, không chỉ là mã lỗi.
- Khi được allow, người dùng thấy action mock thay đổi trạng thái hoặc xuất hiện trong execution log.
- Người dùng có thể khám phá và chạy thử đủ 53 intent mà không cần nhớ câu lệnh mẫu.

### 3.2. Mục tiêu kỹ thuật/sản phẩm

| ID | Mục tiêu | Cách xác minh |
|---|---|---|
| G-01 | UI và test bao phủ đủ 53 intent | Coverage report 53/53 |
| G-02 | Guardrail nạp và đánh giá đủ 109 rule | Loader report 109/109, checksum |
| G-03 | Block path không gọi actuator | Automated negative tests, 0 violation |
| G-04 | Quyết định dùng state snapshot, không dùng state trong utterance | Adversarial E2E tests |
| G-05 | Mọi outcome có hành vi và thông báo xác định | Outcome routing tests 100% |
| G-06 | Kết quả có thể truy vết | Mỗi request có intent, state, rule, outcome, action trace |
| G-07 | Demo phản hồi đủ nhanh | Fast path và Constraint Evaluation latency đạt §15 |
| G-08 | Phần lớn câu rõ ràng tránh T3 SLM | Đo tier distribution; không đánh đổi accuracy lấy coverage |

### 3.3. Nguyên tắc sản phẩm

1. **Fail safe:** không chắc chắn thì không thực thi.
2. **State quyết định action:** text chỉ xác định intent, không xác định an toàn.
3. **Data-driven:** policy nằm trong workbook, không hardcode vào application logic.
4. **Observable by design:** mọi bước quan trọng đều hiện trong trace.
5. **Coverage đầy đủ:** đơn giản hóa mô phỏng, không cắt intent/rule.
6. **Không phóng đại:** mô phỏng không được trình bày như tích hợp xe thật.

### 3.4. Ranh giới sản phẩm và luồng chuẩn

```text
Text Input UI
      ↓
GUARDRAIL — đứng ngoài và trước ViVi Agent
      ├─ T1: Regex / deterministic template matching
      ├─ T2: Lightweight intent classifier
      └─ T3: SLM fallback
                    ↓
                  Intent
                    ↓
       Vehicle State + Constraint Evaluation
                    ↓
    ALLOW | BLOCK_UNSAFE | BLOCK_UNAVAILABLE |
    CONFIRM | NOT_VOICE_ACTIONABLE | ANSWER | UNKNOWN
                    ↓
VIVI AGENT
      ├─ phản hồi/block/confirm/answer
      └─ chỉ `ALLOW` mới gọi Mock Actuator
```

T1/T2/T3 không tự quyết định an toàn chỉ bằng text. Chúng tạo intent. Guardrail tổng thể chỉ tạo outcome sau khi đánh giá intent cùng Vehicle State và constraints.

## 4. Người sử dụng và người kiểm tra sản phẩm

Sản phẩm có ba nhóm liên quan khác nhau: người trực tiếp dùng giao diện, người quản lý giá trị nghiệp vụ và người kiểm tra hệ thống. Việc tách ba nhóm này giúp tránh thiết kế một màn hình chỉ thuận tiện cho kỹ sư nhưng không trả lời được câu hỏi của người ra quyết định hoặc bộ phận tuân thủ.

### 4.1. Người dùng cuối

Người dùng cuối trong pilot là người đóng vai tài xế và nhập câu lệnh cho ViVi bằng văn bản. Họ muốn câu lệnh được hiểu đúng, nhận phản hồi nhanh và biết vì sao một thao tác bị từ chối. Họ không cần hiểu chi tiết mô hình hay cú pháp rule; thông báo chính phải ngắn, rõ và bằng tiếng Việt. Ví dụ, khi xe đang chạy mà người dùng yêu cầu mở cửa, hệ thống phải nói rằng thao tác không thể thực hiện vì điều kiện an toàn hiện tại, thay vì chỉ hiện `BLOCK_UNSAFE`.

### 4.2. Người dùng nghiệp vụ

Nhóm này gồm chủ sản phẩm, người quản lý danh mục ý định và người quản lý policy. Họ cần kiểm tra đủ 53 ý định, biết workbook nào là nguồn dữ liệu chính thức và thấy tác động khi thay đổi trạng thái hoặc rule. Mục tiêu của họ là bảo đảm sản phẩm giải đúng bài toán và có thể cập nhật chính sách mà không sửa mã nguồn. Với nhóm này, báo cáo bao phủ 53/53 ý định và 109/109 rule quan trọng hơn chi tiết của từng hàm phần mềm.

### 4.3. Nhóm kiểm tra nội bộ

Nhóm kiểm tra nội bộ gồm trưởng nhóm, quản lý kỹ thuật, quản lý sản phẩm và người phụ trách chất lượng. Họ cần một kịch bản demo có thể lặp lại, tiêu chí nghiệm thu rõ ràng và nhật ký đủ để xác định lỗi nằm ở phân loại, đánh giá constraint hay thực thi mô phỏng. Họ cũng cần số liệu độ trễ theo từng tầng để biết kiến trúc ba tầng thực sự giảm số lần gọi SLM hay chỉ tồn tại trên tài liệu.

### 4.4. Nhóm thanh tra, tuân thủ, pháp lý và an toàn

Nhóm này không trực tiếp điều khiển demo nhưng cần kiểm tra bằng chứng. Họ phải thấy trạng thái xe nào được dùng, rule nào đã khớp, kết quả nào được trả và bộ thực thi có chạy hay không. Tài liệu và giao diện phải phân biệt rõ “phần mềm thực hiện đúng workbook” với “workbook đã được chứng nhận đúng cho xe thật”. Pilot chỉ chứng minh vế thứ nhất; mọi tuyên bố về an toàn vật lý, tuân thủ pháp luật hoặc phê duyệt OEM đều nằm ngoài phạm vi.

### 4.5. Nhà phát triển AI và tích hợp Agent

Nhà phát triển cần hợp đồng dữ liệu ổn định từ văn bản đầu vào tới ý định, kết quả quyết định và hành động. Họ cần biết Guardrail chịu trách nhiệm đến đâu, ViVi Agent được phép làm gì và những trường nào phải xuất hiện trong nhật ký. Khi một rule lỗi, họ cần hệ thống từ chối nạp policy và chỉ rõ dòng lỗi thay vì tiếp tục chạy trong trạng thái thiếu dữ liệu.

## 5. Mô hình vận hành sản phẩm

### 5.1. Input

Đầu vào chính là câu lệnh tiếng Việt dạng văn bản do người dùng nhập. Pilot cố ý bỏ qua bước chuyển giọng nói thành văn bản để tập trung đánh giá Guardrail. Bên cạnh câu lệnh, Guardrail đọc một ảnh chụp trạng thái xe mô phỏng, chẳng hạn tốc độ, vị trí số, mức pin, trạng thái mưa hoặc trạng thái khóa cửa. Người vận hành demo có thể chỉnh các giá trị này trên giao diện, nhưng nội dung câu lệnh không được phép tự thay đổi chúng.

Hệ thống còn có hai đầu vào cấu hình. Thứ nhất là danh mục 53 ý định cùng các câu mẫu phục vụ ba tầng phân loại. Thứ hai là workbook `Driver_constraints.xlsx`, chứa 109 rule dùng để quyết định kết quả sau khi đã có ý định. Hai nguồn này phải được kiểm tra khi khởi động và phải khớp nhau về tên ý định.

### 5.2. Output

Đầu ra của Guardrail là một gói quyết định gồm ý định, tầng phân loại đã sử dụng, kết quả quyết định, rule đã khớp, phiên bản trạng thái xe, lý do và độ trễ. Kết quả quyết định chỉ được thuộc bảy giá trị có trong workbook: `ALLOW`, `BLOCK_UNSAFE`, `BLOCK_UNAVAILABLE`, `CONFIRM`, `NOT_VOICE_ACTIONABLE`, `ANSWER` hoặc `UNKNOWN`.

ViVi Agent nhận gói quyết định này và tạo đầu ra hướng người dùng. Đó có thể là lời xác nhận hành động đã thực hiện, lời giải thích vì sao bị từ chối, câu hỏi xin xác nhận hoặc câu trả lời về trạng thái xe. Nếu kết quả là `ALLOW`, hệ thống còn tạo một sự kiện thực thi mô phỏng và có thể cập nhật trạng thái xe trên giao diện. Mọi lượt xử lý đều tạo nhật ký kỹ thuật để phục vụ kiểm tra.

### 5.3. Hệ thống cần làm gì

Hệ thống phải thực hiện trọn vẹn bốn trách nhiệm. Trước hết, nó phải hiểu câu lệnh bằng đường xử lý có chi phí thấp nhất có thể: T1 dùng regex hoặc mẫu tất định, T2 dùng bộ phân loại nhẹ và T3 chỉ gọi SLM khi hai tầng trước không đủ chắc chắn. Tiếp theo, nó phải dùng ý định cùng trạng thái xe để đánh giá đúng nhóm constraint liên quan. Sau đó, ViVi Agent phải chuyển kết quả thành phản hồi hoặc hành động mà không tự sửa quyết định. Cuối cùng, hệ thống phải lưu đủ bằng chứng để một người kiểm tra có thể tái dựng toàn bộ lượt xử lý.

Một yêu cầu quan trọng là tối ưu độ trễ mà không đánh đổi độ chính xác. T1 và T2 giúp tránh gọi SLM cho câu rõ ràng; bước đánh giá constraint được giữ nhanh bằng cách nạp workbook một lần, biên dịch điều kiện thành cây cú pháp và lập chỉ mục rule theo ý định. Hệ thống không được tăng tỷ lệ xử lý ở tầng nhanh bằng cách nới ngưỡng đến mức phân loại sai.

### 5.4. Business Flow

Quy trình bắt đầu khi người dùng gửi câu lệnh. Guardrail chuẩn hóa văn bản và thử T1. Nếu T1 không tìm được một kết quả duy nhất, yêu cầu chuyển sang T2; nếu T2 không đạt ngưỡng tin cậy và khoảng cách điểm, yêu cầu mới chuyển sang T3. Khi một tầng trả được ý định, các tầng sau không chạy.

Guardrail sau đó chụp state tại đúng thời điểm đánh giá, lấy các rule `gate` của intent và tìm outcome phù hợp. Decision package được chuyển cho ViVi Agent. Với `ALLOW`, Agent gọi Mock Actuator. Với các outcome chặn, Agent chỉ trả lời và tuyệt đối không thực thi. Với `CONFIRM`, Agent hỏi lại người dùng; khi nhận xác nhận, request phải quay lại Guardrail để đọc state mới trước khi được thực thi. Với `ANSWER` hoặc `UNKNOWN`, Agent trả lời từ dữ liệu mô phỏng mà không gọi Mock Actuator.

Nếu hành động có rule `monitor`, Guardrail tiếp tục đánh giá khi trạng thái thay đổi hoặc khi có nhịp kiểm tra. Khi điều kiện không còn phù hợp, ViVi Agent dừng hành động mô phỏng và ghi lại lý do. Như vậy, Guardrail không chỉ kiểm tra trước hành động mà còn có thể mô phỏng việc theo dõi trong khi hành động đang diễn ra.

### 5.5. Business Objects và quan hệ

| Đối tượng | Ý nghĩa | Quan hệ chính |
|---|---|---|
| Câu lệnh | Văn bản người dùng gửi vào hệ thống | Một câu lệnh tạo một lượt xử lý Guardrail |
| Ý định | Loại yêu cầu chuẩn hóa trong danh mục 53 nhãn | Một ý định có nhiều câu mẫu và nhiều rule |
| Tầng phân loại | Cách tìm ý định: T1, T2 hoặc T3 | Mỗi lượt thành công được giải quyết bởi đúng một tầng |
| Ảnh chụp trạng thái xe | Giá trị trạng thái bất biến tại thời điểm quyết định | Được dùng để đánh giá nhiều điều kiện của một ý định |
| Rule | Một điều kiện gắn với ý định, chế độ kiểm tra và kết quả | Nhiều rule thuộc một ý định; một rule thuộc `gate` hoặc `monitor` |
| Kết quả Guardrail | Quyết định cuối cùng sau phân loại và đánh giá constraint | Được ViVi Agent dùng để chọn phản hồi hoặc hành động |
| Yêu cầu xác nhận | Trạng thái chờ sinh ra từ `CONFIRM` | Thuộc một lượt xử lý và chỉ được dùng một lần |
| Hành động mô phỏng | Sự kiện hoặc thay đổi trạng thái do Agent thực hiện | Chỉ được tạo từ `ALLOW` hoặc xác nhận hợp lệ |
| Phiên theo dõi | Trạng thái theo dõi hành động kéo dài | Tham chiếu hành động, state mới nhất và rule `monitor` |
| Nhật ký truy vết | Chuỗi sự kiện của một lượt xử lý | Liên kết câu lệnh, ý định, state, rule, kết quả và hành động |

Danh mục ý định quản lý các loại yêu cầu mà hệ thống hiểu. Rule quản lý cách một loại yêu cầu được xử lý trong từng trạng thái xe. Kết quả Guardrail không tồn tại độc lập: nó luôn phải truy được ngược về một câu lệnh, một ý định, một ảnh chụp trạng thái và một rule. Quan hệ này là nền tảng cho kiểm tra và giải trình.

### 5.6. UI Definition

Giao diện gồm khu vực hội thoại, ô nhập văn bản, bảng trạng thái xe, danh mục 53 ý định, bảng quyết định, bảng thực thi và dòng thời gian truy vết. Người dùng cuối chủ yếu nhìn khu vực hội thoại; người demo và nhóm kiểm tra có thể mở các bảng chi tiết để xem tầng phân loại, điểm tin cậy, rule và độ trễ. Nhãn **MÔ PHỎNG** phải luôn xuất hiện trên màn hình.

Khi bị từ chối, giao diện ưu tiên câu giải thích tiếng Việt và nêu trạng thái liên quan; mã kỹ thuật nằm trong phần chi tiết. Khi được cho phép, giao diện phải cho thấy hành động đã xảy ra bằng thay đổi trạng thái hoặc sự kiện rõ ràng. Khi cần xác nhận, hộp xác nhận phải tồn tại cho tới khi người dùng chọn, không được biến mất như một thông báo tạm thời.

### 5.7. Technical Proposal ở mức sản phẩm

Giải pháp được đề xuất là một modular monolith chạy local. Guardrail Gateway đứng trước ViVi Agent và chứa ba tầng phân loại cùng Constraint Engine. ViVi Agent đứng sau, chỉ nhận decision package và gọi đúng response handler hoặc action handler. Workbook được nạp một lần khi startup; rule được index theo `(intent, check_mode)`; state nằm trong memory; tất cả condition được parse bằng closed AST evaluator thay vì `eval()`.

Kiến trúc này được chọn vì vừa giữ độ trễ thấp, vừa tạo ranh giới rõ giữa quyết định và thực thi. Tài liệu `specs/architecture/Architecture_Guardrail_FINAL.md` mô tả chi tiết các thành phần, giao diện lập trình, mô hình dữ liệu, xử lý lỗi, bảo mật, triển khai và kiểm thử.

### 5.8. Thuật ngữ

| Thuật ngữ | Định nghĩa trong dự án |
|---|---|
| ViVi Agent mô phỏng | Thành phần nhận kết quả Guardrail và tạo phản hồi hoặc hành động mô phỏng |
| Guardrail | Lớp đứng trước Agent, xác định ý định và quyết định kết quả theo trạng thái xe |
| Ý định | Nhãn chuẩn hóa đại diện cho yêu cầu của người dùng |
| Trạng thái xe mô phỏng | Tập giá trị do người demo chỉnh, dùng làm nguồn sự thật cho constraint |
| Rule `gate` | Rule đánh giá trước khi Agent phản hồi hoặc thực thi |
| Rule `monitor` | Rule đánh giá lại khi hành động mô phỏng đang diễn ra |
| Bộ đánh giá constraint | Mô-đun nội bộ của Guardrail đánh giá `(ý định, trạng thái)` |
| Bộ thực thi mô phỏng | Thành phần mô phỏng hành động, không điều khiển phần cứng |
| Kết quả quyết định | Một trong bảy kết quả policy của Guardrail |
| Nhật ký đầu-cuối | Chuỗi sự kiện từ văn bản đầu vào tới phản hồi, hành động và theo dõi |

## 6. Phạm vi

### 6.1. Phạm vi bắt buộc

- Web UI mô phỏng ViVi với ô nhập text.
- Guardrail end-to-end gồm kiểm tra text, phân loại đủ 53 intent và đánh giá constraint theo state.
- Intent Explorer giúp chạy thử từng intent.
- Vehicle State Mock với state editor và preset.
- Policy loader/parser/evaluator cho đủ 109 rule.
- Outcome routing cho đủ 7 policy outcome.
- Mock Actuator cho mọi action/UI intent.
- Query responder cho state/knowledge intent.
- Confirmation flow có re-evaluation.
- Monitor simulation cho 5 monitor rule.
- Trace end-to-end, policy status và coverage report.
- Test/benchmark đủ để chứng minh acceptance criteria.

### 6.2. Ngoài phạm vi

| Hạng mục | Lý do |
|---|---|
| Microphone, ASR, speech-to-text | Input đã được chốt là text; ASR là bài toán riêng |
| CAN bus, ECU, actuator xe thật | Không có hardware/vehicle integration trong pilot |
| Chứng nhận policy đúng với xe thật | Cần OEM safety owner và evidence ngoài phạm vi software demo |
| Trợ lý hội thoại mở ngoài 53 intent | Làm loãng mục tiêu đánh giá guardrail/policy |
| RAG production | `explain_feature` chỉ dùng knowledge map mô phỏng |
| Production PEP/capability token | Pilot chỉ chứng minh flow, chưa chứng minh enforcement chống bypass cấp production |
| Authentication/multi-user/tenant | Demo local, không phải dịch vụ production |
| Lưu lịch sử dài hạn | Trace chỉ phục vụ session demo và test |

## 7. Dữ liệu và source of truth

### 7.1. Workbook policy

`Driver_constraints.xlsx`, sheet `Constraints`, là source of truth cho decision policy.

| Thuộc tính | Giá trị đã xác minh |
|---|---:|
| Cột | 5 |
| Intent | 53 |
| Rule | 109 (`R001`–`R109`) |
| Gate rule | 104 |
| Monitor rule | 5 |
| Outcome | 7 |

Schema workbook:

| Cột | Ý nghĩa |
|---|---|
| `rule_id` | ID duy nhất của rule |
| `intent` | Intent được rule áp dụng |
| `condition` | Biểu thức điều kiện trên state |
| `check_mode` | `gate` hoặc `monitor` |
| `outcome` | Kết quả khi condition match |

### 7.2. Danh mục 53 intent

| Nhóm | Intent |
|---|---|
| Cửa/khoang chứa | `open_door`, `open_trunk`, `open_chargeport`, `lock_doors`, `unlock_doors`, `OPEN_BONNET` |
| Chiếu sáng/gạt mưa | `turnoff_highbeam`, `turnon_highbeam`, `turnoff_lowbeam`, `turnon_lowbeam`, `AD_WIPER_MAX`, `activate_ahb`, `turnon_corneringlight`, `turnon_interiorlight` |
| Chế độ lái/an toàn | `switch_drivemode_sport`, `switch_drivemode_eco`, `switch_drivemode_normal`, `activate_creepmode`, `turnoff_LKA`, `activate_aac`, `activate_hda`, `activate_tcs`, `deactivate_esc`, `activate_avh` |
| Chế độ xe/đỗ xe | `activate_campmode`, `activate_petmode`, `activate_valetmode`, `activate_autopark`, `activate_epb`, `shift_gear_park`, `SHIFT_GEAR_REVERSE` |
| Ghế/vô lăng/gương/cửa sổ | `ad_steeringwheel`, `fold_backseat`, `open_sunroof`, `ad_driverseat_angle`, `ad_driverseat_pos`, `open_window`, `restore_driverseat_pos`, `fold_mirrors` |
| Tín hiệu/UI | `deactivate_hud`, `turnon_turnsignal_right`, `turnon_turnsignal_left`, `turnoff_turnsignal_right`, `turnoff_turnsignal_left`, `turnon_hazardlight`, `turnoff_hazardlight`, `open_noti_center` |
| Hỏi trạng thái | `get_current_speed`, `get_battery_pct`, `get_gear`, `get_door_lock_status`, `get_avh_status` |
| Hỏi kiến thức | `explain_feature` |

Tên intent giữ nguyên đúng workbook, kể cả khác biệt chữ hoa/thường.

### 7.3. Hệ thống kết quả quyết định

| Outcome | Cấp | Ý nghĩa | Có gọi actuator? |
|---|---|---|---|
| `ALLOW` | Policy | Được thực hiện | Có |
| `BLOCK_UNSAFE` | Policy | Không an toàn trong state hiện tại | Không |
| `BLOCK_UNAVAILABLE` | Policy | Tính năng chưa khả dụng | Không |
| `CONFIRM` | Policy | Cần người dùng xác nhận | Chưa; chỉ sau confirm hợp lệ |
| `NOT_VOICE_ACTIONABLE` | Policy | Không cho thực hiện qua lệnh ViVi | Không |
| `ANSWER` | Policy | Trả lời bằng dữ liệu/knowledge mock | Không |
| `UNKNOWN` | Policy | Thiếu dữ liệu để trả lời | Không |

Guardrail chỉ công bố bảy outcome trong bảng trên. Trường hợp text không ánh xạ được vào catalog là lỗi phân loại để ViVi yêu cầu người dùng diễn đạt lại; đây không phải một outcome mới và không được đi tiếp tới đánh giá constraint hoặc actuator.

## 8. Trải nghiệm người dùng

### 8.1. Bố cục màn hình

1. **Header:** tên sản phẩm, nhãn SIMULATION, policy health.
2. **Chat panel:** lịch sử lệnh và phản hồi ViVi.
3. **Text composer:** ô nhập text, gửi bằng nút hoặc Enter.
4. **Vehicle State panel:** state hiện tại, preset và editor.
5. **Intent Explorer:** tìm kiếm/lọc đủ 53 intent, xem và chèn câu mẫu.
6. **Decision panel:** intent, rule, outcome, message và relevant state.
7. **Execution panel:** actuator events và active actions.
8. **Trace timeline:** từng bước, latency và status.

### 8.2. Luồng chuẩn: allow

1. Người dùng nhập “mở cửa xe”.
2. Guardrail phân loại `open_door` và chụp Vehicle State Mock.
3. Guardrail match gate rule `ALLOW`.
5. Mock Actuator mô phỏng mở cửa.
6. ViVi phản hồi thành công; UI state và trace cập nhật.

### 8.3. Luồng block

1. Người dùng nhập lệnh action.
2. Guardrail phân loại intent, đọc state và match `BLOCK_UNSAFE`, `BLOCK_UNAVAILABLE` hoặc `NOT_VOICE_ACTIONABLE`.
4. ViVi giải thích bằng tiếng Việt và hiển thị state liên quan.
5. Không có actuator event.

### 8.4. Luồng confirmation

1. Policy trả `CONFIRM`.
2. ViVi hỏi xác nhận; action chưa chạy.
3. Người dùng confirm hoặc cancel.
4. Nếu confirm, hệ thống đọc state mới và đánh giá lại policy.
5. Chỉ thực thi một lần nếu confirmation vẫn hợp lệ; nếu state xấu đi thì block.

### 8.5. Luồng query

Intent `ANSWER` được trả bằng state snapshot hoặc knowledge map mô phỏng. Nếu policy trả `UNKNOWN`, ViVi nói rõ chưa lấy được dữ liệu. Query không gọi Mock Actuator.

### 8.6. Luồng monitor

Action có monitor rule tạo active action. Khi state thay đổi hoặc monitor tick, hệ thống đánh giá monitor rule. Nếu outcome block, action mock dừng và ViVi/trace thông báo lý do.

## 9. User Stories

### Người demo

- Là người demo, tôi muốn nhập text tự nhiên để thấy ViVi xử lý như một agent hoàn chỉnh.
- Là người demo, tôi muốn chọn bất kỳ intent nào trong 53 intent để không phụ thuộc trí nhớ câu mẫu.
- Là người demo, tôi muốn đổi state và chạy lại cùng câu lệnh để chứng minh decision phụ thuộc state.
- Là người demo, tôi muốn thấy action mock thay đổi trên UI khi được allow.

### Reviewer

- Là reviewer, tôi muốn biết Guardrail đã phân loại intent, đọc state và match constraint nào để audit kết quả.
- Là reviewer, tôi muốn block path chứng minh actuator không được gọi.
- Là reviewer, tôi muốn thấy policy checksum và rule ID để kết quả có thể tái lập.
- Là reviewer, tôi muốn nhìn thấy nhãn simulation để không nhầm với xe thật.

### Người quản lý policy và nhà phát triển

- Là policy owner, tôi muốn loader từ chối toàn bộ workbook khi có rule lỗi để tránh chạy policy một phần.
- Là developer, tôi muốn mỗi intent hành động có mock handler rõ ràng để phát hiện coverage gap.
- Là developer, tôi muốn cùng input/state/policy tạo cùng output để test ổn định.

## 10. P0 Functional Requirements

Các yêu cầu trong phần này là điều kiện tối thiểu để pilot có ý nghĩa. Chúng mô tả hành vi có thể quan sát được thay vì khóa đội triển khai vào một thư viện cụ thể. Nếu bỏ một yêu cầu thuộc phần này, demo sẽ không còn chứng minh trọn vẹn luồng Guardrail đứng trước ViVi Agent.

### FR-01 — Text command entry

Người dùng tương tác bằng văn bản để loại bỏ biến số nhận dạng giọng nói. Ô nhập cũng là ranh giới đầu vào của Guardrail: mọi lệnh phải đi qua cùng một điểm vào, nhờ đó không tồn tại đường tắt từ giao diện tới ViVi Agent.

- UI phải có ô nhập text, nút gửi và trạng thái loading.
- Text rỗng/only-whitespace không được gửi.
- Một lần gửi tạo đúng một request ID.
- Không có microphone hoặc ASR dependency.
- Command endpoint thuộc Guardrail Gateway; UI không chuyển raw text trực tiếp cho ViVi Agent.

### FR-02 — Kiểm tra text trong Guardrail

Trước khi phân loại, Guardrail chuẩn hóa và kiểm tra văn bản để loại đầu vào rỗng, sai định dạng hoặc có dấu hiệu cố thao túng luồng xử lý. Đây là kiểm soát nội bộ, không tạo thêm kết quả quyết định ngoài bảy giá trị trong workbook. Nếu văn bản không thể xử lý an toàn, hệ thống trả lỗi có kiểu rõ ràng và dừng trước mọi hành động.

- Kiểm tra text là một bước nội bộ của Guardrail, không phải một lớp sản phẩm hay outcome độc lập.
- Text không hợp lệ hoặc có dấu hiệu tấn công không được gọi actuator.
- Phản hồi ra ngoài phải dùng contract chung của Guardrail; không tự tạo thêm outcome ngoài workbook.

### FR-03 — Phân loại ý định

Ba tầng chỉ giải quyết câu hỏi “người dùng muốn gì?”, không tự quyết định hành động có an toàn hay không. Sau khi tìm được ý định, Guardrail mới dùng trạng thái xe và điều kiện ràng buộc để tạo kết quả cuối. Cách tách này là bắt buộc vì cùng câu “mở cửa xe” có thể được cho phép khi xe đỗ và bị chặn khi xe đang chạy.

- Bước phân loại nội bộ trả đúng một trong 53 intent hoặc trạng thái lỗi phân loại.
- Output gồm tier, confidence/match evidence và latency.
- Classifier không đọc Vehicle State.
- Kết quả phân loại chỉ là dữ liệu trung gian; output cuối của Guardrail là một trong bảy outcome của workbook.
- **T1 — Regex/template matching:** chuẩn hóa text và khớp mẫu tất định; câu khớp duy nhất được trả intent ngay, không gọi model.
- **T2 — Lightweight intent classifier:** xử lý paraphrase không khớp T1; chỉ trả intent khi confidence đạt threshold và margin so với nhãn thứ hai đạt yêu cầu.
- **T3 — SLM fallback:** chỉ xử lý câu T1/T2 không giải quyết chắc chắn; SLM bị giới hạn chọn đúng một trong 53 intent, không được tạo action, outcome hoặc tool call.
- Mỗi request dùng đúng tầng đầu tiên tạo kết quả hợp lệ; tầng sau không chạy nếu tầng trước đã resolve.
- T1/T2/T3 đều chỉ tạo intent; Constraint Evaluation sau đó mới tạo outcome.
- Không tìm được intent đủ tin cậy tạo lỗi phân loại và yêu cầu người dùng diễn đạt lại; đây không phải outcome thứ tám.

### FR-03A — Guardrail đứng trước ViVi Agent

Guardrail là lớp nằm ngoài ViVi Agent và là cổng bắt buộc của mọi câu lệnh. ViVi Agent không nhận văn bản thô để tự diễn giải hoặc tự thay đổi quyết định. Nó chỉ nhận kết quả Guardrail đã hoàn chỉnh rồi chuyển kết quả đó thành lời đáp, yêu cầu xác nhận hoặc hành động mô phỏng.

- UI/API gửi text vào Guardrail Gateway, không gửi trực tiếp vào ViVi Agent.
- Guardrail trả `intent`, `outcome`, `rule_id`, `reason`, `state_version`, `tier` và latency metadata.
- ViVi Agent không được tự gọi classifier hoặc Constraint Engine.
- ViVi Agent không được đổi outcome do Guardrail trả về.
- ViVi Agent chỉ được gọi Mock Actuator khi outcome là `ALLOW` hoặc sau confirmation hợp lệ đã được Guardrail đánh giá lại.

### FR-04 — Danh mục khám phá ý định

Danh mục này giúp người demo kiểm thử đủ 53 ý định mà không phải nhớ câu mẫu. Nó không phải đường thực thi thay thế: khi chọn một ý định, giao diện chỉ điền câu mẫu vào ô văn bản; câu đó vẫn phải đi qua toàn bộ Guardrail như câu người dùng tự gõ.

- Hiển thị đúng 53 intent từ catalog runtime.
- Cho phép search, filter theo nhóm và chèn câu mẫu vào composer.
- Hiển thị trạng thái coverage của classifier, policy và handler.
- Thiếu intent bất kỳ là launch blocker.

### FR-05 — Trạng thái xe mô phỏng

Trạng thái xe mô phỏng là nguồn sự thật duy nhất cho bước đánh giá điều kiện. Câu lệnh có thể chứa chuỗi như “speed bằng 0”, nhưng Guardrail phải bỏ qua khẳng định đó và đọc giá trị từ kho trạng thái. Mỗi lần đánh giá dùng một ảnh chụp bất biến để rule và nhật ký cùng tham chiếu đúng một phiên bản dữ liệu.

- Hiển thị/chỉnh được mọi field mà condition đang tham chiếu.
- Có validation type và enum tại input.
- Có preset parked-safe, driving, rainy, low-battery, unavailable/missing-data.
- Mỗi mutation tăng `state_version`.
- Mỗi decision dùng một immutable snapshot.
- Utterance không được thay đổi state tự động.

### FR-06 — Nạp và kiểm tra policy

Workbook được coi là dữ liệu cấu hình, không phải mã thực thi. Khi khởi động, hệ thống đọc toàn bộ sheet `Constraints`, kiểm tra cấu trúc, số lượng, tên ý định, loại kiểm tra, kết quả và cú pháp điều kiện. Chỉ khi toàn bộ 109 rule hợp lệ thì tập policy mới được công bố cho Guardrail sử dụng.

- Đọc đúng sheet `Constraints` của `Driver_constraints.xlsx`.
- Validate schema, 109 unique rule IDs, 53 intents, modes, outcomes và condition.
- Load toàn bộ hoặc fail closed; không bỏ qua row lỗi.
- Hiển thị policy health, rule/intent count và checksum.

### FR-07 — Đánh giá điều kiện ràng buộc

Bước này nhận đúng hai dữ liệu nghiệp vụ: ý định đã phân loại và ảnh chụp trạng thái xe. Nó không đọc lại câu người dùng. Để giữ độ trễ thấp, workbook và các biểu thức được chuẩn bị một lần khi khởi động, sau đó rule được lập chỉ mục theo ý định; một yêu cầu `open_door` chỉ đánh giá nhóm rule của `open_door`, không quét toàn bộ 109 dòng.

- Gate evaluation chỉ nhận intent và state snapshot.
- Condition parser hỗ trợ toàn bộ cú pháp workbook hiện tại.
- Không dùng `eval()`.
- Mỗi request phải trả đúng một decision xác định.
- Không match hoặc multi-match ngoài thiết kế phải fail closed và không gọi actuator.
- Workbook được đọc, normalize, parse và compile một lần khi startup; không đọc Excel theo request.
- Rule được index theo `(intent, check_mode)`; mỗi request chỉ evaluate rules của intent tương ứng, không quét cả 109 rule.

### FR-08 — Định tuyến kết quả quyết định

Sau khi Guardrail trả outcome, ViVi Agent chuyển outcome đó tới đúng handler. Outcome Router là nơi duy nhất có quyền gọi Mock Actuator. Quy tắc này biến yêu cầu “bị chặn thì không hành động” thành một thuộc tính kiến trúc, thay vì phụ thuộc vào việc từng màn hình nhớ kiểm tra.

- `ALLOW` route tới Mock Actuator.
- Các block route tới response, không actuator.
- `CONFIRM` route tới Confirmation Manager.
- `ANSWER`/`UNKNOWN` route tới Query Responder.
- Router ghi event trước và sau mỗi side effect.

### FR-09 — Thông báo khi bị từ chối

Thông báo phải giúp người dùng hiểu chuyện gì xảy ra mà không làm lộ chi tiết triển khai không cần thiết. Phần chat dùng câu tiếng Việt tự nhiên; bảng chi tiết hiển thị ý định, rule, kết quả và trạng thái liên quan để phục vụ demo và kiểm tra. Hệ thống không được tự bịa gợi ý nếu workbook không cung cấp đủ căn cứ.

Mỗi block response có:

- câu tiếng Việt dễ hiểu;
- loại block;
- intent nếu đã classify;
- `rule_id` nếu policy đã chạy;
- relevant state trong detail panel;
- gợi ý an toàn nếu có thể xác định mà không bịa policy.

Message mặc định:

| Outcome | Message |
|---|---|
| `BLOCK_UNSAFE` | “Không thể thực hiện vì điều kiện an toàn hiện tại chưa phù hợp.” |
| `BLOCK_UNAVAILABLE` | “Tính năng hiện chưa khả dụng trong trạng thái xe hiện tại.” |
| `NOT_VOICE_ACTIONABLE` | “Thao tác này không thể thực hiện bằng lệnh ViVi.” |

Nếu không phân loại được intent, ViVi dùng câu “ViVi chưa hiểu yêu cầu này, bạn vui lòng diễn đạt lại.” như một error response, không gắn outcome policy.

### FR-10 — Xác nhận trước khi thực thi

`CONFIRM` có nghĩa là chưa được phép thực thi. Khi người dùng xác nhận, trạng thái xe có thể đã thay đổi, vì vậy Guardrail phải đánh giá lại trên ảnh chụp mới. Chỉ khi kết quả mới vẫn cho phép thì ViVi Agent mới được thực thi một lần; xác nhận cũ, hết hạn hoặc dùng lại đều bị từ chối.

- `CONFIRM` tạo pending confirmation có expiry và single-use ID.
- Chưa confirm không được gọi actuator.
- Confirm phải re-read state và re-evaluate gate policy.
- Cancel, timeout hoặc confirmation đã dùng đều không thực thi.
- Nếu re-evaluation trả block, response phải dùng block mới.
- Nếu vẫn match cùng confirmation rule, confirm hiện tại cho phép thực thi một lần.

### FR-11 — Mock Actuator

Bộ thực thi làm cho kết quả `ALLOW` trở nên hữu hình: cửa có thể đổi sang trạng thái mở, đèn có thể bật hoặc một sự kiện hành động được ghi nhận. Tuy nhiên, mọi thay đổi chỉ tồn tại trong môi trường demo. Bộ xử lý không được gọi hệ điều hành, mạng, xe thật hoặc thiết bị bên ngoài.

- Có handler cho mọi action/UI intent trong catalog.
- Handler chỉ cập nhật state mock, active action hoặc event log.
- Không có external side effect.
- UI không được gọi handler trực tiếp.
- Handler thiếu phải trả lỗi fail closed, không giả thành công.

### FR-12 — Trả lời câu hỏi

Các ý định hỏi trạng thái và hỏi kiến thức không phải hành động. Với `ANSWER`, ViVi Agent tạo câu trả lời từ ảnh chụp trạng thái hoặc kho kiến thức mô phỏng. Với `UNKNOWN`, hệ thống nói rõ chưa có dữ liệu; nó không được dùng kiến thức chung của mô hình để lấp chỗ trống.

- State query trả dữ liệu từ snapshot, không dùng text để suy đoán.
- `explain_feature` dùng knowledge map được đánh dấu mock.
- `UNKNOWN` trả message thiếu dữ liệu và không gọi actuator.

### FR-13 — Theo dõi hành động mô phỏng

Năm rule `monitor` mô tả điều kiện cần tiếp tục kiểm tra sau khi hành động bắt đầu. Trong demo, việc theo dõi có thể chạy theo thay đổi trạng thái, bộ đếm thời gian hoặc nút kiểm tra thủ công. Nếu Guardrail trả kết quả chặn, ViVi Agent phải dừng hành động; nếu đánh giá gặp lỗi, hành động cũng dừng theo nguyên tắc an toàn.

- Chỉ action có monitor rule mới tạo monitor session.
- Monitor chạy khi state mutation, timer demo hoặc manual tick.
- Monitor block dừng active action.
- Monitor failure cũng dừng action theo fail-safe.
- UI hiển thị active action, last tick, rule và outcome.

### FR-14 — Trace

Nhật ký là bằng chứng của demo. Nó phải kể lại toàn bộ câu chuyện của một yêu cầu: văn bản vào, tầng nào giải quyết ý định, trạng thái nào được đọc, rule nào khớp, kết quả nào được trả và bộ thực thi có chạy hay không. Nhật ký phục vụ tái lập và kiểm tra, không phải kho lưu trữ sản xuất lâu dài.

Mỗi request lưu tối thiểu:

- request/session ID và timestamp;
- input text;
- các bước nội bộ của Guardrail và classification result;
- state version và snapshot;
- policy checksum, matched rule và outcome;
- confirmation lifecycle;
- actuator/query/monitor events;
- latency từng stage và end-to-end.

## 11. P1 Requirements

Những khả năng dưới đây giúp demo dễ sử dụng và thuyết phục hơn nhưng không thay đổi luận điểm cốt lõi. Chúng chỉ được triển khai sau khi toàn bộ yêu cầu bắt buộc đã đạt tiêu chí nghiệm thu.

- Scenario library chạy một chạm cho allow/block/confirm/query/monitor.
- Dashboard coverage và latency histogram.
- Export trace JSON.
- So sánh hai lần chạy cùng utterance với state khác nhau.
- Vietnamese response catalog chi tiết theo từng rule.
- Keyboard navigation và responsive layout cho màn hình demo.

## 12. P2 — Future Considerations

Các hạng mục sau được ghi lại để thiết kế hiện tại không vô tình chặn đường nâng cấp. Chúng không thuộc cam kết của pilot và không được trình bày như chức năng đã có.

- ASR và voice input.
- Vehicle state adapter cho CAN/ECU.
- Production actuator adapter.
- PEP/capability grants và authorization token chống replay.
- Monitor loop real-time.
- RAG thật cho knowledge query.
- Authentication, multi-user và persistent audit store.
- Đa ngôn ngữ và model fine-tuning.

## 13. Business Rules và Invariants

Các điều bất biến phải đúng trong mọi màn hình, mọi ý định và mọi đường xử lý. Chúng được tách khỏi yêu cầu giao diện để đội kiểm thử có thể chuyển trực tiếp thành kiểm tra tự động.

| ID | Quy tắc |
|---|---|
| BR-01 | Guardrail chỉ trả một trong bảy outcome của workbook |
| BR-02 | Lỗi phân loại không được đánh giá constraint hoặc gọi actuator |
| BR-03 | Bước đánh giá constraint không được đọc utterance |
| BR-04 | Mọi block/unknown không gọi actuator |
| BR-05 | `CONFIRM` không phải `ALLOW` và chưa được thực thi |
| BR-06 | Confirm phải đánh giá lại state |
| BR-07 | Một confirmation chỉ thực thi tối đa một lần |
| BR-08 | Query intent không gọi actuator |
| BR-09 | Policy invalid làm toàn hệ thống fail closed |
| BR-10 | Text khai báo state không thay thế Vehicle State Mock |
| BR-11 | UI/test coverage phải đủ 53 intent và 109 rule |
| BR-12 | Tất cả action đều là simulation |

## 14. Acceptance Criteria

Tiêu chí nghiệm thu mô tả bằng chứng cần quan sát ở ranh giới sản phẩm. Một kiểm thử chỉ được coi là đạt khi vừa có phản hồi đúng cho người dùng, vừa có nhật ký chứng minh các thành phần không được phép đã không chạy.

### 14.1. Mức độ bao phủ

1. Given application khởi động với workbook canonical, when loader hoàn tất, then policy status hiển thị 53 intents, 109 rules, 104 gate và 5 monitor.
2. Given Intent Explorer, when đếm item, then có đúng 53 intent và không có intent ngoài workbook.
3. Given automated coverage suite, when chạy, then mỗi intent có ít nhất một E2E scenario.
4. Given rule coverage suite, when chạy, then từng `R001`–`R109` có test evidence hoặc validation evidence phù hợp mode.

### 14.2. Guardrail và phân loại intent

5. Given text không hợp lệ hoặc test case tấn công, when gửi, then Guardrail không gọi actuator và không tạo outcome ngoài bảy giá trị đã định nghĩa.
6. Given utterance hợp lệ có câu mẫu, when gửi, then trả đúng intent.
7. Given utterance không đủ tin cậy, when gửi, then ViVi yêu cầu diễn đạt lại, không gắn policy outcome và không gọi actuator.
8. Given utterance chứa “speed=0” nhưng state khác 0, when xử lý, then decision dùng Vehicle State Mock.

### 14.3. Quyết định policy và hành động

9. Given `open_door` và state `(gear=P, speed<3)`, when gửi lệnh, then `ALLOW`, Mock Actuator chạy đúng một lần.
10. Given `open_door` và xe đang chạy, when gửi, then `BLOCK_UNSAFE`, actuator không chạy.
11. Given `deactivate_esc`, when gửi, then `NOT_VOICE_ACTIONABLE`, actuator không chạy.
12. Given policy row không parse được, when khởi động, then status `POLICY_INVALID` và command execution bị khóa.
13. Given nhiều rule gate cùng match trái thiết kế, when evaluate, then fail closed và nêu policy ambiguity.

### 14.4. Xác nhận, câu hỏi và theo dõi

14. Given `CONFIRM`, when chưa confirm, then không có actuator event.
15. Given state trở nên không an toàn trước confirm, when confirm, then hệ thống block theo state mới.
16. Given pending confirmation bị confirm hai lần, then lần thứ hai bị từ chối.
17. Given state query có dữ liệu, then trả `ANSWER` từ snapshot.
18. Given query thiếu dữ liệu, then trả `UNKNOWN`, không actuator.
19. Given monitored action đang active, when monitor rule trả block, then action dừng và trace ghi monitor rule.

### 14.5. Trải nghiệm và khả năng quan sát

20. Given bất kỳ result nào, then chat hiển thị message tiếng Việt và decision panel hiển thị mã kỹ thuật.
21. Given block result, then relevant state và rule có thể xem được mà không mở developer console.
22. Given allow result, then execution panel thể hiện action và state/event thay đổi.
23. Given mọi màn hình demo, then nhãn SIMULATION luôn hiển thị.

## 15. Success Metrics và cách đo

Pilot được đánh giá bằng mức độ bao phủ, tính nhất quán, an toàn của đường thực thi và độ trễ. Các ngưỡng dưới đây là điều kiện phát hành, không phải kết quả đã đo. Báo cáo cuối phải ghi rõ cấu hình máy, số mẫu, thời gian làm nóng và các phân vị thay vì chỉ công bố số trung bình.

| Metric | Ngưỡng ship | Cách đo |
|---|---:|---|
| Intent coverage | 53/53 | Automated E2E report |
| Policy load coverage | 109/109 | Loader validation report |
| Gate/monitor count | 104/5 | Loader validation report |
| Outcome routing consistency | 100% | Unit/integration tests |
| Block path actuator violations | 0 | Spy/assertion trong tests |
| Confirmation compliance | 100% | Confirmation state-machine tests |
| Determinism | 100% cùng input/state/policy | Repeat-run suite |
| Fast Guardrail latency | ≤25 ms p99 | Benchmark local target |
| Policy evaluation latency | ≤5 ms p99 | Benchmark sau warm load |
| T1 latency | ≤5 ms p99 | Benchmark sau warm-up |
| T2 latency | ≤20 ms p99 | Benchmark classifier warm-loaded |
| T3 SLM latency | Đo và báo cáo riêng | Không trộn vào fast-path metric |
| Tier distribution | Đo T1/T2/T3 riêng | Chứng minh tỷ lệ request tránh SLM |
| SLM call avoidance | Tối đa hóa có điều kiện | Không được giảm intent accuracy để tăng tỷ lệ tránh SLM |
| Demo task completion | 100% scenario bắt buộc | Rehearsal checklist |

Không có metric “physical safety accuracy”. Pilot đo implementation có tuân theo workbook, không đo policy có đúng với xe thật.

## 16. Analytics và Logging

### 16.1. Các sự kiện tối thiểu

- `command_received`
- `guardrail_started` / `intent_classified` / `classification_failed`
- `constraint_evaluated` / `guardrail_completed` / `guardrail_error`
- `confirmation_requested` / `confirmed` / `cancelled` / `expired`
- `actuator_executed` / `actuator_failed`
- `query_answered` / `query_unknown`
- `monitor_started` / `monitor_tick` / `monitor_stopped`
- `command_completed`

Mỗi event có `session_id`, `request_id`, timestamp, stage và policy checksum. Không log secret hoặc system prompt.

## 17. Dependencies và Assumptions

### 17.1. Phụ thuộc

- Workbook `Driver_constraints.xlsx` phải có mặt khi ứng dụng khởi động.
- Intent catalog/câu mẫu phải ánh xạ đủ 53 intent.
- Vehicle State schema phải bao phủ identifiers trong condition.
- Danh bạ hàm phải cung cấp các hàm nằm trong danh sách cho phép, chẳng hạn `kb_has_feature`.

### 17.2. Giả định

- Demo chạy cục bộ cho một người dùng tại một thời điểm.
- Trạng thái được chỉnh tay và không thay đổi với tần suất như xe thật.
- Bộ thực thi mô phỏng không tạo tác động bên ngoài ứng dụng.
- T3 SLM có thể là thành phần tùy chọn; demo phải có đường xử lý tất định khi không có mạng.
- Nội dung policy là input được chấp nhận cho pilot nhưng chưa được xác nhận là policy sản xuất.

## 18. Rủi ro và biện pháp giảm thiểu

Bảng dưới đây tập trung vào những trường hợp có thể khiến demo đưa ra bằng chứng sai: phạm vi không đủ, policy bị đọc thiếu, hành động chạy trên đường chặn hoặc người xem hiểu nhầm mô phỏng là hệ thống thật. Mỗi biện pháp phải gắn với một kiểm tra hoặc tín hiệu quan sát được.

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| UI có 53 intent nhưng classifier hoặc handler thiếu coverage | Cao | Runtime coverage report và launch gate |
| Cú pháp điều kiện không đồng nhất | Cao | Bộ phân tích cú pháp đóng, chuẩn hóa và kiểm tra khi nạp |
| Bị chặn nhưng bộ thực thi vẫn chạy | Cao | Ranh giới định tuyến duy nhất, kiểm thử trường hợp âm và kiểm tra nhật ký |
| Xác nhận bị bỏ qua hoặc dùng lại | Cao | Trạng thái chờ, thời hạn, dùng một lần và đánh giá lại |
| Theo dõi lỗi nhưng hành động tiếp tục | Cao | Dừng hành động theo nguyên tắc an toàn |
| Người xem hiểu nhầm tích hợp thật | Cao | Nhãn MÔ PHỎNG cố định và tuyên bố phạm vi rõ ràng |
| Giả định policy bị trình bày như sự thật | Cao | Ghi giới hạn bằng chứng trong báo cáo và demo |
| T3 SLM phụ thuộc mạng làm demo hỏng | Trung bình | Ưu tiên SLM cục bộ hoặc đường dự phòng tất định không cần mạng |

## 19. Kế hoạch triển khai và điều kiện chuyển giai đoạn

### Giai đoạn 1 — Nền tảng policy

- Bộ nạp policy, bộ phân tích/đánh giá điều kiện và lược đồ trạng thái.
- Kiểm tra đủ 109 rule.
- Kiểm thử rule `gate` và `monitor`.

**Điều kiện chuyển giai đoạn:** nạp và phân tích được 109/109 rule; policy không hợp lệ phải khóa thực thi.

### Giai đoạn 2 — Luồng xử lý Guardrail

- Guardrail Gateway; T1 regex/template, T2 lightweight classifier, T3 SLM; Constraint Engine và trace.
- Danh mục được bao phủ đủ 53 ý định.

**Điều kiện chuyển giai đoạn:** 53/53 ý định có kịch bản phân loại; mọi đường bị chặn có số lần gọi bộ thực thi bằng 0.

### Giai đoạn 3 — Hành vi mô phỏng của ViVi Agent

- Bộ thực thi mô phỏng, bộ trả lời câu hỏi, xác nhận và theo dõi.

**Điều kiện chuyển giai đoạn:** đủ bảy kết quả policy; kiểm thử máy trạng thái xác nhận và theo dõi đều đạt.

### Giai đoạn 4 — Giao diện và mức sẵn sàng demo

- Hội thoại, bảng trạng thái, danh mục ý định, bảng quyết định, thực thi và truy vết.
- Bộ trạng thái mẫu, đo hiệu năng và diễn tập demo.

**Điều kiện chuyển giai đoạn:** toàn bộ tiêu chí nghiệm thu bắt buộc đạt trên máy demo mục tiêu.

## 20. Definition of Done

Sản phẩm chỉ được coi là hoàn thành khi:

- PRD và đặc tả kiến trúc đồng bộ;
- giao diện chạy được bằng đầu vào văn bản;
- báo cáo tự động chứng minh bao phủ 53/53 ý định và 109/109 rule;
- mọi kết quả có hướng xử lý và trải nghiệm đúng;
- `BLOCK_*` và `UNKNOWN` không gọi bộ thực thi;
- xác nhận luôn đánh giá lại, có thời hạn và chỉ dùng một lần;
- năm rule `monitor` đều có kịch bản;
- nhật ký hiển thị đầy đủ luồng đầu-cuối;
- độ trễ được đo trên máy mục tiêu;
- README và kịch bản demo phản ánh đúng phạm vi mô phỏng;
- không có tuyên bố về xe thật hoặc xác nhận an toàn của OEM.
