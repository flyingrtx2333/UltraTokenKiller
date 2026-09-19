# Compatibility matrix

Status labels distinguish implementation from live acceptance. “Implemented” means the adapter and restoration tests pass. “Live verified” requires a real client request through the declared route.

| Platform / client | Status | Evidence |
|---|---|---|
| Windows 10/11, Codex with ChatGPT login | Live verified | A real Codex Responses request used the UTK-equivalent temporary provider route and returned `UTK_OK`. Headroom recorded complete accounting for `gpt-6-astra`, 150,145 input tokens before compression, 148,237 after, 7 output tokens, and 1,908 tokens removed. The persistent configuration path is covered by parse and restoration tests. |
| Windows 10/11, Codex with API key | Implemented | Provider/base URL discovery and reversible managed configuration are tested; no paid API request was made during this build. |
| Windows 10/11, NousResearch Hermes Agent | Implemented, live verification pending | OpenAI-compatible provider routing and reversible YAML changes are tested. Hermes was not installed as a native command on the build host. |
| macOS 12+, Codex/Hermes | Implemented, platform verification pending | LaunchAgent and platform-specific RTK asset selection are included. |
| Linux with user systemd, Codex/Hermes | Implemented, platform verification pending | User service and x86_64/aarch64 RTK asset selection are included. |

Anthropic, Bedrock, and Vertex Hermes providers are detected and left unchanged because the first release only configures OpenAI-compatible Hermes model routes. Unknown providers without an explicit `base_url` are also left unchanged.
