# Unity Bridge v1：模块设计与实现约束

本文是实现、代码审查和验收的设计契约。基于该契约的 demo 已加入本目录，接入方法和实际验证边界见 [README.md](README.md)。后续用户要求 Python 顶层只保留一个 `.py` 入口，实际接口与目录采用下文的单入口形式。

## 1. 目标与范围

Unity Bridge 将 Robot Framework 关键字转换为 Unity 内部元素操作：

```text
Robot Framework
    ↓ 关键字
Python：UnityBridgeLibrary → UnityBridgeClient → RpcClient
    ↓ TCP / UTF-8 / 每行一条 JSON
127.0.0.1:<host_port>
    ↓ adb forward
Android：127.0.0.1:<server_port>
    ↓
C#：TcpServer → RpcDispatcher → 主线程调度 → UGUI 适配器
```

已确认首版主要面向 **UGUI 元素，例如 Button、Toggle**。必须支持：

- 读取元素状态，以及等待元素满足指定状态。
- 监测 `visible`、`not visible`、`enabled`、`disabled` 四种状态条件。
- 等待元素可以点击，再执行一次点击。
- 有限的连接、请求、状态等待和 ADB 操作超时。
- Python 自动管理 ADB 转发，向 Robot Framework 隐藏 TCP、JSON 和请求 ID。

v1 默认支持单个设备上的一个 Unity 实例、一个连接、一个进行中的请求。不同设备可以使用不同 Python 库实例和本地端口并行测试。单个实例不支持并发关键字调用。

v1 不包含 2D/3D Collider 对象、UI Toolkit、输入文本、拖拽、多点触控、长按和逐像素可见性分析。后续通过适配器扩展，不改动 Robot Framework 与 RPC 的基本边界。

## 2. 两端的职责与模块

### 2.1 C# / Unity

| 模块 | 职责 | 必须满足的约束 |
| --- | --- | --- |
| `UnityBridgeHost` | 配置、启动、停止服务，管理连接与跨场景生命周期 | 实例唯一；切换场景不重复监听；停止时关闭连接并取消待执行任务 |
| `TcpServer` | 接收 TCP、组装消息、限制消息长度、串行发送响应 | 网络线程不访问 Unity 对象；有界缓冲；连接断开后释放会话资源 |
| `RpcDispatcher` | 校验版本、方法、参数、请求 ID，转换为类型明确的命令 | 仅允许明确列出的 RPC；禁止执行任意 C#、反射调用业务方法或解析任意脚本 |
| `MainThreadScheduler` | 将命令交给 Unity 主线程执行，推进等待任务 | 不阻塞主线程等待网络或条件；每帧检查任务、连接取消与截止时间 |
| `ElementRegistry` | 测试 ID 到元素的映射、场景变化与销毁处理 | 包含已注册的 inactive 元素；重复 ID 报错；不长期持有失效对象 |
| `BridgeElement` | 为元素声明稳定 ID，并绑定 UGUI 适配器 | ID 不依赖显示文案、层级路径或实例 ID |
| `UguiElementAdapter` | 计算状态、寻找点击位置、执行指针事件 | 所有 Unity API 操作在主线程；按本文状态与点击契约执行 |
| `PendingOperation` | 保存等待条件、最后快照、截止时间、点击执行阶段 | 取消或超时后不能继续发起点击；不同请求不共享可变状态 |

建议采用普通 C# 数据对象保存网络请求和响应，使用 `ConcurrentQueue` 或等价的线程安全机制跨线程传递。主线程负责读取元素状态，序列化和发送可以使用已经复制好的普通数据。

网络异步任务即使由主线程启动，也不得让阻塞式 `Accept`、`Read`、`Write` 占用 Unity 主线程。不要依赖 `async` 关键字自动解决线程与阻塞问题。

服务端最多保留一个待执行或等待中的操作。一个客户端在上一请求完成前发来新请求时，返回 `REQUEST_IN_PROGRESS`，不建立无界等待队列。第二个客户端应在有界握手阶段收到 `SERVER_BUSY` 后断开，不得接管活动会话。

### 2.2 Python

| 模块 | 职责 | 必须满足的约束 |
| --- | --- | --- |
| `AdbForwardManager` | 选择设备、创建和清理端口转发 | 始终使用明确的 serial；仅清理本实例创建且仍匹配的映射 |
| `TcpTransport` | 建连、发送完整帧、保留接收缓冲、按行读帧 | 支持拆包与粘包；按绝对截止时间计算剩余等待时间 |
| `RpcClient` | 请求 ID、协议验证、响应匹配、错误映射 | 单请求串行；连接出错后作废会话；不自动重发点击 |
| `UnityBridgeClient` | 提供 `connect/get_state/wait_for_state/click/close` | 不依赖 Robot Framework，便于普通 Python 脚本使用 |
| `UnityBridgeLibrary` | 注册关键字、转换时间参数、整理日志与失败信息 | 关键字中不暴露 JSON、socket、ADB 命令和请求 ID |

依赖方向必须为：`Robot 适配层 → 业务客户端 → RPC/ADB → 传输`。底层不反向调用 Robot Framework 日志或断言接口。

首版 Python 使用标准库 `socket`、`subprocess`、`json`、`time` 即可，Robot 适配层另外依赖 `robotframework`。Robot 时间字符串应使用 Robot Framework 的时间解析工具，转换后的内部单位统一为毫秒。

## 3. 元素标识与注册

每个可测试元素通过 `BridgeElement` 声明一个 ID，例如 `login.submit`、`settings.sound_toggle`。

- v1 只支持精确 ID 定位：`{"id":"login.submit"}`，不做模糊搜索或路径回退。
- ID 是区分大小写的非空字符串，最长 128 个字符，不得包含控制字符。
- ID 必须在当前已加载场景与跨场景常驻对象中唯一；包含 inactive 元素。
- 重复 ID 返回 `AMBIGUOUS_ELEMENT`，不得任选其中一个继续操作。
- 注册不能只依赖 `OnEnable`；禁用对象仍须可被查询为不可见或不可用。
- 场景初次加载应从所有根节点扫描，包括 inactive 子节点；`OnDisable` 不注销，销毁和场景卸载才移除。
- 动态实例化的元素必须显式接入注册流程，尤其是初始 inactive、尚未触发 `Awake` 的对象；不能假定 `Awake` 总会及时注册。
- 每次状态采样重新校验引用。等待期间允许旧对象销毁、同 ID 新对象出现；点击执行期间则绑定具体实例，不能把一次点击的按下和抬起分别发送给两个实例。
- 高频采样必须通过注册表定位，不得每隔 100 ms 全场景扫描或反复使用 `GameObject.Find`。

首版内置适配器至少覆盖 `Button`、`Toggle`。其他 UGUI 组件只有在提供明确的 enabled 与点击语义后才可接入。已注册但适配器不支持的元素返回 `UNSUPPORTED_ELEMENT`。

## 4. 状态契约

### 4.1 四个条件对应两个独立维度

四种状态是等待条件，不是四选一的枚举。例如，元素可以同时 `visible` 和 `disabled`，也可以 `not visible` 但 `enabled`。

状态快照示例：

```json
{"id":"login.submit","exists":true,"visible":true,"enabled":false}
```

| 等待条件 | 精确定义 |
| --- | --- |
| `visible` | `exists == true` 且 `visible == true` |
| `not visible` | `exists == false` 或 `visible == false` |
| `enabled` | `exists == true` 且 `enabled == true` |
| `disabled` | `exists == true` 且 `enabled == false` |

元素不存在时返回：

```json
{"id":"login.submit","exists":false,"visible":false,"enabled":null}
```

因此，等待元素消失可以使用 `not visible`；等待 `disabled` 不会因为元素不存在而成功。`null` 不能转成 `false` 后参与 disabled 判断。

### 4.2 visible：UGUI 的几何可见性

v1 的 `visible` 表示元素具备在当前 UI 画面显示的条件。必须同时满足：

1. 对象 `activeInHierarchy == true`。
2. 相关 Canvas 处于有效启用状态，使用受支持的显示目标。
3. 至少一个指定的展示 Graphic 有效启用，具有非零面积，且有效透明度大于阈值，默认 `0.01`。
4. 该 Graphic 的投影区域与目标显示区域有交集，且未被 Unity 已计算出的整体剔除状态排除。

展示 Graphic 可显式配置；默认收集当前元素的 Graphic 和子级 Graphic，但排除属于其他嵌套 `BridgeElement` 的子树。不能仅因为 Button 的背景透明，就忽略仍然可见的文字。

CanvasGroup 的有效透明度与继承规则必须按项目使用的 Unity/UGUI 版本处理，并以集成场景验证，不能简单假定所有父级属性都无条件累乘。状态采样使用当前帧有效的布局和 Canvas 数据；不在每个等待任务中重复强制刷新整个 Canvas。

v1 支持显示器 0 上的 `Screen Space - Overlay` 与 `Screen Space - Camera`。后者要求有效相机且不输出到 RenderTexture。不支持的 Canvas 配置返回 `UNSUPPORTED_CANVAS`，不能伪装成普通不可见。

这个定义不保证元素没有被其他 UI 遮挡，也不保证通过截图能找到可见像素；纹理内部透明像素、部分裁剪以及复杂 stencil 遮罩不做逐像素判断。点击时另行执行射线检测。

### 4.3 enabled：交互开关

对于 Button、Toggle，`enabled` 表示：

- 对应 `Selectable` 组件自身 `enabled == true`。
- `Selectable.interactable == true`。
- 按 UGUI 的有效继承规则，相关 CanvasGroup 允许交互。

此定义不包含对象是否显示、是否在屏幕内、是否被遮挡。inactive 元素仍可能 `enabled == true`。不要直接使用 `isActiveAndEnabled` 作为该字段，也不能对 inactive 对象不加校验地依赖可能未更新的交互缓存。

`CanvasGroup.blocksRaycasts`、`Graphic.raycastTarget` 参与实际点击命中判断，不单独决定 `enabled`。

## 5. 元素监测与点击

### 5.1 读取与等待

- `element.get`：在一次主线程采样中返回快照，不等待元素出现。不存在是正常结果。
- `element.wait`：重复采样，直到指定条件满足或预算耗尽。条件第一次满足即返回，不要求连续稳定多帧。
- 监测采用主线程定时采样，默认间隔 `100 ms`，每个操作每帧最多采样一次；它不是服务端持续推送的订阅功能。
- 使用不受 `Time.timeScale` 影响的单调时钟；`timeScale=0` 不应使超时失效。
- 等待逻辑不能使用阻塞循环或 `Thread.Sleep` 占用主线程。
- 每次采样前检查取消和截止时间；预算已到时不再通过一次迟到采样宣布成功。

### 5.2 点击

`element.click` 内部等待以下条件同时成立：

1. 元素存在、可见且 enabled。
2. 当前存在有效的 EventSystem，目标具备受支持的 UGUI 点击处理能力。
3. 目标点击点经过 `EventSystem.RaycastAll` 的实际排序后，最前方有效命中的点击处理对象是目标元素。

默认点击点是目标 RectTransform 的几何中心。协议可选 `point=[x,y]`，表示该 RectTransform 内从左下到右上的归一化坐标，两个值都必须在 `[0,1]` 内。Screen Space Camera 使用实际事件相机转换坐标。

命中目标的子级 Graphic 可以接受，但必须解析到同一个预期点击处理对象；不能因为命中了某个后代，就误点嵌套的另一个 Button。

前置条件满足后，主线程重新校验目标实例与截止时间，并在一次操作中派发匹配 UGUI 点击语义的 `pointerDown → pointerUp → pointerClick`。处理对象的解析、按下对象记录、点击资格和回调间的重新校验必须参考所用 UGUI 版本的输入模块规则，不能简单向任意 GameObject 无条件广播三个事件。

- Button、Toggle 使用各自事件处理逻辑，不直接调用 `Button.onClick.Invoke()`，也不直接修改 `Toggle.isOn`。
- 如果按下事件使对象销毁、禁用或失去点击资格，停止剩余点击流程，返回 `CLICK_INTERRUPTED` 和已经执行的阶段；不得换一个同 ID 实例继续。
- 按下后若仍可安全发送抬起或清理事件，应完成必要清理，但不得对失效对象发事件。
- v1 的按下和抬起发生在同一帧，不模拟按住时长，也不保证 hover、真实鼠标位置、Input System 设备状态或 `Input.GetMouseButton` 发生变化。
- 中心点被遮挡时继续等待，到期返回最后的阻挡原因；不自动寻找其他可点位置。可由调用者指定其他归一化位置。
- 回包成功仅代表点击事件派发完成。跳转、网络请求、动画等业务结果必须再用状态等待或其他断言验证。

点击副作用必须最多发起一次。条件轮询只检测，不重复点击。一次公开的 Click 关键字最多发送一次 `element.click` RPC。

## 6. 文本 RPC 协议

### 6.1 编码与消息边界

- 使用 TCP 长连接、UTF-8 无 BOM，每条完整 JSON 对象以 LF 字节结束；允许接收 CRLF。
- JSON 字符串中的换行使用 JSON 转义，不能作为消息分隔符。不得使用多行美化 JSON。
- v1 单条消息最大 `64 KiB`，包含 JSON UTF-8 字节但不包含末尾 CR/LF。接收缓冲在未读到换行时同样受此限制。
- 不能假定一次 `send` 对应一次 `recv`；必须保留未完成帧和下一帧的剩余字节。
- 服务端在收到一帧的首字节后，最多允许 `5 s` 等待该帧完整到达；超时关闭连接，不为每段数据重新计时。正常已握手连接在没有新帧开始时可以保持空闲。
- 每条有效请求恰好一个最终响应；v1 无进度通知、无批量请求、无服务端事件推送。
- v1 是自定义 RPC 协议，不宣称兼容 JSON-RPC 2.0。

### 6.2 请求与响应结构

请求示例，实际发送时末尾附加一个 LF：

```json
{"v":1,"id":2,"method":"element.wait","params":{"selector":{"id":"login.submit"},"state":"visible"},"timeout_ms":10000}
```

成功响应：

```json
{"v":1,"id":2,"ok":true,"result":{"snapshot":{"id":"login.submit","exists":true,"visible":true,"enabled":true},"matched_state":"visible","elapsed_ms":137}}
```

失败响应：

```json
{"v":1,"id":2,"ok":false,"error":{"code":"ELEMENT_WAIT_TIMEOUT","message":"Element did not become visible within 10000 ms","data":{"selector":{"id":"login.submit"},"expected_state":"visible","last_snapshot":{"id":"login.submit","exists":false,"visible":false,"enabled":null},"elapsed_ms":10003}}}
```

协议字段约束：

- `v` 必须为整数 `1`。
- `id` 是 `1..2147483647` 的整数，每条 TCP 连接内严格递增；握手也占用 ID。
- 服务端保存本连接已接受的最大 ID。重复或倒序 ID 返回 `DUPLICATE_REQUEST_ID`，不得再次执行原操作；这不是跨连接的 exactly-once 保证。
- `method` 必须在方法表内；`params` 必须是对象。未知方法和未知参数立即报错，避免拼写错误被默默忽略。
- `timeout_ms` 是 `1..120000` 的整数。Python 提供默认值；0 不合法，立即读取状态使用 `element.get`。
- 响应的 `result` 与 `error` 只能出现一个；`id` 必须匹配当前请求。
- `elapsed_ms` 从完整请求被服务端接收开始，使用单调时钟统计。
- 无法提取合法 ID 的坏帧，在日志中记录原因并关闭连接；合法请求的参数错误则返回结构化失败响应。

这里的“一次最终响应”以连接仍可用为前提；连接中断后不承诺响应送达。可恢复关联但包含参数错误的请求同样消耗它的 ID，客户端不能修改参数后复用该 ID。

### 6.3 方法表

| 方法 | 参数 | 成功结果 | 等待行为 |
| --- | --- | --- | --- |
| `bridge.hello` | `{}` | 协议版本、会话 ID、Unity 版本、支持的方法与状态 | 不做元素等待 |
| `element.get` | `selector` | `snapshot`、`elapsed_ms` | 一次采样 |
| `element.wait` | `selector`、`state` | `snapshot`、`matched_state`、`elapsed_ms` | 等待状态成立 |
| `element.click` | `selector`、可选 `point` | `dispatched=true`、`snapshot_before`、`elapsed_ms` | 等待可点击后派发一次 |

连接建立后必须先 `bridge.hello`，成功验证 `v=1` 以及所需能力后才进入已连接状态。握手返回的状态名称必须包含本文约定的四种字符串。

握手成功结果字段固定为：

```json
{"protocol_version":1,"session_id":"server-generated-session-id","unity_version":"实际 Unity 版本","methods":["bridge.hello","element.get","element.wait","element.click"],"states":["visible","not visible","enabled","disabled"],"click_delivery":"ugui_pointer_events","max_timeout_ms":120000}
```

`session_id` 在每条已接受的连接中唯一，用于日志关联，不承担跨连接请求去重。hello 在正常成功响应的 `result` 中返回以上对象。

`state` 仅接受四个规范字符串。Robot 层可以去除首尾空白并统一小写；发送到服务端的值必须规范化。

### 6.4 错误与副作用信息

最低错误集合：

| 错误码 | 含义 |
| --- | --- |
| `INVALID_REQUEST` / `INVALID_PARAMS` | 消息或参数不符合契约 |
| `UNSUPPORTED_VERSION` / `METHOD_NOT_FOUND` | 协议版本或方法不支持 |
| `HANDSHAKE_REQUIRED` / `SERVER_BUSY` | 尚未握手或服务端已有活动客户端 |
| `REQUEST_IN_PROGRESS` | 当前连接已经有进行中的操作 |
| `DUPLICATE_REQUEST_ID` | 请求 ID 重复或倒序 |
| `AMBIGUOUS_ELEMENT` | ID 对应多个元素 |
| `UNSUPPORTED_ELEMENT` / `UNSUPPORTED_CANVAS` | 当前适配器不支持 |
| `DEADLINE_EXCEEDED` | 任务在执行或等待开始前已超过服务端预算 |
| `ELEMENT_WAIT_TIMEOUT` | 元素状态在期限内未满足 |
| `ELEMENT_CLICK_TIMEOUT` | 可点击条件在期限内未满足 |
| `CLICK_INTERRUPTED` | 派发期间对象或交互资格发生变化 |
| `INTERNAL_ERROR` | 未预期的服务端异常 |

点击失败的 `error.data` 必须包含 `effect`：`not_started`、`started` 或 `completed`，根据已发生的阶段填写；不能把已经执行过 pointerDown 的失败说成完全未执行。条件超时必须返回 `not_started`。

状态等待与点击等待失败都应返回期望条件、最后快照和耗时。点击还应提供最近原因，例如 `not_found`、`not_visible`、`disabled`、`blocked`、`no_event_system`；尚未完成任何采样时，最后快照允许为 `null`。

Python 另外定义本地错误，例如 `AdbError`、`DeviceSelectionError`、`BridgeConnectError`、`BridgeProtocolError`、`BridgeTransportError`、`BridgeWaitTimeout`、`BridgeClickOutcomeUnknown`。最后一种用于点击请求可能已执行但无法获得可靠响应，不能伪装为元素等待超时。

## 7. 超时与取消

| 超时 | 默认值 | 负责方与范围 |
| --- | --- | --- |
| 连接超时 | `10 s` | Python；覆盖设备检查、创建转发、TCP 连接、握手，使用同一个总截止时间 |
| 单次 ADB 命令超时 | 最多 `3 s` | Python；实际不得超过连接过程的剩余预算 |
| 服务端初次握手/单帧组装超时 | 各 `5 s` | C# 网络层；防止未完成连接长期占用服务 |
| 服务端响应写回超时 | `2 s` | C# 网络层；超时断开，不阻塞主线程 |
| 普通读取/握手 RPC 预算 | `5 s` | Unity；包含主线程排队 |
| 状态等待/点击准备预算 | `5 s`，可覆盖 | Unity；包含主线程排队和条件采样 |
| 传输余量 | `2 s` | Python；用于发送、调度与回包，不重复执行操作 |
| 清理超时 | `3 s` | Python；独立、有界，不能因清理永久卡住 teardown |

约束：

1. Unity 的服务端截止时间从完整请求被接收时计算；Python 使用每次 RPC 开始时的绝对截止时间，默认最多等待操作预算加传输余量。两端不比较墙上时钟。
2. 拆分收到多个字节块时，不能为每次 `recv` 重置完整超时，否则对端缓慢发送就会无限延长等待。
3. 状态等待应由服务端一次 `element.wait` 完成，不由 Python 连续调用 get 并各自消耗一个完整超时。
4. 点击派发开始前必须检查截止时间。到期未开始则失败，后续帧不得补执行。
5. Unity 主线程中的同步业务回调无法被安全抢占。点击开始后回调超时，不承诺回滚，也不能把已经发生的点击报告为“未执行”。如果可靠回包未到达客户端，只能报告结果未知。
6. 连接断开时取消本连接尚未开始的点击及等待任务；已经执行的回调不回滚。取消被主线程观察前可能存在竞态，因此客户端仍不能依据断线推断点击没有发生。
7. Python 请求超时、读到 EOF、响应 ID 不匹配或协议损坏后，关闭连接并作废会话，防止迟到响应被误用于下一条请求。
8. 点击不自动重试或自动重连后重发。调用者重新连接后应先检查业务状态，再决定是否发起新的点击。
9. 连接建立阶段可以在总预算内重试无副作用的 TCP 连接或握手；重连期间不得替调用者重放元素操作。

Demo 的连接等待以合法 hello 成功为就绪条件；TCP 建连错误、握手 EOF / reset / 传输超时在剩余总预算内重试。单次 TCP + hello 尝试最多 1 秒，失败后最多间隔 0.1 秒；协议不兼容和明确 RPC 错误立即报告。ADB 转发只创建一次，重试期间仅更换 socket。Python 连接结果额外返回 `connect_elapsed_ms`（含 ADB 准备的客户端总耗时）与 `connect_attempts`，不修改线上 hello 对象。这不代表界面或业务就绪，后者应继续使用元素状态断言。

当游戏主线程停顿时，服务端可能无法及时返回超时响应；Python 仍需按本地截止时间退出，不得无限等待。

## 8. ADB 转发与连接生命周期

### 8.1 设备和转发

- 用户给出 serial 时固定使用该设备；未给出时，只有一个已授权且状态为 `device` 的设备才能自动选择。多个设备不猜测。
- 后续所有命令都使用 `adb -s <serial>`。
- 使用 `subprocess` 参数列表执行，`shell=False`，检查返回码并保留 stdout/stderr 作为错误上下文。
- 默认由 ADB 分配本地空闲端口，避免先找空闲端口再绑定造成竞争：

```text
adb -s SERIAL forward tcp:0 tcp:13000
```

解析该命令返回的本地端口后，连接 `127.0.0.1:<host_port>`。如果 ADB 不支持所需能力，返回明确错误，不随机尝试覆盖已有映射。

用户指定本地端口时使用：

```text
adb -s SERIAL forward --no-rebind tcp:23000 tcp:13000
```

端口已被占用则失败。v1 不自动接管已有转发，也不调用 `adb forward --remove-all`。

### 8.2 生命周期

```text
未连接
  → 校验参数、选择设备
  → 创建并记录本实例拥有的 forward
  → TCP 连接 + hello
  → 可执行关键字
  → 关闭 socket
  → 核对并删除本实例 forward
  → 未连接
```

- Unity 应用由测试前置步骤启动，例如现有 Appium 关键字；Connect 不隐式安装或启动 APK。
- 创建转发后，允许在连接总预算内等待 Unity 服务就绪。
- 任一步失败都要关闭已创建的 socket，并尝试在独立清理预算内撤销本次创建的转发。
- 记录 serial、本地端口、远端端口和所有权。删除前核对当前映射仍然匹配；无法核实或已被替换时不删除，并报告清理情况。
- 删除形式为 `adb -s SERIAL forward --remove tcp:<host_port>`。
- Close 必须幂等，重复执行不能删除其他会话的资源。
- socket 已断开不影响继续清理 forward。单独 Close 失败应抛出清理异常；如果已有主异常，保留主异常并附加清理详情。
- 已有可用连接时再次 Connect 报明确的 already-connected 错误，要求先 Close，防止隐式丢失原会话。

Unity 服务默认只监听 loopback，测试组件通过 Editor、Development Build 或明确的测试编译开关启用，避免随着普通发布构建意外启用。

## 9. Python API 与 Robot Framework 关键字

Python API 草案：

```python
client.connect(serial=None, server_port=13000, host_port=None, timeout=10.0)
client.get_state(element_id, timeout=5.0)
client.wait_for_state(element_id, state, timeout=5.0)
client.click(element_id, timeout=5.0, point=None)
client.close()
```

Python API 中超时单位为秒，接受有限正数，拒绝布尔值、NaN 和无穷大，并明确检查服务端的最大预算。RPC 编码时转换为整数毫秒，不得把秒直接当毫秒。

Robot 库采用 suite scope，关闭自动关键字暴露，只显式注册以下关键字：

| 关键字 | 参数 | 返回值 |
| --- | --- | --- |
| `Connect To Unity` | `serial=None, server_port=13000, host_port=auto, timeout=10s` | 连接信息，可供日志使用 |
| `Close Unity Connection` | 无 | 无；幂等清理 |
| `Get Unity Element State` | `element_id, timeout=5s` | 状态快照字典 |
| `Wait For Unity Element State` | `element_id, state, timeout=5s` | 条件满足时的快照字典 |
| `Click Unity Element` | `element_id, timeout=5s, point=None` | 派发结果，包含 `dispatched` 和 `snapshot_before` |

构造参数可以覆盖默认操作超时。关键字失败时必须带上元素 ID、期望状态或点击条件、实际耗时、服务端错误码和最后状态；不能只报告通用的 socket 错误。

参数错误使用明确的参数异常；期望状态超时或明确的点击条件失败在 Robot 中表现为可读的测试断言失败；通信异常保留其类型与上下文。基础 RPC 层不要用一个无差别异常吞掉所有细节。

示例采用 demo 的单文件公开入口；实际导入路径应相对于 `.robot` 文件设置：

```robot
*** Settings ***
Library           ../python/UnityBridge.py
Suite Setup       Connect To Unity    serial=${DEVICE_SERIAL}    server_port=13000
Suite Teardown    Close Unity Connection

*** Variables ***
${DEVICE_SERIAL}    emulator-5554

*** Test Cases ***
进入主界面
    Wait For Unity Element State    login.submit    visible    timeout=10s
    Wait For Unity Element State    login.submit    enabled    timeout=10s
    Click Unity Element            login.submit    timeout=5s
    Wait For Unity Element State    loading.spinner    not visible    timeout=20s
    Wait For Unity Element State    home.start    visible    timeout=10s

验证禁用按钮
    Wait For Unity Element State    shop.purchase    disabled    timeout=5s
    ${state}=    Get Unity Element State    shop.purchase
    Should Be Equal    ${state}[enabled]    ${False}
```

Click 自己执行完整准备条件检查，上面的 visible/enabled 等待用于展示接口，并非每次点击前都必须单独调用。连续关键字默认各自拥有预算；若测试需要整个业务流程的总时限，应另外在用例层设置。

## 10. 建议目录

```text
bridge/
  DESIGN.md
  README.md
  unity/com.robotframework.unitybridge/
    package.json
    Runtime/           # TCP、协议、Host、元素注册与 UGUI 适配
    Editor/            # SDK Host、元素标识的接入菜单
    Samples~/Demo/     # 可生成的演示场景
    Tests/Runtime/     # 待 Unity 环境执行的 PlayMode 测试
  python/
    pyproject.toml
    UnityBridge.py     # 唯一公开 .py 入口
    _unity_bridge/    # 私有实现
      adb.py
      transport.py
      rpc.py
      client.py
      errors.py
      robot_library.py
  tests/
    test_python.py
    csharp/            # 本机语法、协议、TCP 检查，不替代 Unity 编译
  examples/
    bridge_smoke.robot
```

C# demo 以 Unity 2021.3 LTS、UGUI 和官方 Newtonsoft JSON 包为基线。生产 SDK 不依赖 .NET 10；.NET 10 仅用于本机检查独立于 Unity 的协议与 TCP 源码。Unity API 绑定与目标平台构建仍需在实际工程中验证。

## 11. 验收约束

以下是后续程序必须通过的验收场景，不代表当前已经执行测试。

| 类别 | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| 协议 | 一条 JSON 被拆为多个 TCP 包，多条 JSON 一次到达 | 正确组帧，每条只执行一次 |
| 协议 | 超长消息、坏 JSON、未知参数、重复请求 ID | 有界失败，不崩溃，不重复点击 |
| 线程 | 请求从后台网络线程到达 | 所有对象访问和事件派发都发生在 Unity 主线程 |
| 元素 | 重复 ID、初始 inactive 元素、动态 inactive 元素、场景卸载 | 结果符合注册契约，没有错误命中或失效引用 |
| 状态 | 可见且启用、可见且禁用、不可见但启用、不可见且禁用 | 两个维度独立，四个条件按定义匹配 |
| 状态 | 元素不存在 | get 返回 exists=false；not visible 成功；disabled 不成功 |
| 状态 | CanvasGroup、禁用 Canvas、移出屏幕、透明度变化 | 符合本文可见性与交互契约 |
| 点击 | 正常 Button、Toggle，命中子级文字 | 点击一次；Button 回调一次，Toggle 翻转一次 |
| 点击 | 遮挡层、blocksRaycasts、raycastTarget、嵌套按钮 | 不穿透遮挡，不点击错误处理对象 |
| 点击 | 中心被挡但边缘可点 | 默认中心点击等待；显式有效 point 可以成功 |
| 点击 | pointerDown 中销毁或禁用目标 | 不向新实例补发，不重复操作，报告执行阶段 |
| 超时 | 主线程排队、元素一直不存在、timeScale=0 | 有限退出；未开始的点击不在后续帧补执行 |
| 通信 | 点击成功后响应丢失，主线程长时间卡住 | Python 按本地截止时间退出，报告结果未知，不自动重发 |
| ADB | 多设备、设备未授权、端口占用、握手失败 | 清楚报错，清理本次资源，不移除其他映射 |
| 生命周期 | 断线后关闭、重复关闭、重新连接、场景切换 | 不泄漏 socket、转发或待执行任务 |
| Robot | 用例只使用业务关键字 | 不需要手写 ADB、TCP、JSON 或请求 ID；失败报告包含可定位的信息 |

实施顺序建议：先完成协议编解码与 Python 假服务端验证，再完成 Unity 主线程状态采样，随后接入点击事件，最后连通真实 Android 设备的 ADB 转发与 Robot 用例。每层独立验收后再接入下一层。
