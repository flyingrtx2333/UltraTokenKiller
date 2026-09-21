# RTK Git 命令固定上游对照（2026-09-21）

固定上游：RTK `0924356b4caba4989607227b7c8824d3d8098719`。

本批把原有共用 `git-action` 拆为 `status`、`log`、`diff`、`add`、`commit`、`push`、`pull`、`fetch`、`checkout`、`switch`、`branch`、`stash` 和 `worktree` 契约。机器格式、用户指定的统计/单行/word-diff 形态和外部 diff 继续透传；失败和无法确认的输出不压缩。

固定 RTK 二进制在临时 Git 仓库上执行只读的 `status` 与 `log`。仓库、作者和提交时间均由生成器固定，不读取用户仓库。修改性命令的 UTK 过滤器使用捕获输出单元测试，不为了统计再次提交、拉取或推送。

| 场景 | 固定 RTK 压缩率 | UTK 压缩率 | 相对比例 | 关键事实 |
|---|---:|---:|---:|---|
| `git status` 工作区 | 88.5% | 87.5% | 98.8% | 通过 |
| `git log` 默认格式 | 61.4% | 65.4% | 106.4% | 通过 |
| `git diff` 多文件 | 34.6% | 54.1% | 156.3% | 通过 |

上述三项只是 Windows 固定上游成功形态证据，不含失败、未知格式及 macOS/Linux 固定二进制变体，因此不会提升为完整上游对标通过。写操作现已具备逐命令路由、成功/失败/未知格式离线测试，但仍待固定上游捕获输出逐项对照。

证据文件：

- `docs/evidence/upstream-rtk-reference-20260920.json`
- `docs/evidence/upstream-rtk-comparison-20260920.json`
- `tests/test_rtk_git.py`
