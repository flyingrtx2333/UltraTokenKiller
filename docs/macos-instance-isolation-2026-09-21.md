# macOS 实例隔离与原文恢复验收（2026-09-21）

## 被测版本与环境

- 源码提交：`a103ac2`（服务归属）及 `ea3af6d`（回环 WebSocket 代理策略）。
- 机器：`xiangjunshengdeMac-mini.local`，macOS 26.6.2，Apple Silicon arm64。
- Python：Homebrew CPython 3.14.7。
- 隔离源码：`/tmp/utk-instance-a103ac2`。
- 隔离配置：`UTK_HOME=/tmp/utk-instance-a103ac2-smoke`。
- 未安装 LaunchAgent，未接入 Codex 或 Hermes，模型请求数为 0。

## 离线回归

- Mac arm64：`237 passed, 1 skipped, 2 warnings`。
- Windows x64：`235 passed, 3 skipped, 1 warning`。
- macOS 首次回归复现了系统 SOCKS 代理被 WebSocket 库用于回环地址的问题。修复后，`127.0.0.1`、`localhost` 和 `::1` 明确绕过系统代理，远程 WebSocket 仍使用库的代理发现。

## 实际安装与恢复闭环

执行 `utk install --no-clients --no-autostart` 时，机器已有服务占用 18787。新实例没有复用其他 `UTK_HOME` 的管理服务或输入代理，最终选择：

- 管理看板：18790。
- 输入代理：18789。

通过 `UTK_SESSION_ID=macfilesmokesession123456 utk exec -- json ...` 压缩 500 条结构化记录：

- 输出为 162 字节并包含 `UTK retrieve` 标识。
- 使用同一会话经 broker 取回原文，SHA-256 与输入文件一致。
- 测试实例停止后，18790 不再可达；原有 18787 服务响应内容保持一致且继续可达。

机器可读证据见 `docs/evidence/macos-instance-isolation-20260921.json`。本次只验证实例隔离、原生 JSON 工具、内存恢复和回环 WebSocket；不提升 RTK 逐命令固定上游对标状态。
