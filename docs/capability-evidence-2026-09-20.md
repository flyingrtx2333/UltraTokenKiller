# 能力证据绑定（2026-09-20）

能力状态现在绑定实现文件、对应测试、固定上游提交和最近一次完整离线测试的 SHA-256 指纹。仅存在测试文件不再视为“离线通过”；实现或测试变化后，状态自动降为“已实现待验证”，直到完整套件重新通过并生成账本。

当前结果：

- 核心能力 36 项：30 项绑定当前源码并离线通过，6 项已实现待验证。
- 命令契约 22 项：22 项已审阅且绑定当前 `tool_filters.py`、执行层和契约测试。
- 固定 RTK 的 211 个命令变体已冻结为覆盖分母；57 项映射现有审阅契约，154 项仍待逐项验证。映射不等于实现或上游对标通过。
- 三层逐项核心分母为 256：Headroom 24、RTK 211、Caveman 21。机器清单和可读报告见 `src/ultratokenkiller/data/full-parity-inventory.json` 与 `docs/full-capability-parity-2026-09-21.md`。33/36 是高层产品能力状态，不代表这 256 项全部完成固定上游对标。
- RTK 固定上游逐项对标当前为 0/211；Caveman 5 类成对质量仍需 180 次授权模型请求；Headroom 的固定样例证据与未逐项比较能力分开计数。
- 旧 Codex 实机证据没有记录当前源码指纹，因此 `recovery.mcp`、Responses HTTP/SSE、Git 工具、回答档位和 Codex 订阅接入从“真实客户端通过”降为离线或待验证。旧报告仍保留作历史证据。
- 上游对标和真实客户端源码绑定数均为 0；`parity_certified` 保持 `false`。

输入层新增保守的管道表格识别，只在至少四行且列数一致时处理，并仅折叠完全相同的连续行。内容仍写入会话绑定的内存恢复库。固定 12 个 Headroom 样例现在都能被处理并保留必需事实；短表格的显式恢复标识会占用 token，因此该样例仍未达到上游压缩率的 90%，不会提升为上游对标通过。

复现：

```sh
python scripts/generate-verification-ledger.py
utk capabilities --json
```

账本位于 `src/ultratokenkiller/data/verification-ledger.json`，随 wheel 分发。真实客户端和上游状态只能由另行生成、且包含同一源码指纹的证据提升。

## 固定上游四路输入证据

固定 Headroom、RTK、Caveman 提交均通过 checkout 哈希验证。Headroom 12 个合成输入样例已完成透传、冻结基础版、固定上游和当前 UTK 四路对齐，事实保持全部通过，模型调用为 0。元数据报告见 `docs/evidence/four-route-matrix-20260920.json`；报告不包含提示词、回答正文或认证信息。

当前源码绑定状态为 33/36 离线通过，剩余 3 项为 Caveman 成对质量及 Hermes CLI/gateway 真实客户端验收。RTK 工具输出及 Caveman 回答质量继续由各自独立能力项验收，不由输入参考报告代替。
