# RTK Git 命令固定上游对照（2026-09-21）

固定上游：RTK `0924356b4caba4989607227b7c8824d3d8098719`。

本批把原有共用 `git-action` 拆为 `status`、`log`、`diff`、`add`、`commit`、`push`、`pull`、`fetch`、`checkout`、`switch`、`branch`、`stash` 和 `worktree` 契约。机器格式、用户指定的统计/单行/word-diff 形态和外部 diff 继续透传；失败和无法确认的输出不压缩。

固定 RTK 二进制在临时 Git 仓库上执行只读的 `status` 与 `log`。仓库、作者和提交时间均由生成器固定，不读取用户仓库。修改性命令的 UTK 过滤器使用捕获输出单元测试，不为了统计再次提交、拉取或推送。

| 场景 | 固定 RTK 压缩率 | UTK 压缩率 | 相对比例 | 关键事实 |
|---|---:|---:|---:|---|
| `git status` 工作区 | 88.5% | 87.5% | 98.8% | 通过 |
| `git log` 默认格式 | 61.4% | 65.4% | 106.4% | 通过 |
| `git diff` 多文件 | 34.6% | 54.1% | 156.3% | 通过 |
| `git commit` 成功 | 80.5% | 78.0% | 97.0% | 通过 |
| `git pull` 成功 | 80.0% | 77.5% | 96.9% | 通过 |
| `git checkout` 成功 | 36.4% | 36.4% | 100.0% | 通过 |
| `git push` 成功 | 77.8% | 77.8% | 100.0% | 通过 |
| `git fetch` 成功 | 70.8% | 70.8% | 100.0% | 通过 |
| `git show` 提交补丁 | 64.4% | 65.3% | 101.3% | 通过 |
| `git branch` 列表 | 51.4% | 48.6% | 94.4% | 通过 |
| `git stash show` | 38.9% | 38.9% | 100.0% | 通过 |
| `git worktree list` | 6.1% | 6.1% | 100.0% | 通过 |

`status`、`log`、`diff`、`show` 当前只有 Windows 固定上游成功形态；`commit`、`pull`、`checkout`、`push`、`fetch`、`branch`、`stash`、`worktree` 已增加成功与失败捕获输出，失败内容中的路径和阻断原因均保留。所有项目仍缺未知格式及 macOS/Linux 固定二进制变体，因此不会提升为完整上游对标通过。`add` 已在一次成功执行后使用只读 `git diff --cached --stat --shortstat` 生成暂存统计，不会重复执行写操作；固定上游执行级对照仍待补充。

`utk exec` 现使用总内存上限约束的双通道捕获器，stdout 与 stderr 分开保存、压缩并写回原通道。容量超限时两个通道一起切换为流式透传，避免只压缩 stdout 而漏掉 Git `push`、`fetch`、`worktree` 的 stderr 输出。该能力已有通道、退出码、二进制与容量回退测试；真实客户端采用证据仍需后续重新绑定。

包含 `git add` staged stat 探针的提交 `7c3a11b` 在 Mac arm64 的独立 `/tmp` 工作区完成全量离线回归：`292 passed, 1 skipped, 2 warnings`。该运行未执行固定 RTK 二进制，因而只证明 UTK 跨平台回归，不补充上游变体证据。

证据文件：

- `docs/evidence/upstream-rtk-reference-20260920.json`
- `docs/evidence/upstream-rtk-comparison-20260920.json`
- `docs/evidence/macos-rtk-git-20260921.json`
- `tests/test_rtk_git.py`

## `git add` 固定 RTK 执行证据

- 固定提交：`0924356b4caba4989607227b7c8824d3d8098719`，RTK `0.48.0`。
- macOS arm64 二进制在隔离 `/tmp` 工具链编译，SHA-256：`82de051972beb180a5ac5dec0f6a235284b1ba62fb271c9e83b8bcf76520692f`。
- 修改性命令只执行一次：`rtk git add tracked.txt`；退出码为 0，暂存文件为 `tracked.txt`，固定 RTK 输出保留 `1 file changed, 1 insertion(+)`。
- 四路对照使用同一份暂存统计输入，未为了统计再次执行 `git add`。
- 机器证据：`docs/evidence/macos-rtk-git-add-20260921.json`。

## 未知格式与机器格式

- 固定 RTK 的 13 个 Git 命令族及 UTK 的 17 个细分过滤器均验证未知输出原样透传。
- `--porcelain`、`--format`、`--numstat` 等 7 组机器格式在命令识别阶段直接绕过，不进入文本压缩。
- 这些结果只计为安全回退证据，不计为压缩支持；机器证据见 `docs/evidence/rtk-git-shape-matrix-20260921.json`。
