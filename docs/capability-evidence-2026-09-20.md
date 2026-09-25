# 能力证据绑定

本文件是持续维护的当前状态说明，初建于 2026-09-20，最近刷新于 2026-09-22。带日期的实机、平台和阶段验收报告保留其运行当时的结论，不随本文件回写。

能力状态绑定实现文件、对应测试、固定上游提交和最近一次完整离线测试的 SHA-256 指纹。仅存在实现或测试文件不视为验证通过；实现、测试或证据变化后，状态自动降为“已实现待验证”，直到完整套件重新通过并生成账本。

## 当前结果

<!-- BEGIN GENERATED CURRENT STATUS -->
高层产品能力共 **36 项**：**33 项**证据有效并离线通过，**3 项**已实现但当前证据待重新验证，**0 项**拥有当前源码绑定的实机通过证据。

完整三层核心分母共 **256 项**：固定上游完整通过 1 项、部分通过 40 项、离线通过 42 项、仅完成契约映射 30 项、资产未就绪 2 项、未实现 141 项。

“已实现”表示实现文件和测试入口仍存在；“当前已验证”还要求完整测试账本、实现与测试源码指纹以及相关证据哈希全部匹配。代码或证据变化后，状态会保守降级，不沿用旧结论。

当前 3 项已实现但证据待重新验证：

- `client.hermes_cli`
- `client.hermes_gateway`
- `response.paired_quality`
<!-- END GENERATED CURRENT STATUS -->

机器清单和可读报告分别位于 `src/ultratokenkiller/data/full-parity-inventory.json` 和 `docs/full-capability-parity-2026-09-21.md`。能力状态与完整分母是两套口径：36 项描述产品层能力，256 项用于逐项跟踪固定 Headroom、RTK 和 Caveman 能力；契约映射、安全透传和测试文件存在均不等于完整对标通过。

## 复现与账本

```sh
python scripts/generate-verification-ledger.py
python scripts/refresh_full_parity_ledger.py
python scripts/generate_current_status.py
utk capabilities --json
```

高层账本位于 `src/ultratokenkiller/data/verification-ledger.json`，完整分母账本位于 `src/ultratokenkiller/data/full-parity-verification-ledger.json`，均随 wheel 分发。真实客户端和上游状态只能由包含相同源码指纹与证据哈希的记录提升。

`python scripts/generate_current_status.py --check` 只检查 README、本文件和当前路线图的生成区块，不写文件；任一状态数字或待验证清单过期时返回非零退出码。

## 固定上游证据边界

- Headroom 固定样例、RTK 命令对照和 Caveman 策略对照分别计数，不能互相替代。
- 固定上游样例成功不等于该能力已覆盖失败、未知格式和全部适用平台。
- 旧 Codex 与客户端报告未绑定当前源码指纹时仍作为历史证据保留，但不提升当前状态。
- `parity_certified` 在全部门槛完成前保持 `false`。
- Caveman 五类真实回答质量场景仍需单独授权的 180 次模型请求；离线策略测试不能代替该结论。
