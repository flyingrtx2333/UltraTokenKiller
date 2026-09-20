# 固定 RTK 捕获输出对照（2026-09-20）

本轮首次让固定提交 `0924356b4caba4989607227b7c8824d3d8098719` 的 RTK 二进制处理与 UTK 完全相同的捕获输出。执行器校验 checkout HEAD 和二进制 SHA-256，并在隔离的临时用户目录中运行。

测试不会重新执行真实测试、Git 命令或外部写操作。临时 PATH 中的假命令只输出仓库内的固定公开 fixture，再由 RTK 的真实命令专属过滤器处理。因此每个失败场景只复用同一份原始输出，不会为统计重复产生副作用。本轮模型调用为 0。

当前覆盖八个捕获输出场景：

| 场景 | 固定 RTK 压缩率 | UTK 压缩率 | UTK／固定 RTK | 关键事实 |
|---|---:|---:|---:|---|
| Pytest 失败 | 71.94% | 68.71% | 95.50% | 通过 |
| TypeScript pretty diagnostics | 83.94% | 82.48% | 98.26% | 通过 |
| Maven 测试失败 | 52.71% | 69.99% | 132.78% | 通过 |
| Bun 测试失败 | 54.47% | 63.20% | 116.03% | 通过 |
| Deno 测试失败 | 89.44% | 91.76% | 102.60% | 通过 |
| Gradle 测试失败 | 33.19% | 52.16% | 157.14% | 通过 |
| golangci-lint v2 issues | 94.15% | 94.07% | 99.91% | 通过 |
| Git 多文件 diff | 34.63% | 54.11% | 156.25% | 通过 |

关键事实检查覆盖失败测试名、断言或诊断代码、源文件与 hunk 位置、全部变更行、失败计数和构建结果。UTK 对未知失败格式仍会透传，不把无法确认的格式算作压缩支持。

固定上游的原始结果与环境指纹见 [upstream-rtk-reference-20260920.json](evidence/upstream-rtk-reference-20260920.json)，逐样例比较见 [upstream-rtk-comparison-20260920.json](evidence/upstream-rtk-comparison-20260920.json)。两份文件使用锁定 tokenizer 的离线估算，不是提供商账单 usage。

这 8 个样例只是 RTK 命令族对标的早期证据。它们不能代表已完成现有 211 个发现项，也不能证明 Git 的其他输出形态、GitHub CLI、其他测试框架、云基础设施工具或平台取消语义已经完成固定上游对标。后续仍需按机器可读清单逐项增加成功、失败、未知格式和适用平台证据。

复现命令：

```sh
python scripts/generate-rtk-reference.py --checkout output/reference-rtk --binary output/reference-rtk/target/release/rtk.exe --output docs/evidence/upstream-rtk-reference-20260920.json --comparison docs/evidence/upstream-rtk-comparison-20260920.json
```
