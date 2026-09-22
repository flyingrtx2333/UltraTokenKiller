<picture>
  <source media="(prefers-color-scheme: dark)" srcset="web/public/brand/utk-lockup.svg">
  <img src="web/public/brand/utk-lockup-light.svg" alt="UltraTokenKiller" width="430">
</picture>

# UltraTokenKiller

让 AI 编程助手少读重复内容，少花 Token。

UTK 在本机运行，可以接入 Codex 和 Hermes Agent。它会缩短冗长的命令输出、整理发给模型的部分历史内容，也可以让模型回答更简洁。你仍然使用自己的模型和账号。

## 能帮你做什么

- **缩短命令输出**：把一长串测试、日志和搜索结果整理成摘要，让 AI 更快看到结果和错误。
- **减少重复上下文**：压缩适合处理的历史工具结果，减少后续请求携带的内容。
- **让回答更简洁**：按需开启，减少重复解释和铺垫。
- **查看使用情况**：在本地控制台查看请求记录、Token 用量和压缩效果。

压缩效果取决于任务和内容。重复日志通常更容易缩短；无法识别的命令和输出会保留原样。支持范围见 [兼容说明](COMPATIBILITY.md)。

## 安装

需要 Python 3.10 或更高版本，推荐 3.11。下载项目后，在项目目录打开终端。

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

macOS / Linux：

```sh
sh ./scripts/install.sh
```

安装后检查服务，并打开控制台：

```sh
utk doctor
utk web
```

控制台用于接入客户端、调整压缩强度和查看记录。安装遇到问题时，先看 `utk doctor` 的检查结果。

## 开始使用

### Codex

在项目目录启动一个带 UTK 的 Codex 会话：

```sh
utk codex
```

也可以通过 `--model <模型名称>` 指定模型。这个入口为新会话接上压缩和原文查询功能。支持的 Codex 版本见 [接入说明](docs/codex-auto-session-2026-09-19.md)。

### Hermes Agent

先确保 Hermes 本身能正常对话，再执行：

```sh
utk enable hermes
```

重新启动 Hermes 后使用。UTK 会配置本地代理，并安装用于处理终端命令的插件。取消接入使用 `utk disable hermes`。

### 手动运行命令

也可以在命令前加上 `utk exec --`：

```sh
utk exec -- git status
utk exec -- python -m pytest -v
```

部分压缩需要正在运行的 UTK 服务和会话；条件不满足时会返回原文。手动执行成功不一定表示发生了压缩，可以到控制台查看记录。

## 怎么看有没有生效

先接入客户端，再让它执行一次任务，然后打开 `utk web`：

- **请求记录**：确认模型请求经过了 UTK。
- **工具记录**：确认命令是否经过压缩，以及缩短了多少。
- **Token 用量**：模型服务返回用量后才会显示；没有返回时显示“未知”。

服务显示“运行中”，只说明服务或功能已开启。请求数为 0、没有活动记录时，还不能据此判断压缩效果。

控制台里的压缩估算用于了解内容减少了多少，实际费用以模型服务商账单为准。

每条工具记录会显示压缩前后的输出大小；“已压缩 / 工具命令”表示命令数量，不是压缩率。活动里的“上游 400/404”是 Hermes 与兼容接口协商或回退请求，不等于最终任务失败；“命令失败”表示命令本身返回了非零退出码。

![UTK 公网控制台实时数据](docs/assets/utk-dashboard-live.png)

## 常用设置

使用稳妥压缩，并让回答稍微简洁一些：

```sh
utk profile safe --caveman lite
```

关闭输入压缩和回答精简：

```sh
utk profile off --caveman off
```

查看、启动或停止本地服务：

```sh
utk status
utk start
utk stop
```

## 数据保存在哪里

统计保存在本机，不记录提示词、回答正文或凭据。为支持找回原文，压缩前的内容会临时保存在内存中；过期或服务重启后就无法找回。

### 在服务器上查看

默认只允许本机访问。需要公开统计时，在 UTK 的 `config.json` 中设置 `"dashboard_host": "0.0.0.0"`，重启 UTK，并在服务器防火墙中放行控制台端口。

公网地址只展示统计，不能修改设置、接入客户端或读取原文。管理服务器上的 UTK，请使用 SSH 转发后访问本机地址。模型代理端口仍只监听本机，无需对外开放。

## 开发文档

- [兼容说明](COMPATIBILITY.md)
- [开发记录与测试命令](docs/development-notes.md)
- [功能对照清单](docs/full-capability-parity-2026-09-21.md)

## 许可

UTK 使用 Apache-2.0。第三方声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
