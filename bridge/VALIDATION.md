# Demo 验证记录

日期：2026-10-27。环境：Windows、Python 3.14、.NET SDK 10.0.301。

本机未安装 Unity、ADB 和 Robot Framework。验证以静态检查为主，并运行本机 Python / C# 检查；没有把替身元素的成功当成 Unity 场景验证。

| 检查 | 结果 | 能证明的范围 |
| --- | --- | --- |
| Python 入口和源码 | 通过 | 顶层只有 `UnityBridge.py`；可导入普通 Python API；源码语法有效 |
| Python 标准库测试 | **18 项通过，无跳过** | 参数校验、TCP 帧边界、异常分类、总截止时间、ADB 命令替身及清理 |
| Python → 实际 C# TCP | 通过，包含在上述 18 项中 | 使用 SDK 原始 Protocol.cs / TcpServer.cs 完成握手、读取、等待、点击与已知超时；元素执行为测试替身 |
| SDK C# 语法 | 通过 | 10 个 Runtime / Editor / Sample / Test 文件，3 种编译符号配置 |
| C# 协议及网络 | 通过 | 编译运行实际协议和 TCP 源码；验证拆包、重复 ID、单请求限制、第二客户端、超时、坏帧及大小上限 |
| UPM 配置与元数据 | 通过 | 6 个 JSON / asmdef 文件可解析；24 个元数据 GUID 唯一且资产有对应 .meta |
| Unity API 类型绑定及 UGUI 行为 | **未执行** | 需要真实 Unity Editor 编译并运行；仅语法解析不能证明 Unity API 使用完全正确 |
| 包内 PlayMode 测试 | **已提供，未执行** | 需要 Unity Test Framework 和 Unity 工程 |
| Robot Framework 用例 | **已提供，未执行** | 需要 Robot Framework 环境；本机只检查了关键字适配方法的直接调用 |
| Android / ADB 实机 | **未执行** | 需要带 SDK 的 Android 开发构建及已授权设备 |

本机复现命令见 [README.md 的检查说明](README.md#7-本机检查与验证边界)。

后续优先顺序：Unity Package Manager 导入并确认编译 → PlayMode 测试 → 示例场景的普通 Python 调用 → Robot smoke → Android 构建和 ADB 实机。
