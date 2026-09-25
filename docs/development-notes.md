# 开发记录与测试命令

以下内容从旧 README 移入，保留当时的开发记录和测试命令；历史状态不代表最新版的使用效果。日常使用请看 [README](../README.md)。

## 当前原生能力

当前是开发预览版，尚未达到固定版本三层核心能力完整对标标准。

- 输入：JSON 异常值及少数状态保留、日志聚合、多语言代码摘要、补丁、搜索结果、中英文长文本和内联图像压缩；本地语义模型需单独安装。图像只在确认是大型照片且压缩至少减少 15% 时缩放，文字密集、细节任务、用途不明或能力未就绪时保守透传。
- 恢复与缓存：原文仅在守护进程内存保存；MCP `utk_retrieve` 按会话找回。已压缩和已透传历史保持稳定；容量不足时停止新增有损压缩。
- 工具：`utk exec` 提供部分 Git、搜索、测试及诊断输出规则。支持暂存差异、Git 工作目录参数和 `python -m pytest`；提交日志保留正文。stdout 与 stderr 分通道有界捕获并写回原通道，容量超限时整体流式透传。未知输出透传，保留退出码，取消时清理自有进程树。
- 统计：会话内工具指标通过认证的本地接口由守护进程统一写入 SQLite，避免沙箱内共享数据库失败。相同执行标识去重；不保存命令参数、提示词、回答正文或凭据。
- 回答：lite/full/ultra/off 与文言档位；结构化输出和详细解释要求优先。不截断已生成内容，不声称未经对照的节省比例。
- 协议：Responses、Chat Completions、Anthropic Messages 的 HTTP/SSE 转发；WebSocket 透传有离线测试，但未完成真实客户端验收。
- 看板：终端与网页读取统一统计。网页显示原文内存状态、已观测命令的压缩比例与未完成对标提示。
- 证据：能力与命令契约绑定实现、测试和固定基线的源码指纹；代码变化会自动将旧状态降级，避免把“文件存在”当作验证通过。

**已验证：**Windows 与 WSL Ubuntu 离线回归；Windows Codex 0.138.0 使用现有订阅和 `gpt-5.6-luna` 完成输入压缩、`utk exec` 压缩及 MCP 原文找回任务。验收使用隔离端口和临时配置覆盖，没有替换本机现用代理。

真实模型账单用量未返回，仍显示未知。Hermes CLI／gateway 的受管 shell hook 已实现离线验证：只改写可证明安全的终端命令，只授权 `utk hermes-hook`，禁用时保留用户钩子与授权；真实 Hermes 客户端任务仍未验收。全部 RTK 命令、上游效果对照和三平台干净安装也尚未完整验收。详见 [兼容矩阵](../COMPATIBILITY.md) 和 [Luna 验收记录](acceptance-luna-2026-09-19.md)。

## 安装

Codex 自动会话开发预览入口为 `utk codex --model gpt-5.6-luna`。它只对新启动的进程绑定代理、只读命令钩子和原文查询，不改全局接入设置；修复后的真实编码验收仍待完成。版本限制与最新证据见 [自动会话进度](codex-auto-session-2026-09-19.md)。

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
# 一次生成透传、旧版、固定上游和当前 UTK 四路对齐报告
utk benchmark --mode matrix --reference path/to/reference-results.json --model gpt-5.6-luna
utk web
```

维护者可在三个隔离 checkout 均处于锁定提交时生成输入层上游结果包：

```sh
python scripts/generate-reference.py --headroom path/to/headroom --rtk path/to/rtk --caveman path/to/caveman --output reference-results.json
```

结果包会分别记录三层覆盖数；当前固定样例是输入压缩套件，因此 RTK 与 Caveman 覆盖明确为 0，不会把“提交已校验”冒充三层对标通过。Headroom 缺少固定提交编译扩展时生成会失败并说明原因。首份实测结果与剩余差距见 [固定上游输入层对照](upstream-input-reference-2026-09-20.md)。

维护者也可以让固定 RTK 二进制读取捕获的公开失败输出，以验证命令专属过滤器，而不重新执行测试或写操作：

```sh
python scripts/generate-rtk-reference.py --checkout path/to/rtk --binary path/to/rtk-binary --output rtk-reference.json --comparison rtk-comparison.json
```

当前 66 个捕获输出样例均保留关键事实，其中包含 `rg`、`grep`、文件列表、原生 `read`／`json`／`smart`，Git，以及 `gh`／`glab`／`gt` 的成功、失败和显式机器格式透传。新增成功形态的 UTK 压缩效果达到对应固定 RTK 的至少 90%；失败形态保持关键错误，固定 RTK 自身增加失败前缀时不制造压缩百分比。这只是已验证输出形态证据，不代表 211 个 RTK 变体已完成逐项对标，详见 [固定 RTK 捕获输出对照](upstream-rtk-reference-2026-09-20.md) 与 [Git 命令对照](rtk-git-reference-2026-09-21.md)。

能力状态的源码绑定和自动降级规则见 [能力证据绑定](capability-evidence-2026-09-20.md)，当前完成度和开发顺序见 [当前状态与开发路线图](current-status-and-roadmap.md)。

<!-- BEGIN GENERATED CURRENT STATUS -->
高层产品能力共 **36 项**：**33 项**证据有效并离线通过，**3 项**已实现但当前证据待重新验证，**0 项**拥有当前源码绑定的实机通过证据。

完整三层核心分母共 **256 项**：固定上游完整通过 1 项、部分通过 40 项、离线通过 42 项、仅完成契约映射 30 项、资产未就绪 2 项、未实现 141 项。

- Headroom：24 项；固定上游完整 1 项、部分样例 13 项、10 项待逐项对照。
- RTK：211 项；42 项已有固定上游不同级别证据、70 项已映射契约、141 项未实现；契约映射和安全透传不算完整对标。
- Caveman：21 项；14 项固定策略对照、2 项结构化绕过离线通过、5 个真实回答质量场景等待独立 180 次授权。
<!-- END GENERATED CURRENT STATUS -->

逐项输入、行为、上游证据、UTK 实现、测试、平台、实现状态、对标状态与缺口见 [完整三层能力对标清单](full-capability-parity-2026-09-21.md)。另有 6 项云服务、发布基础设施和云端分析生态功能明确排除，不纳入核心分母。

Caveman 固定策略契约可离线复现，不调用模型：

```sh
python scripts/generate-caveman-reference.py --checkout path/to/caveman --output caveman-policy-reference.json
```

当前 6 个启用档位、`off` 无操作行为和 7 组共同安全规则均通过固定源文件核对。该结果只证明指令策略覆盖，不冒充回答质量或输出节省比例，详见 [固定 Caveman 策略契约](upstream-caveman-policy-reference-2026-09-20.md)。

隔离验证时设置 `UTK_HOME`，执行 `utk install --no-clients --no-autostart`。看板优先使用 127.0.0.1:18787，端口占用时选择空闲端口。无需另外下载压缩器；`--skip-downloads` 仅作为旧命令兼容参数。

已有本地 Headroom 等代理不会自动串联。客户端上游仍指向本地代理时，安装器保留配置并提示先恢复原始上游。旧版本配置中的 headroom/rtk/caveman 字段名暂保留为迁移兼容别名，不表示运行这些外部程序。

## 管理

`install`、`doctor`、`status`、`start`、`stop`、`enable`、`disable`、`profile`、`exec`、`dashboard`、`web`、`update`、`uninstall`。

```sh
utk exec -- git status
utk exec -- read --line-numbers path/to/source.py
utk exec -- json --keys-only path/to/data.json
utk exec -- smart path/to/source.py
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

网页构建资源随 Python 包提供；最终用户无需 Node.js。当前验证边界见 [COMPATIBILITY.md](../COMPATIBILITY.md)。

## 后续计划

- 当前证据账本已完成刷新；下一阶段先完成已映射的 RTK 契约，再推进剩余命令族。
- 随后补齐 Headroom 逐项对照与本地资产；Caveman 的 180 次成对质量评测必须另行取得明确授权。
- 最后完成 Codex/Hermes、三平台安装恢复、真实客户端和发布验收矩阵。

分阶段工作量、完成条件与发布门槛见 [当前状态与开发路线图](current-status-and-roadmap.md)。

最新 Mac、协议及客户端证据以 [兼容矩阵](../COMPATIBILITY.md) 为准；README 截图只展示当前产品界面，不代替功能验收。

## 许可

UTK 使用 Apache-2.0。原生代码在本仓库实现；历史版本引用项目及普通框架依赖见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
