# 原生引擎兼容性

2026-09-19 最新补充：macOS arm64 / Codex 0.153.4 / 现有订阅 / gpt-5.6-luna 已通过日常启动器自动工具压缩与 MCP 找回，以及隔离配置下的输入、工具、恢复组合验收；均采集到实际 usage，用户配置不变。累计计入 57/60 次，其中 4 次为修复前路由绕过的元数据补记。自动适配仅覆盖已验证的基础权限，旧 sandbox、自定义 profile 和已有网络代理仍拒绝自动接入。详见[最新报告](docs/macos-launcher-acceptance-2026-09-19.md)。下文较早的 40/40 和输入尚未闭环记录保留为历史，不代表最新结果；仍未达到正式发布条件。

2026-09-19 补充：Windows Codex 0.138.0 / gpt-5.6-luna 已实际触发自动工具钩子并完成原文查询，一次代码修复通过全部 7 项测试。但全局 `projects` 配置变化及第二次修改命令失败仍未解决，自动接入仍为开发预览、未通过整体验收。详见[新增预算验收](docs/codex-hooks-acceptance-2026-09-19.md)。下表早期证据不足以声明正式支持。

本表仅描述当前原生实现，不将旧集成版证据作为原生对标结果，也不声明正式完整支持。

Hermes CLI 与 gateway 共用的 `pre_tool_call` shell hook 已完成离线实现和配置恢复测试。UTK 仅为精确命令 `utk hermes-hook` 写入受管授权，复杂 shell、未知命令和结构化工具透传；尚无本机 Hermes 真实任务证据，因此状态仍为“已实现待验证”。

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
| macOS arm64 26.6.2 / Codex 0.153.4 | 现有订阅 gpt-5.6-luna 在仅放行 UTK socket 的配置下完成自动钩子、工具压缩、MCP 找回、源码修复及 7 项测试；后续已采集实际 usage、触发输入压缩；累计 40/40 | 输入专项在找回成功后因额度耗尽未取得最终标记；日常旧 sandbox/profile 自动兼容、三次对照、运行时准备、自启与升级/卸载待验收，无正式支持声明 |

macOS 实机证据见 [离线验收](docs/macos-arm64-acceptance-2026-09-19.md)、[真实编码复验](docs/macos-codex-live-followup-2026-09-19.md) 和 [socket / usage / 输入复验](docs/macos-native-ipc-2026-09-19.md)。

Luna 手动包装命令链路通过时累计使用 16/20 次，随后自动钩子编码尝试未通过，累计达到 19/20。钩子信任与冲突隔离已修复并通过离线预检，真实重验等待新增预算。提供商实际 usage 缺失，不展示推算成实际的 token 或现金节省。详见 [原验收记录](docs/acceptance-luna-2026-09-19.md) 与 [自动会话进度](docs/codex-auto-session-2026-09-19.md)。
