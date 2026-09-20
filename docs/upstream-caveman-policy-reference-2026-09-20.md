# 固定 Caveman 策略契约（2026-09-20）

本轮对固定提交 `542442bab314973709f95b85b1ac0b3f6f5b5dc6` 的 Caveman skill 源文件进行离线核对。生成器校验 checkout HEAD，记录源文件 SHA-256，再比较 UTK 的回答指令。运行时不调用 Caveman，也不调用模型。

核对结果：

- `lite`、`full`、`ultra`、`wenyan-lite`、`wenyan-full`、`wenyan-ultra` 六个启用档位均有独立 UTK 指令。
- `off` 返回空指令，不改变请求。
- 技术名词、代码块和错误原文保护通过。
- 否定、数字和单位保护通过。
- 回答语言保持通过。
- 安全警告与不可逆操作清晰度保护通过。
- 用户要求详细解释时优先满足通过。
- 禁止自造缩写与因果箭头通过。
- 压缩不得让回答更长的约束通过。

机器证据见 [upstream-caveman-policy-reference-20260920.json](evidence/upstream-caveman-policy-reference-20260920.json)。报告明确保留 `paired_output_quality_passed: false`：策略契约通过不能证明模型实际回答同时更短且正确，也不能生成“节省比例”。成对回答质量仍需固定模型、固定输入和显式预算的真实评测。

复现命令：

```sh
python scripts/generate-caveman-reference.py --checkout output/reference-caveman --output docs/evidence/upstream-caveman-policy-reference-20260920.json
```
