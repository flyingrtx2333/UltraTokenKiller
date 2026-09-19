# UltraTokenKiller

UTK 是本地原生 Token 优化工具。输入压缩、工具输出压缩、回答精简由 UTK 自己实现，不安装或调用 Headroom、RTK、Caveman。普通 Python/Web 框架依赖仍由安装器安装。

## 当前原生能力

当前是开发预览版，尚未达到固定版本三层核心能力完整对标标准。

- 输入：JSON 异常值及少数状态保留、日志聚合、多语言代码摘要、补丁、搜索结果、中英文长文本和内联图像压缩；本地语义模型需单独安装。图像只在确认是大型照片且压缩至少减少 15% 时缩放，文字密集、细节任务、用途不明或能力未就绪时保守透传。
- 恢复与缓存：原文仅在守护进程内存保存；MCP `utk_retrieve` 按会话找回。已压缩和已透传历史保持稳定；容量不足时停止新增有损压缩。
- 工具：`utk exec` 提供部分 Git、搜索、测试及诊断输出规则。支持暂存差异、Git 工作目录参数和 `python -m pytest`；提交日志保留正文。未知输出透传，保留退出码，取消时清理自有进程树。
- 统计：会话内工具指标通过认证的本地接口由守护进程统一写入 SQLite，避免沙箱内共享数据库失败。相同执行标识去重；不保存命令参数、提示词、回答正文或凭据。
- 回答：lite/full/ultra/off 与文言档位；结构化输出和详细解释要求优先。不截断已生成内容，不声称未经对照的节省比例。
- 协议：Responses、Chat Completions、Anthropic Messages 的 HTTP/SSE 转发；WebSocket 透传有离线测试，但未完成真实客户端验收。
- 看板：终端与网页读取统一统计。网页显示原文内存状态、已观测命令的压缩比例与未完成对标提示。

**已验证：**Windows 与 WSL Ubuntu 离线回归；Windows Codex 0.138.0 使用现有订阅和 `gpt-5.6-luna` 完成输入压缩、`utk exec` 压缩及 MCP 原文找回任务。验收使用隔离端口和临时配置覆盖，没有替换本机现用代理。

真实模型账单用量未返回，仍显示未知。Hermes、全部 RTK 命令、上游效果对照、自动钩子和三平台干净安装尚未完整验收。详见 [兼容矩阵](COMPATIBILITY.md) 和 [Luna 验收记录](docs/acceptance-luna-2026-09-19.md)。

## 安装

Codex 自动会话开发预览入口为 `utk codex --model gpt-5.6-luna`。它只对新启动的进程绑定代理、只读命令钩子和原文查询，不改全局接入设置；修复后的真实编码验收仍待完成。版本限制与最新证据见 [自动会话进度](docs/codex-auto-session-2026-09-19.md)。

Python 3.10+，推荐 3.11。从源码目录执行：

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

macOS / Linux：

```sh
sh ./scripts/install.sh
```

开发安装：

```sh
python -m pip install -e ".[test]"
utk install
utk doctor
utk capabilities
utk capabilities --json
utk benchmark
# 只有显式提供经过校验的固定上游结果时，才会生成上游对照结论
utk benchmark --reference path/to/reference-results.json --model gpt-5.6-luna
utk web
```

隔离验证时设置 `UTK_HOME`，执行 `utk install --no-clients --no-autostart`。看板优先使用 127.0.0.1:18787，端口占用时选择空闲端口。无需另外下载压缩器；`--skip-downloads` 仅作为旧命令兼容参数。

已有本地 Headroom 等代理不会自动串联。客户端上游仍指向本地代理时，安装器保留配置并提示先恢复原始上游。旧版本配置中的 headroom/rtk/caveman 字段名暂保留为迁移兼容别名，不表示运行这些外部程序。

## 管理

`install`、`doctor`、`status`、`start`、`stop`、`enable`、`disable`、`profile`、`exec`、`dashboard`、`web`、`update`、`uninstall`。

```sh
utk exec -- git status
utk profile safe --caveman lite
utk profile off --caveman off
```

原生输入/回答档位按请求读取，不需要重启客户端代理。Git/测试输出在命令结束后显示；原始工具输出只进入受会话约束的内存恢复库，不落磁盘，容量不足时停止新增有损压缩并透传。取消当前子进程已处理，跨平台进程树取消尚待完整实机验证。

## 统计口径

提供商 usage 单独记录实际输入、输出和缓存 token；缺失值显示未知。离线估算优先使用锁定的 `tiktoken==0.14.0` 与模型编码映射；模型无法匹配时明确标记通用编码或 UTF-8 字节启发式，不把估算写成账单用量。输入压缩与工具输出估算不相加为账单节省，不宣称订阅现金节省。回答精简只有在显式提供同任务成对结果并通过事实检查后才展示减少比例。

## 验证

```sh
python -m pytest
cd web
npm ci
npm run build
```

网页构建资源随 Python 包提供；最终用户无需 Node.js。当前验证边界见 [COMPATIBILITY.md](COMPATIBILITY.md)。

## 许可

UTK 使用 Apache-2.0。原生代码在本仓库实现；历史版本引用项目及普通框架依赖见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
