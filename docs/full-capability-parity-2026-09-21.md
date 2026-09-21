# UTK fixed-version full capability parity inventory

Generated from machine-readable upstream evidence. Implementation status and fixed-upstream parity status are separate; passthrough never counts as parity.

## Denominator

| Upstream | Core items | Implementation states | Parity states |
|---|---:|---|---|
| Headroom | 24 | {'offline_passed': 21, 'real_client_passed': 3} | {'fixed_upstream_sample_passed': 9, 'fixed_upstream_suite_passed': 1, 'not_individually_compared': 14} |
| Rtk | 211 | {'contract_mapped': 70, 'unverified': 141} | {'fixed_upstream_behavior_suite_windows': 2, 'fixed_upstream_success_failure_windows': 27, 'fixed_upstream_success_only': 13, 'pending_fixed_upstream_variant_evidence': 169} |
| Caveman | 21 | {'implemented_unverified': 5, 'real_client_passed': 16} | {'authorization_required': 5, 'fixed_upstream_policy_passed': 14, 'offline_passed': 2} |

Total core denominator: **256**

## Items

| ID | Category | Capability | Implementation | Fixed-upstream parity | Gap |
|---|---|---|---|---|---|
| `headroom.input.routing` | input | `input.routing` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.json` | input | `input.json` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.table` | input | `input.table` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.logs` | input | `input.logs` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.code.python` | input | `input.code.python` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.code.multilanguage` | input | `input.code.multilanguage` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.diff` | input | `input.diff` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.search` | input | `input.search` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.long_text_en` | input | `input.long_text_en` | offline_passed | fixed_upstream_sample_passed | — |
| `headroom.input.long_text_zh` | input | `input.long_text_zh` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.input.image` | input | `input.image` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.recovery.memory` | recovery | `recovery.memory` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.recovery.mcp` | recovery | `recovery.mcp` | real_client_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.cache.stable_prefix` | recovery | `cache.stable_prefix` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.protocol.responses_http_sse` | protocol | `protocol.responses_http_sse` | real_client_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.protocol.chat_completions` | protocol | `protocol.chat_completions` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.protocol.anthropic_messages` | protocol | `protocol.anthropic_messages` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.protocol.responses_websocket` | protocol | `protocol.responses_websocket` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.benchmark.fixed_upstream` | benchmark | `benchmark.fixed_upstream` | offline_passed | fixed_upstream_suite_passed | — |
| `headroom.client.codex_subscription` | client | `client.codex_subscription` | real_client_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.client.codex_api_key` | client | `client.codex_api_key` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.dashboard.metrics` | dashboard | `dashboard.metrics` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.install.windows` | distribution | `install.windows` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `headroom.install.macos_linux` | distribution | `install.macos_linux` | offline_passed | not_individually_compared | Needs a fixed-upstream item-level comparison |
| `rtk.tools.BunCommands.Add` | javascript | `bun add` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunCommands.Build` | javascript | `bun build` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunCommands.Install` | javascript | `bun install` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunCommands.Other` | javascript | `bun other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunCommands.Pm` | javascript | `bun pm` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunCommands.Remove` | javascript | `bun remove` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunCommands.Run` | javascript | `bun run` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunCommands.Test` | javascript | `bun test` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.BunCommands.X` | javascript | `bun x` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunPmCommands.Ls` | javascript | `bun pm ls` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.BunPmCommands.Other` | javascript | `bun pm other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommand.Build` | rust | `cargo build` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommand.Check` | rust | `cargo check` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommand.Clippy` | rust | `cargo clippy` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommand.Install` | rust | `cargo install` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommand.Nextest` | rust | `cargo nextest` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommand.Test` | rust | `cargo test` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.CargoCommands.Build` | rust | `cargo build` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommands.Check` | rust | `cargo check` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommands.Clippy` | rust | `cargo clippy` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommands.Install` | rust | `cargo install` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommands.Nextest` | rust | `cargo nextest` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommands.Other` | rust | `cargo other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.CargoCommands.Test` | rust | `cargo test` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.AstGrep` | general | `ast-grep` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Aws` | cloud_infrastructure | `aws` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Bun` | javascript | `bun` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Bunx` | general | `bunx` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Cargo` | rust | `cargo` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.CcEconomics` | general | `cc-economics` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Config` | general | `config` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Ctest` | general | `ctest` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Curl` | general | `curl` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Deno` | javascript | `deno` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Deps` | general | `deps` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Diff` | general | `diff` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Discover` | general | `discover` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Docker` | cloud_infrastructure | `docker` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Dotnet` | dotnet | `dotnet` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Ecs` | general | `ecs` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Env` | general | `env` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Err` | general | `err` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Find` | file_search | `find` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.Commands.Format` | general | `format` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Gain` | general | `gain` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Gh` | git | `gh` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.Commands.Git` | git | `git` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Glab` | git | `glab` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.Commands.Go` | go | `go` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.GolangciLint` | general | `golangci-lint` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Gradlew` | general | `gradlew` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Grep` | file_search | `grep` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.Commands.Gt` | git | `gt` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.Commands.Hook` | general | `hook` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.HookAudit` | general | `hook-audit` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Init` | general | `init` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Jest` | javascript | `jest` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Json` | file_search | `json` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.Commands.Kubectl` | cloud_infrastructure | `kubectl` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Learn` | general | `learn` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Lint` | general | `lint` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Log` | general | `log` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Ls` | file_search | `ls` | contract_mapped | fixed_upstream_behavior_suite_windows | Fixed-upstream success, failure and unknown-format samples passed on Windows; macOS and Linux evidence remain |
| `rtk.tools.Commands.Mvn` | jvm | `mvn` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Mvnd` | general | `mvnd` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Mypy` | python | `mypy` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Next` | general | `next` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Npm` | javascript | `npm` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Npx` | javascript | `npx` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Oc` | cloud_infrastructure | `oc` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Paratest` | general | `paratest` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Pest` | general | `pest` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Php` | general | `php` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Phpstan` | general | `phpstan` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Phpt` | general | `phpt` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Phpunit` | general | `phpunit` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Pint` | general | `pint` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Pip` | python | `pip` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Pipe` | general | `pipe` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Playwright` | general | `playwright` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Pnpm` | javascript | `pnpm` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Prettier` | javascript | `prettier` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Prisma` | javascript | `prisma` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Proxy` | general | `proxy` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Psql` | data | `psql` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Pytest` | python | `pytest` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Rake` | general | `rake` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Read` | file_search | `read` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.Commands.Recall` | general | `recall` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Rewrite` | general | `rewrite` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Rg` | file_search | `rg` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.Commands.Rspec` | general | `rspec` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Rubocop` | general | `rubocop` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Ruff` | python | `ruff` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Run` | general | `run` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Sbt` | jvm | `sbt` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Session` | general | `session` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Smart` | file_search | `smart` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.Commands.Sqlfluff` | general | `sqlfluff` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Summary` | general | `summary` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Telemetry` | general | `telemetry` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Test` | general | `test` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Tree` | file_search | `tree` | contract_mapped | fixed_upstream_behavior_suite_windows | Fixed-upstream success, failure and unknown-format samples passed on Windows; macOS and Linux evidence remain |
| `rtk.tools.Commands.Trust` | general | `trust` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Tsc` | javascript | `tsc` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Untrust` | general | `untrust` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Uv` | python | `uv` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Verify` | general | `verify` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Vitest` | javascript | `vitest` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.Commands.Wc` | general | `wc` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.Commands.Wget` | general | `wget` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.ComposeCommands.Build` | cloud_infrastructure | `docker compose build` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.ComposeCommands.Logs` | cloud_infrastructure | `docker compose logs` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.ComposeCommands.Other` | cloud_infrastructure | `docker compose other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.ComposeCommands.Ps` | cloud_infrastructure | `docker compose ps` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Check` | javascript | `deno check` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Compile` | javascript | `deno compile` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Install` | javascript | `deno install` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Lint` | javascript | `deno lint` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Other` | javascript | `deno other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Run` | javascript | `deno run` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Task` | javascript | `deno task` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DenoCommands.Test` | javascript | `deno test` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.DockerCommands.Compose` | cloud_infrastructure | `docker compose` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DockerCommands.Images` | cloud_infrastructure | `docker images` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.DockerCommands.Logs` | cloud_infrastructure | `docker logs` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DockerCommands.Other` | cloud_infrastructure | `docker other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DockerCommands.Ps` | cloud_infrastructure | `docker ps` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.DotnetCommands.Build` | dotnet | `dotnet build` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DotnetCommands.Format` | dotnet | `dotnet format` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DotnetCommands.Other` | dotnet | `dotnet other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DotnetCommands.Restore` | dotnet | `dotnet restore` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.DotnetCommands.Test` | dotnet | `dotnet test` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.GitCommand.Add` | git | `git add` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.GitCommand.Branch` | git | `git branch` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommand.Checkout` | git | `git checkout` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommand.Commit` | git | `git commit` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommand.Diff` | git | `git diff` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommand.Fetch` | git | `git fetch` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommand.Log` | git | `git log` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommand.Pull` | git | `git pull` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommand.Push` | git | `git push` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommand.Show` | git | `git show` | unverified | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommand.Stash` | git | `git stash` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommand.Status` | git | `git status` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommand.Worktree` | git | `git worktree` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Add` | git | `git add` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.GitCommands.Branch` | git | `git branch` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Checkout` | git | `git checkout` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Commit` | git | `git commit` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Diff` | git | `git diff` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommands.Fetch` | git | `git fetch` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Log` | git | `git log` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommands.Other` | git | `git other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.GitCommands.Pull` | git | `git pull` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Push` | git | `git push` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Show` | git | `git show` | unverified | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommands.Stash` | git | `git stash` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GitCommands.Status` | git | `git status` | contract_mapped | fixed_upstream_success_only | Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain |
| `rtk.tools.GitCommands.Worktree` | git | `git worktree` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GoCommands.Build` | go | `go build` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.GoCommands.Other` | go | `go other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.GoCommands.Test` | go | `go test` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.GoCommands.Vet` | go | `go vet` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.GtCommands.Branch` | git | `gt branch` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GtCommands.Create` | git | `gt create` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GtCommands.Log` | git | `gt log` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GtCommands.Other` | git | `gt other` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GtCommands.Restack` | git | `gt restack` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GtCommands.Submit` | git | `gt submit` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.GtCommands.Sync` | git | `gt sync` | contract_mapped | fixed_upstream_success_failure_windows | Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain |
| `rtk.tools.HookCommands.Check` | general | `hook check` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Claude` | general | `hook claude` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Codex` | general | `hook codex` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Copilot` | general | `hook copilot` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Cursor` | general | `hook cursor` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Droid` | general | `hook droid` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Gemini` | general | `hook gemini` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Trae` | general | `hook trae` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.HookCommands.Vibe` | general | `hook vibe` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.KubectlCommands.Get` | cloud_infrastructure | `kubectl get` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.KubectlCommands.Logs` | cloud_infrastructure | `kubectl logs` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.KubectlCommands.Other` | cloud_infrastructure | `kubectl other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.KubectlCommands.Pods` | cloud_infrastructure | `kubectl pods` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.KubectlCommands.Services` | cloud_infrastructure | `kubectl services` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.OcCommands.Get` | cloud_infrastructure | `oc get` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `rtk.tools.OcCommands.Logs` | cloud_infrastructure | `oc logs` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.OcCommands.Other` | cloud_infrastructure | `oc other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.OcCommands.Pods` | cloud_infrastructure | `oc pods` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.OcCommands.Services` | cloud_infrastructure | `oc services` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommand.Install` | javascript | `pnpm install` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommand.List` | javascript | `pnpm list` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommand.Outdated` | javascript | `pnpm outdated` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommands.Install` | javascript | `pnpm install` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommands.List` | javascript | `pnpm list` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommands.Other` | javascript | `pnpm other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommands.Outdated` | javascript | `pnpm outdated` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PnpmCommands.Typecheck` | javascript | `pnpm typecheck` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaCommand.DbPush` | javascript | `prisma db-push` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaCommand.Generate` | javascript | `prisma generate` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaCommand.Migrate` | javascript | `prisma migrate` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaCommands.DbPush` | javascript | `prisma db-push` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaCommands.Generate` | javascript | `prisma generate` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaCommands.Migrate` | javascript | `prisma migrate` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaMigrateCommands.Deploy` | javascript | `prisma migrate deploy` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaMigrateCommands.Dev` | javascript | `prisma migrate dev` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.PrismaMigrateCommands.Status` | javascript | `prisma migrate status` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.SbtCommands.Compile` | jvm | `sbt compile` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.SbtCommands.Other` | jvm | `sbt other` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.SbtCommands.Run` | jvm | `sbt run` | unverified | pending_fixed_upstream_variant_evidence | Needs a dedicated contract plus success, failure and unknown-format evidence |
| `rtk.tools.SbtCommands.Test` | jvm | `sbt test` | contract_mapped | pending_fixed_upstream_variant_evidence | Mapped contract still needs success, failure and unknown-format fixed-upstream evidence |
| `caveman.mode.off` | mode | `off` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.mode.lite` | mode | `lite` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.mode.full` | mode | `full` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.mode.ultra` | mode | `ultra` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.mode.wenyan-lite` | mode | `wenyan-lite` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.mode.wenyan-full` | mode | `wenyan-full` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.mode.wenyan-ultra` | mode | `wenyan-ultra` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.rule.facts-and-errors` | rule | `facts-and-errors` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.rule.negations-and-numbers` | rule | `negations-and-numbers` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.rule.language-preservation` | rule | `language-preservation` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.rule.safety-clarity` | rule | `safety-clarity` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.rule.detail-override` | rule | `detail-override` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.rule.no-invented-abbreviations` | rule | `no-invented-abbreviations` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.rule.never-grow` | rule | `never-grow` | real_client_passed | fixed_upstream_policy_passed | — |
| `caveman.quality.technical-qa` | quality | `technical_qa` | implemented_unverified | authorization_required | Needs authorized paired model responses for every active mode and three repetitions |
| `caveman.quality.code-explanation` | quality | `code_explanation` | implemented_unverified | authorization_required | Needs authorized paired model responses for every active mode and three repetitions |
| `caveman.quality.code-review` | quality | `code_review` | implemented_unverified | authorization_required | Needs authorized paired model responses for every active mode and three repetitions |
| `caveman.quality.commit-message` | quality | `commit_message` | implemented_unverified | authorization_required | Needs authorized paired model responses for every active mode and three repetitions |
| `caveman.quality.task-summary` | quality | `task_summary` | implemented_unverified | authorization_required | Needs authorized paired model responses for every active mode and three repetitions |
| `caveman.bypass.json-schema` | structured_output | `json_schema` | real_client_passed | offline_passed | — |
| `caveman.bypass.tool-call` | structured_output | `tool_call` | real_client_passed | offline_passed | — |

## Explicit ecosystem exclusions

| ID | Upstream | Reason |
|---|---|---|
| `headroom.hosted-service` | headroom | Cloud accounts and hosted control plane are outside the single-user local core scope |
| `rtk.release-infrastructure` | rtk | Project CI, release automation and maintainer tooling are not runtime token-compression capabilities |
| `caveman.cloud-backend` | caveman | Cloud accounts, billing and team administration are outside the local core scope |
| `caveman.workflow-discovery` | caveman | Cross-workflow spend discovery is an ecosystem feature, not response compression |
| `caveman.experiment-management` | caveman | Remote experiment lifecycle management is outside the fixed response-policy core |
| `caveman.cost-analytics` | caveman | Hosted cost analytics is outside local response compression and quality evaluation |
