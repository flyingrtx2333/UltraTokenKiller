# 原生引擎兼容性

2026-09-19 补充：Windows Codex 0.138.0 / gpt-5.6-luna 已实际触发自动工具钩子并完成原文查询，一次代码修复通过全部 7 项测试。但全局 `projects` 配置变化及第二次修改命令失败仍未解决，自动接入仍为开发预览、未通过整体验收。详见[新增预算验收](docs/codex-hooks-acceptance-2026-09-19.md)。下表早期证据不足以声明正式支持。

本表仅描述当前原生实现，不将旧集成版证据作为原生对标结果，也不声明正式完整支持。

| 路径 | 当前证据 | 尚未完成 |
|---|---|---|
| Windows Codex 0.138.0 / 现有订阅 / gpt-5.6-luna | 隔离实例真实完成输入压缩、一次工具输出压缩与 MCP 原文找回，返回码 0 | 自动接入、强制钩子覆盖、真实代码修改任务、多次效果对照 |
| Windows Codex / gpt-5.6-terra | 先前原文找回专项任务通过 | 不能作为完整三层联动证据 |
| Responses HTTP/SSE | 离线协议测试及上述 Luna 真实任务 | API Key、认证过期等真实提供商组合 |
| Chat Completions / Anthropic Messages | 本地协议与 usage 处理测试 | Hermes CLI/gateway 与真实提供商验收 |
| Responses WebSocket | 本地实际 socket 转发与关闭测试 | 真实 Codex WebSocket、多模态与压缩联动 |
| 多模态 | 原样透传的离线测试 | 图像压缩及真实多模态任务 |
| 原文恢复 | 内存、会话隔离、过期、容量、历史稳定性测试；真实 MCP 调用 | 正常客户端自动会话绑定 |
| 工具压缩 | 部分 Git、搜索、测试及诊断命令；真实 Git 暂存差异和 pytest 成功/失败离线执行 | 固定 RTK 基线所有命令与参数组合；不能将未知格式透传算作覆盖 |
| 回答策略 | 各档离线规则测试；Luna 联动任务使用 lite | 相同任务的正确性和长度成对对照 |
| Windows / WSL Ubuntu | 两个环境运行离线测试；Windows 运行真实客户端任务 | WSL 原生 Codex 未安装/未验收；干净机器安装、自启和卸载验收 |
| macOS arm64 26.6.2 / Codex 0.153.4 | 隔离 Python 3.11 环境完成 98 项离线测试；修复 WebSocket 清理取消泄漏；ChatGPT 登录、`hooks/list`、精确钩子信任及配置不变检查通过 | 系统 Python 3.9 无法直接安装；0.153.4 尚未完成真实模型任务；缺少运行时准备、登录自启、升级/卸载验收，无正式支持声明 |

macOS 实机证据见 [macOS arm64 隔离验收](docs/macos-arm64-acceptance-2026-09-19.md)。

Luna 手动包装命令链路通过时累计使用 16/20 次，随后自动钩子编码尝试未通过，累计达到 19/20。钩子信任与冲突隔离已修复并通过离线预检，真实重验等待新增预算。提供商实际 usage 缺失，不展示推算成实际的 token 或现金节省。详见 [原验收记录](docs/acceptance-luna-2026-09-19.md) 与 [自动会话进度](docs/codex-auto-session-2026-09-19.md)。
