# macOS arm64 阶段一隔离验收（2026-09-20）

## 环境

- UTK 提交：`219d043192197af2096404313ffc77fc3b3061c3`
- 主机：`xiangjunshengdeMac-mini.local`
- 系统：macOS 26.6.2，Apple Silicon arm64
- 隔离目录：`/tmp/utk-stage1-219d043`
- Python：由 uv 创建的 CPython 3.11.16
- Codex：`/Applications/ChatGPT.app/Contents/Resources/codex`，版本 0.153.4
- Hermes Agent：0.21.0；仅探测，未接入或修改配置

## 结果

- 完整离线测试：203 项通过，0 项失败。
- 实际打包服务：`/dashboard`、JS、CSS、`/brand/utk-icon.svg`、状态、指标、事件、配置、能力及恢复接口均返回 200。
- SSE：`/api/v1/stream?hours=24` 返回 200，并驱动页面持续刷新。
- Playwright 分别以 1440×1100 和 390×844 视口渲染实际页面，Logo、Favicon、桌面与窄屏布局正常。
- 未运行压缩或回答评测时，两个评测接口按契约返回 404；页面显示真实“未运行”状态。
- wheel 在 Windows 构建检查中包含 12 个 `static/brand` 文件；Mac 从同一提交源码安装并成功提供这些资源。

## 安全与预算

- 使用独立 `UTK_HOME` 和端口 18797；未安装 LaunchAgent，未修改日常 Codex/Hermes 配置。
- 未提交提示词、回答、凭据或用户指标；截图是隔离实例的真实空状态。
- 本轮模型请求为 0。历史授权账本仍按仓库证据记录为 57/60，剩余 3 次未使用，也不作为发布级评测预算。

## 尚未完成

- Hermes CLI/gateway 真实任务。
- Codex 固定任务三次重复对照、API Key 路径和真实 WebSocket 多模态联动。
- 登录自启、重复安装、升级失败回滚及卸载恢复。
- Headroom、RTK、Caveman 全量能力清单对标。


## 最新源码与安装器复验（`d4e37e9`）

- 隔离仓库更新到 `d4e37e9`；macOS arm64 完整离线回归为 **207 passed, 1 skipped**。
- Shell 安装器在系统 Python 不满足要求时，通过现有 `/opt/homebrew/bin/uv` 创建 Python **3.11.16** 环境。
- 实机发现并修复了原子切换后 console script 仍引用 `venv.new` 的问题；修复后 `utk doctor`、`utk status`、`utk capabilities --json` 均返回 0。
- 重复安装保留 `venv.previous`；安装前后的 Codex/Hermes 配置哈希及 LaunchAgent 清单一致。
- 指定错误的离线 uv SHA-256 时安装器返回 1，明确报告 `Runtime helper checksum mismatch`，且不产生活动运行时。
- 使用最新版打包页面重新生成 1440×1100 与 390×844 截图；能力状态为 36 项、离线通过 29 项、待验证 7 项、当前源码绑定 29 项、命令契约 22/22。
- 本轮未调用模型、未安装或接入客户端、未创建 LaunchAgent；测试服务及隔离 Chrome 进程在验收后关闭。

更新截图：

- `docs/assets/dashboard-macos-arm64-desktop.png`
- `docs/assets/dashboard-macos-arm64-mobile.png`

截图数据性质：真实页面、隔离空状态；无提示词、回答正文、用户名、凭据或日常目录。
