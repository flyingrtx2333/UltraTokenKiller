# README visual assets

| File | Source | Viewport | Data |
|---|---|---:|---|
| `dashboard-desktop-empty.png` | Packaged UTK dashboard served by the local FastAPI app | 1440 x 1100 | Real empty state from an isolated `UTK_HOME`; no prompts, responses, credentials, or user metrics |
| `dashboard-mobile-empty.png` | Same packaged dashboard | 390 x 844 | Real empty state from the same isolated service |
| `dashboard-macos-arm64-desktop.png` | Packaged UTK dashboard on macOS 26.6.2 arm64 | 1440 x 1100 | Real empty state; Codex 0.153.4 and Hermes 0.21.0 detected without enabling either client |
| `dashboard-macos-arm64-mobile.png` | Same macOS packaged dashboard | 390 x 844 | Real empty state from the same isolated service |
| `terminal-dashboard.svg` | UTK Textual dashboard in an isolated terminal | 120 columns x 45 rows | Real empty state; no user data |

The screenshots are acceptance artifacts, not design mockups. Regenerate them
after material dashboard changes and update the environment/date note in the
main README.
