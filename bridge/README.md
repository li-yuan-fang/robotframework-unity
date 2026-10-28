# Unity Bridge Demo

这是一个将 UGUI 元素暴露给 Python / Robot Framework 的开发版 SDK 原型。

- **Python 唯一公开入口：** `python/UnityBridge.py`。内部代码在 `_unity_bridge/`，支持直接按文件路径导入，也提供可安装的 Python 包。
- **Unity SDK：** `unity/com.robotframework.unitybridge/`，是标准 UPM 本地包，包含 Runtime、Editor 菜单、Samples 和 PlayMode 测试。
- **能力：** 状态读取、等待 `visible / not visible / enabled / disabled`、经过射线命中检查的 Button/Toggle 点击。
- **环境基线：** Unity 2021.3 LTS 或更高，UGUI，Python 3.9 或更高。Android 模式额外需要 ADB。Robot Framework 只在使用 `.robot` 用例时需要。

SDK 会编译到接入项目中，与应用一起运行；电脑端 Python 库连接 SDK。它具有“给游戏接入测试 SDK，再由外部测试程序控制”的使用形式，当前覆盖的功能是一个小范围 demo。

## 1. 先在 Unity Editor 中运行示例

1. 打开自己的 Unity 项目。
2. 选择 **Window → Package Manager**，点击 **+ → Add package from disk**。
3. 选择仓库内 `bridge/unity/com.robotframework.unitybridge/package.json`。Unity 将解析 UGUI 和官方 Newtonsoft JSON 包依赖。
4. 在这个包的详情中展开 **Samples**，导入 **UGUI Bridge Demo**。
5. 选择 **Tools → Unity Bridge → Create Demo Scene**，生成并保存示例场景。已有同名场景时使用新文件名。
6. 点击 **Play**，在 Game 视图中保持示例运行。Console 应出现：`[Unity Bridge] Listening on 127.0.0.1:13000`。

示例运行时创建 Canvas、EventSystem、SDK Host 和这些测试元素：

| ID | 初始状态 / 点击效果 |
| --- | --- |
| `demo.login` | 可见、启用；点击后隐藏并显示 `demo.home` |
| `demo.home` | 初始 inactive；登录后可见 |
| `demo.toggle` | Toggle；切换购买按钮是否允许交互 |
| `demo.purchase` | 可见、disabled；Toggle 打开后 enabled |
| `demo.once` | 点击后禁用；界面显示实际回调计数 |
| `demo.hidden` | inactive，因此 not visible；交互配置仍为 enabled |
| `demo.blocked` | 可见、enabled，但中心点被另一层 UI 挡住，点击应超时 |

UGUI 按钮由代码生成，不需要额外美术资源。示例使用项目当前输入后端；只安装新 Input System 的项目通过运行时发现其 UI 输入模块，不强制引入该包。

## 2. 从普通 Python 调用

无需安装任何第三方运行依赖，先把库所在目录加入模块搜索路径：

```python
import sys
sys.path.insert(0, r"C:\Users\mazecheng\Documents\robotframework-unity\bridge\python")

from UnityBridge import UnityBridgeClient

with UnityBridgeClient() as bridge:
    info = bridge.connect_local(server_port=13000)  # Editor / 桌面 Player，不使用 ADB
    print(info)
    print(bridge.get_state("demo.purchase"))
    bridge.wait_for_state("demo.login", "visible", timeout=5)
    bridge.click("demo.login", timeout=5)
    bridge.wait_for_state("demo.home", "visible", timeout=5)
```

所有普通 Python API 的数值超时单位都是**秒**；原始 RPC 使用毫秒。`with` 在退出时关闭连接并清理本实例拥有的转发。

后续也可通过 `python -m pip install ./bridge/python` 安装成库，再直接 `from UnityBridge import UnityBridgeClient`。仅复制 `UnityBridge.py` 不够，必须一起保留其 `_unity_bridge` 子目录；顶层公开入口始终只有一个 `.py` 文件。

## 3. 接入已有 Unity 项目

不需要使用示例场景，按以下步骤接入自己的项目：

1. 按第一节方式导入 UPM 包。
2. 在启动场景选择 **GameObject → Unity Bridge → SDK Host**，创建一个根对象。该组件跨场景保留，默认端口 `13000`，可在 Inspector 修改。
3. 选中要操作的 Button / Toggle，选择 **Tools → Unity Bridge → Add Element To Selected UI**，或者手动添加 `Bridge Element` 组件。
4. 在 Inspector 的 **Element Id** 中填写稳定、唯一的 ID，例如 `login.submit`。
5. 保存场景后运行，Python 即可按 ID 操作。

SDK 默认在 Editor、Development Build 中启用 TCP 服务；明确设置 `UNITY_BRIDGE_ENABLED` 编译符号也可启用。普通非开发构建不启动服务。每个 Player 只需要一个活动 SDK Host。

动态创建的对象应显式注册，尤其是创建后保持 inactive 的对象：

```csharp
using RobotFramework.UnityBridge;

// obj 上应已经有 Button 或 Toggle。
var element = obj.GetComponent<BridgeElement>();
if (element == null) element = obj.AddComponent<BridgeElement>();
element.Configure("inventory.confirm");

// 也可扫描刚实例化的整个 UI 子树，包括 inactive 子节点：
BridgeElement.RegisterHierarchy(instantiatedPanel);
```

初始场景、后续加载场景中的已有元素由 SDK 扫描。不要把 BridgeElement 加在按钮的文本子对象上，它应与 Button / Toggle 位于同一 GameObject。

首版支持显示器 0 的 Screen Space Overlay / Screen Space Camera，后者要求有效相机且不输出到 RenderTexture。`visible` 为几何可见性，遮挡在点击时另外检测。

## 4. Android / ADB 模式

1. 在 Unity Android Player Settings 中将 **Internet Access** 设置为 **Require**，确保清单包含网络权限。
2. 在 Build Settings 中启用 **Development Build**，将包含 SDK Host 的应用安装到设备。
3. 启动应用并保持前台运行；Python 的 Connect 只负责连接，不负责安装或启动 APK。
4. 在电脑连接已授权的 ADB 设备后调用：

```python
from UnityBridge import UnityBridgeClient

with UnityBridgeClient(adb_path="adb") as bridge:
    info = bridge.connect(serial="emulator-5554", server_port=13000)
    print("ADB 自动分配的电脑端口:", info["host_port"])
    bridge.click("demo.login", timeout=5)
    bridge.wait_for_state("demo.home", "visible", timeout=5)
```

库自动执行 `adb -s SERIAL forward tcp:0 tcp:13000`，取得本地端口并完成 TCP 握手。用户无需维护转发命令。指定电脑端口时使用 `host_port=23000`，内部采用 `--no-rebind` 避免覆盖已有映射。

启动应用后可以直接调用 `Connect To Unity` / `connect()`，在 `timeout` 总预算内自动等待 SDK 握手成功，无需先固定 Sleep。连接返回后，界面加载仍通过元素状态等待判断，详见第 7 节。

未指定 serial 时，必须恰好有一个已授权的 `device` 状态设备。关闭时仅删除本实例创建且当前仍然匹配的转发。设备离线导致清理失败会报告具体错误，恢复连接后可以再次 `close()` 清理。

## 5. Robot Framework 用法

具备 Robot Framework 环境后，按文件路径导入：

```robot
*** Settings ***
Library           ../python/UnityBridge.py
Suite Setup       Connect To Unity Editor
Suite Teardown    Close Unity Connection

*** Test Cases ***
登录
    Wait For Unity Element State    demo.login    visible    timeout=5s
    Click Unity Element            demo.login    timeout=5s
    Wait For Unity Element State    demo.home    visible    timeout=5s
```

公开关键字：

| 关键字 | 作用 |
| --- | --- |
| `Connect To Unity` | ADB 转发 + TCP + 握手 |
| `Connect To Unity Editor` | 直接连接本机 Editor / Player |
| `Close Unity Connection` | 关闭连接并清理拥有的转发 |
| `Get Unity Element State` | 返回状态快照字典 |
| `Wait For Unity Element State` | 等待四种状态之一 |
| `Click Unity Element` | 等待可点击并派发一次点击 |

后续如需安装 Robot 依赖，可执行 `python -m pip install "./bridge/python[robot]"`。在仓库根目录运行现成用例：

```powershell
python -m robot -d results/bridge bridge/examples/bridge_smoke.robot
python -m robot -d results/bridge -v MODE:android -v DEVICE_SERIAL:emulator-5554 bridge/examples/bridge_smoke.robot
```

每次重新运行完整 smoke 用例前，重新进入 Play Mode 或重启示例应用，恢复被用例改变的按钮与 Toggle 初始状态。使用自己的 Appium 启动关键字时，在 Suite Setup 中先启动应用再连接 Bridge。

## 6. 失败和超时的含义

- 不存在的元素快照是 `exists=false, visible=false, enabled=null`。因此 `not visible` 可以成功，`disabled` 会继续等待。
- `Click` 自己等待“存在 + 可见 + enabled + 实际射线命中”，不必在每次点击前写四个准备关键字。
- 点击采用 UGUI 指针事件派发；不修改真实鼠标或 Input System 设备状态，不模拟按住时长。
- 点击响应成功表示事件派发完成，业务是否完成仍需后续断言。
- `BridgeWaitTimeout` / `BridgeClickTimeout` 表示已知的条件失败；后者包含 `effect=not_started`。
- `BridgeClickOutcomeUnknown` 表示点击可能已经执行，但没有获得可靠响应。库不自动重试；重新连接后先检查业务状态。
- Unity 主线程同步回调不能被安全抢占。客户端仍按自身截止时间退出，不保证对已发生的业务副作用回滚。

协议和详细边界参见 [DESIGN.md](DESIGN.md)。

## 7. 等待服务就绪与查看连接耗时

`Connect To Unity` 和 `Connect To Unity Editor` 都会等待合法的 `bridge.hello` 成功响应。只连通 TCP 端口不算就绪：ADB 的电脑端口可能已经可连，但设备上的 SDK 尚未监听，握手会立即断开。连接关键字会在总超时内重新建连并握手，成功就立即返回。

直接修改原有 Setup 即可，`30s` 表示最长等待时间：

```robot
Test Unity Bridge
    [Setup]    Connect To Unity    serial=${ADB_DEVICE}    server_port=13000    timeout=30s
    [Teardown]    Close Unity Connection
    Wait For Unity Element State    test.jump    visible    timeout=10s
    Click Unity Element    test.jump    timeout=5s
```

需要记录本次实际等待多久时，在自己的 Setup 关键字中获取返回字典：

```robot
*** Keywords ***
Connect And Wait For Unity
    ${info}=    Connect To Unity    serial=${ADB_DEVICE}    server_port=13000    timeout=30s
    Log    Unity Bridge ready in ${info}[connect_elapsed_ms] ms; attempts=${info}[connect_attempts]
```

普通 Python：

```python
info = bridge.connect(serial="emulator-5554", server_port=13000, timeout=30)
print(info["connect_elapsed_ms"], info["connect_attempts"])
```

- `connect_elapsed_ms` 使用 Python 单调时钟统计，从本次 Connect 开始到握手成功；Android 模式包含设备检查与创建转发。这是本次客户端观察到的连接等待耗时，不能用来推断 APK 进程启动到监听的精确耗时。
- `connect_attempts` 为 TCP / hello 尝试次数，首尝即成功时为 `1`。字段由 Python 添加，不改变 TCP 协议。
- 重试只用于建连失败、握手 EOF / reset / 传输超时。每次尝试最多约 1 秒，失败后间隔最多 0.1 秒；所有尝试共享 `timeout`，不会每次重新获得完整预算。
- 协议不兼容、坏 JSON、`SERVER_BUSY` 等明确 RPC 错误立即失败，ADB 设备/转发错误也直接报告。每个失败尝试都会关闭 socket，重试期间复用同一条本实例转发。
- 超时后抛出 `BridgeConnectError`，包含尝试次数、TCP/hello 耗时与最后错误，随后清理本实例转发。清理有独立的有界预算，因此失败调用的总墙钟耗时可能稍长于连接预算。
- Connect 成功只确认 SDK 通信可用；界面就绪继续用 `Wait For Unity Element State`。已连接后的元素操作不自动重连、重放，点击仍只派发一次。

此变更只涉及 Python 库，已可工作的 APK 不需要为它重新打包。更新库时保留 `UnityBridge.py` 和整个 `_unity_bridge` 子目录；若通过 pip 安装，需重新安装更新后的本地包并重启测试进程。

## 8. 本机检查与验证边界

当前开发机器没有 Unity、ADB 和 Robot Framework。已执行结果见 [VALIDATION.md](VALIDATION.md)。本仓库提供两类本机检查，以及待 Unity 环境执行的 PlayMode 测试：

```powershell
# 只依赖 Python 标准库：参数、组帧、错误处理、超时和 ADB 命令替身检查。
py -3.14 -m unittest discover -s bridge/tests -p test_python.py -v

# 本机 .NET 10：解析全部 SDK C# 语法；编译并运行实际协议/TCP 源码。
# 首次运行会在本地还原无第三方 NuGet 包的测试项目。
dotnet run --project bridge/tests/csharp/BridgeContractTests.csproj

# 让 Python 连接实际 C# TCP 实现；元素执行仍为测试替身。
$env:UNITY_BRIDGE_CSHARP_HARNESS = (Resolve-Path bridge/tests/csharp/bin/Debug/net10.0/BridgeContractTests.dll).Path
py -3.14 -m unittest discover -s bridge/tests -p test_python.py -v
```

.NET 检查使用本机 SDK 附带的 Roslyn / Newtonsoft 程序集，项目 NuGet.Config 清空远程源。它验证协议与网络部分以及 C# 语法，**不验证 Unity API 类型绑定、场景渲染或 Android 构建**。

Unity 环境的后续验收：在项目 `Packages/manifest.json` 的 `testables` 数组中加入 `com.robotframework.unitybridge`，确保项目安装 Unity Test Framework，然后在 **Window → General → Test Runner → PlayMode** 中执行包内测试。测试覆盖缺失元素、inactive 与 enabled 的区别、单次点击、遮挡、按下时禁用、重复 ID、timeScale=0 超时。随后运行示例 smoke 和 Android 实机用例。
