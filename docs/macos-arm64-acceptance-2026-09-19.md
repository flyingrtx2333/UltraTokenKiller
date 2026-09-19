# macOS arm64 隔离验收

2026-09-19 在远端 `xiangjunshengdeMac-mini.local` 完成隔离测试。系统为 Apple Silicon arm64、macOS 26.6.2。所有文件和运行时放在 `/tmp/utk-mac-test.u67QUU`，没有安装登录自启、没有改写 Codex/Hermes 配置，也没有调用模型。

## 环境结论

- 系统仅有 Python 3.9.6，不满足项目要求；没有 Homebrew、uv、pyenv 或 mise。首次非交互 PATH 探测没有发现 Codex，后续确认 `/Applications/ChatGPT.app/Contents/Resources/codex` 提供内置 CLI，Node.js 位于 `/opt/homebrew/bin/node`。
- 当前 `scripts/install.sh` 直接调用系统 `python3`，不会准备兼容运行时，因此这台干净 Mac 无法按“一键安装”目标直接安装。
- 验收中临时下载 uv 0.12.17，并在测试目录安装 Python 3.11.16；随后按约束文件安装 UTK 和测试依赖。该做法用于验证源码，不代表安装器已经通过。
- `utk capabilities` 可以启动。未执行 `utk install`；隔离 `UTK_HOME` 下运行 `utk doctor` 如预期报告配置和两个服务未安装，内置工具压缩可见。
- ChatGPT 应用内置 `codex-cli 0.153.4`，`codex login status` 确认使用 ChatGPT 登录。该版本未加入 shell PATH，且高于 UTK 当前只放行的 0.138.0。
- 不调用模型的应用服务器检查通过：`hooks/list` 返回有效结果，UTK 临时钩子的精确哈希信任可生成并由二次查询确认，检查前后用户级 `~/.codex/config.toml` 字节不变。

## 发现与修复

初次全量测试结果为 1 项失败、97 项通过。失败项为 `tests/test_protocols_v2.py::test_websocket_text_binary_and_usage`：客户端退出 WebSocket 上下文时，ASGI 请求任务的取消在等待两个转发子任务收尾时泄漏，表现为 `concurrent.futures.CancelledError`。

修复将取消容错限定在 WebSocket 清理块：取消两个转发子任务后，吸收清理等待和上游关闭期间的 `asyncio.CancelledError`。正常文本帧、二进制帧、usage 记录和传输错误处理不变。

修复后：

- Windows WebSocket 专项通过。
- WSL Ubuntu WebSocket 专项通过。
- macOS arm64 WebSocket 专项通过。
- Windows、WSL Ubuntu、macOS arm64 全量离线测试均返回 0；当前共收集 98 项测试。

## 尚未通过

本次仍不能把 macOS 标记为正式支持：安装器仍缺少运行时准备和校验，登录自启、端口冲突、升级回滚、卸载恢复及 Hermes 真实模型任务尚未验证。

Codex `0.153.4`、ChatGPT 订阅、`gpt-5.6-luna` 的真实编码验收已运行到授权账本 `19/20`。本轮真实任务执行了命令并调用了 `utk_retrieve`，但命令工具名未命中当时的精确 matcher，UTK 没有生成工具事件，原文查询返回不可用，源码也未修改，因此验收报告为未通过。用户 Codex 配置前后逐字节不变。

随后已将会话 matcher 扩展为所有 `PreToolUse` 事件，并限定为仅改写含字符串型 `command` 或 `cmd` 的输入。Mac 离线预检确认 MCP 原文找回、钩子信任、零模型请求、`19/20` 账本和原配置不变均通过；同一 13,381 字符夹具的 `grep` 输出在 Mac 上生成了恢复句柄和 601 token 的工具压缩估算。完整编码任务需要至少 4 次模型提交，剩余 1 次不足，因此没有越过 20 次授权上限重试，也未把该组合标记为正式支持。
