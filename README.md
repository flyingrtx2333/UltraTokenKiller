# UltraTokenKiller

UltraTokenKiller (`utk`) combines three independent token controls behind one local control plane:

- Headroom compresses eligible model input while preserving a cache-first default.
- RTK filters supported command output before it enters agent context.
- Caveman instructions ask the model for concise answers without truncating generated text.

The terminal dashboard and local web console report these layers separately. They never add Headroom estimates and RTK output savings together as billing savings. Prompt and response bodies are not stored.

When Codex and Hermes use different upstream providers, UTK starts one Headroom instance per upstream. Clients sharing the same upstream share an instance. This prevents a ChatGPT subscription route from being sent to an API-key endpoint, or vice versa.

## Install from this checkout

Python 3.10 or newer is supported. Python 3.11 is recommended.

One-click Windows install creates an isolated environment, installs verified dependencies, configures detected clients, and registers user logon startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

macOS and Linux:

```sh
sh ./scripts/install.sh
```

For a development install without the isolated environment:

```powershell
python -m pip install -e .
utk install
```

On macOS or Linux:

```sh
python3 -m pip install -e .
utk install
```

Open the web console with `utk web`, or run the terminal dashboard with `utk dashboard`. Use `utk doctor` to distinguish an installed dependency from a working client route.

Run a command through RTK with:

```sh
utk exec -- git status
```

`utk install` backs up client configuration before adding a marked managed block. `utk disable codex`, `utk disable hermes`, and `utk uninstall` remove only that block.

## Supported clients

| Client | Supported path | Notes |
|---|---|---|
| Codex | Responses API, API key or ChatGPT login | Uses user-level `config.toml`; credentials stay with Codex. |
| NousResearch Hermes Agent | OpenAI-compatible providers | Providers using Anthropic, Bedrock, or Vertex protocols are detected but not automatically changed. |

See [COMPATIBILITY.md](COMPATIBILITY.md) for the distinction between implemented adapters and live-verified combinations.

Windows and WSL are separate installations and configurations. macOS uses a LaunchAgent, Linux uses user-level systemd when present, and Windows uses a per-user logon task.

## Development

```sh
python -m pip install -e ".[test]"
python -m pytest
cd web && npm install && npm run build
```

The frontend build is copied into `src/ultratokenkiller/static` before packaging.

## Security and privacy

All listeners bind to `127.0.0.1`. State-changing web requests require a random local session token and validate the browser origin. SQLite contains request metadata only. Authentication tokens and message bodies remain in the original clients and Headroom process.

## Licenses

UltraTokenKiller is Apache-2.0. It integrates, but does not relicense, third-party projects. Headroom and RTK are Apache-2.0. The bundled concise-response instruction is derived from the MIT-licensed Caveman skill text and does not include Caveman's BSL engine directories. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
