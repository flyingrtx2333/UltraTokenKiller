# 固定上游输入层对照（2026-09-20）

本轮首次把 `utk benchmark --mode upstream` 从手工占位数据接到可复现的固定上游执行器。

- Headroom：`bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`
- RTK：`0924356b4caba4989607227b7c8824d3d8098719`
- Caveman：`542442bab314973709f95b85b1ac0b3f6f5b5dc6`
- Headroom wheel：由上述 checkout 在 Windows x64 本地构建，版本 `0.37.0`；结果包记录 Python 模块和原生扩展 SHA-256。
- 模型调用：0。

执行器先检查三份 checkout 的精确 HEAD，再用隔离 Python 运行 Headroom。输入均为仓库内的 12 个固定合成样例，不读取用户提示词、回答或凭据。原始输出包见 [upstream-input-reference-20260920.json](evidence/upstream-input-reference-20260920.json)，不含正文的计数报告见 [upstream-input-report-20260920.json](evidence/upstream-input-report-20260920.json)。

固定上游在 12 个样例中全部保留必需事实，中位压缩率为 82.26%。建立对照后，UTK 已针对重复长文本、TypeScript 签名查询、搜索结果、补丁及异常堆栈补齐确定性规则；当前 11/12 个样例达到“事实保留且压缩率至少为上游 90%”的逐样例门槛，详见 [upstream-input-comparison-20260920.json](evidence/upstream-input-comparison-20260920.json)。剩余 `unknown-format` 是 UTK 的低置信度透传样例，而固定 Headroom 将其识别为表格并压缩；在没有更强结构证据前仍保留透传，不能把这一项标为上游对标通过。这份结果不将个别样例通过等同于某一整类能力完成。

当前结果包的覆盖为 Headroom 12、RTK 0、Caveman 0。RTK 需要独立的捕获输出套件，Caveman 需要成对回答套件；校验了两个 checkout 不代表执行了它们的对照。因此 `parity_certified` 继续为 `false`，能力清单状态不提升为“上游对标通过”。

复现命令：

```sh
python scripts/generate-reference.py --headroom output/reference-headroom --rtk output/reference-rtk --caveman output/reference-caveman --output reference-results.json --python output/reference-headroom/.venv/Scripts/python.exe
utk benchmark --mode upstream --reference reference-results.json --model gpt-5.6-luna
utk benchmark --mode matrix --reference reference-results.json --model gpt-5.6-luna
```

`matrix` 将透传、冻结基础版、固定上游和当前 UTK 按样例哈希对齐，并分别记录事实保持、恢复、token 估算方法、耗时和峰值内存。缺少或不匹配的固定上游结果会令报告保持 `incomplete`，不会以当前 UTK 输出替代上游结果。
