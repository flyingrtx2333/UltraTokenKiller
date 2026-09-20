# RTK command coverage denominator

Date: 2026-09-20
Reference commit: `0924356b4caba4989607227b7c8824d3d8098719`

## Result

The frozen RTK command inventory contains **211 command variants**. Every variant is part of the core coverage denominator. Nothing was excluded from the denominator in this pass.

| Evidence state | Count | Meaning |
|---|---:|---|
| `contract_mapped` | 55 | The variant maps to one or more of UTK's existing reviewed contracts. This is traceability only; it does not prove fixed-upstream parity. |
| `unverified` | 156 | The variant still needs a command-specific contract and success, failure, and unknown-format evidence on each applicable platform. |
| **Total denominator** | **211** | Frozen core variants discovered from the pinned RTK source. |

Unknown output that UTK passes through remains unverified. Passthrough does not count as compression support.

## Family breakdown

| Family | Variants | Suggested implementation batch |
|---|---:|---|
| File and search | 8 | 1. File reads, directory listing, find and structured search |
| Git | 38 | 2. Status, log, diff and write-operation results |
| General | 59 | 3 and 7. GitHub CLI, wrappers, statistics and uncovered-command discovery |
| Python | 5 | 4. Test and language tooling |
| JavaScript | 46 | 4 and 5. Test, build, lint, formatting and package managers |
| Rust | 14 | 4 and 5. Test, build, lint and formatting |
| Go | 5 | 4 and 5. Test, build and formatting |
| JVM | 6 | 4 and 5. Test and build tooling |
| .NET | 6 | 4 and 5. Test and build tooling |
| Cloud and infrastructure | 23 | 6. Docker, Kubernetes, OpenShift, AWS and infrastructure tools |
| Data | 1 | 6. Data tooling |

## Traceability contract

`src/ultratokenkiller/data/command-inventory.json` is the machine-readable source of truth. Each entry records:

- fixed upstream commit, source path, source line and source URL;
- resolved command path and parameter roles;
- expected output formats and applicable platforms;
- mapped UTK contract identifiers;
- disposition and current evidence state.

`scripts/finalize_command_inventory.py` regenerates the inventory from the pinned upstream checkout and UTK's reviewed contracts. `tests/test_command_inventory.py` enforces uniqueness, source traceability, nested parameter preservation, the 211-item denominator, and the public capability-report totals.

## Remaining work

The 55 mapped variants must still be checked against the frozen upstream behavior. The other 156 require dedicated contracts before implementation can be credited. Each final contract needs successful output, failed output, unknown-format fallback, platform scope, exit-code preservation, stdout/stderr behavior, working-directory and environment behavior, and cancellation evidence where applicable.

This inventory freezes the denominator. It does not change the preview release status or claim RTK feature parity.
