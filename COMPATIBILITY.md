# 原生引擎兼容性

本表适用于当前原生实现。旧集成版的 Headroom/RTK 验证结果不能用于证明原生实现。

| 路径 | 当前证据 | 状态 |
|---|---|---|
| Responses HTTP/SSE | MockTransport 检查认证头、订阅路由、完整 SSE 字节、usage、429、异常回退 | 本地测试通过；真实 Codex 未验证 |
| Chat Completions | 原生转发和历史 tool 消息压缩已实现 | 真实 Hermes 未验证 |
| WebSocket | 暂未实现；Codex 配置声明关闭 | 不支持 |
| 多模态 | 请求对象内非工具内容保留测试 | 真实多模态未验证 |
| Git status/stat、普通 rg/grep/pytest | 原生输出规则、透传和退出码测试 | 保守能力，非 RTK 全命令覆盖 |
| 回答 lite/full/ultra/off | 原生请求指令控制 | 不提供未经对照的节省比例 |
| Windows / macOS / Linux | 保留安装、自启实现 | 原生版三平台干净安装和登录验收待完成 |

缺失能力：语义输入压缩、复杂测试报告/搜索结果压缩、WebSocket、跨平台进程树取消、真实客户端关联验收。当前不标记为正式首版发布。
