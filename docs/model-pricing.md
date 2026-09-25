# 配置模型费用估算

UTK 不会猜自定义模型的价格。配置后，看板才会显示按服务商用量计算的费用估算；它不是账单。

编辑 UTK 的 `config.json`，加入 `model_pricing`。Windows 默认位置是 `%LOCALAPPDATA%\UltraTokenKiller\config.json`；macOS/Linux 默认位置是 `~/.local/state/utk/config.json`。键写成“客户端名/模型名”，两者都要与活动记录一致；单价按每 100 万 Token 填写。

```json
"model_pricing": {
  "hermes/准确的模型名": {
    "currency": "USD",
    "input_per_million": 1.0,
    "output_per_million": 2.0,
    "cache_mode": "unknown",
    "source": "服务商价格页面",
    "checked_on": "2026-09-23"
  }
}
```

上面的数字只是格式示例，必须替换成服务商公布的单价。Codex 的键以 `codex/` 开头。若同一客户端改接了不同服务商，要同步更新价格表。`cache_mode` 填 `none` 表示确认该模型不使用缓存计费；填 `priced` 时还要填写 `cached_input_per_million`，并确保服务商会返回缓存 Token 数；无法确认时填 `unknown`，UTK 会隐藏费用估算。改完后重启 UTK。

输入费差额只在确认无缓存计费时估算。修改价格表不会重算旧记录；旧记录缺少请求当时的价格快照时，显示为未记录。
