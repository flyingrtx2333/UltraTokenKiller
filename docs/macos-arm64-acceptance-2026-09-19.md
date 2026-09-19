# macOS arm64 隔离验收

2026-09-19 在远端 `xiangjunshengdeMac-mini.local` 完成隔离测试。系统为 Apple Silicon arm64、macOS 26.6.2。所有文件和运行时放在 `/tmp/utk-mac-test.u67QUU`，没有安装登录自启、没有改写 Codex/Hermes 配置，也没有调用模型。

## 环境结论

- 系统仅有 Python 3.9.6，不满足项目要求；没有 Homebrew、uv、pyenv、mise、Node.js 或 Codex。
- 当前 `scripts/install.sh` 直接调用系统 `python3`，不会准备兼容运行时，因此这台干净 Mac 无法按“一键安装”目标直接安装。
- 验收中临时下载 uv 0.12.17，并在测试目录安装 Python 3.11.16；随后按约束文件安装 UTK 和测试依赖。该做法用于验证源码，不代表安装器已经通过。
- `utk capabilities` 可以启动。未执行 `utk install`；隔离 `UTK_HOME` 下运行 `utk doctor` 如预期报告配置和两个服务未安装，内置工具压缩可见。
- 目标机没有 Codex，所以不能进行 macOS Codex 真实客户端、订阅认证、自动钩子或模型任务验收。

## 发现与修复

初次全量测试结果为 1 项失败、97 项通过。失败项为 `tests/test_protocols_v2.py::test_websocket_text_binary_and_usage`：客户端退出 WebSocket 上下文时，ASGI 请求任务的取消在等待两个转发子任务收尾时泄漏，表现为 `concurrent.futures.CancelledError`。

修复将取消容错限定在 WebSocket 清理块：取消两个转发子任务后，吸收清理等待和上游关闭期间的 `asyncio.CancelledError`。正常文本帧、二进制帧、usage 记录和传输错误处理不变。

修复后：

- Windows WebSocket 专项通过。
- WSL Ubuntu WebSocket 专项通过。
- macOS arm64 WebSocket 专项通过。
- Windows、WSL Ubuntu、macOS arm64 全量离线测试均返回 0；当前共收集 98 项测试。

## 尚未通过

本次不能把 macOS 标记为正式支持：安装器仍缺少运行时准备和校验，登录自启、端口冲突、升级回滚、卸载恢复、真实 Codex/Hermes 客户端均未验证。
