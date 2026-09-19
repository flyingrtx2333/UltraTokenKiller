# UltraTokenKiller

UTK 是本地原生 Token 优化工具。输入压缩、工具输出压缩、回答精简由 UTK 自己实现，不安装或调用 Headroom、RTK、Caveman。普通 Python/Web 框架依赖仍由安装器安装。

## 当前原生能力

- 输入：处理 Responses API 和 OpenAI Chat Completions 历史工具结果中的连续重复行。保留系统/用户指令、多模态数据、工具调用 ID 和最新工具结果；JSON、补丁和代码块透传。压缩异常时转发原始请求。
- 工具：`utk exec -- git status` 去除已知 Git 英文操作提示，保留文件和状态；Git stat、普通 rg/grep/pytest 输出折叠连续重复行。错误输出、非 UTF-8、未知命令和机器格式透传。保留退出码、工作目录与参数，不使用 shell 重写。
- 回答：UTK 自有 lite/full/ultra 指令，在请求时应用；off 不附加精简指令，不截断生成结果。
- 代理：直连指定原始上游；HTTP/SSE、认证头、错误状态透传，不自动重试。每个上游使用独立本地端口。
- 看板：`utk dashboard` 和 `utk web` 展示同一 SQLite 元数据，不保存模型输入、回答正文或凭据。工具输出压缩使用临时文件，命令结束后关闭删除。

这是原生引擎的首个保守实现，并非三个参考项目的等价复刻。语义压缩、搜索结果相关性排序、复杂测试报告解析、WebSocket 和原生引擎真实客户端验收尚未完成。HTTP/SSE 单元测试不能替代 Codex/Hermes 真机验收。当前适配器关闭 Codex WebSocket 声明。

## 安装

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

原生输入/回答档位按请求读取，不需要重启客户端代理。Git/测试输出在命令结束后显示，支持命令的 stdout 使用磁盘临时文件；大于 8 MiB 时原样分块输出。取消当前子进程已处理，跨平台进程树取消尚待验证。

## 统计口径

提供商 usage 单独记录实际输入、输出和缓存 token；缺失值显示未知。压缩量是 UTF-8 字节数除以 4 的粗略估算，不等同模型 tokenizer 或账单节省。输入压缩与工具输出估算不相加为账单节省，不宣称订阅现金节省。回答精简只展示状态和实际输出量，不宣称未经对照测试的减少比例。

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
