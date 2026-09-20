# Caveman paired response-quality evaluation

The frozen corpus is `src/ultratokenkiller/data/response-quality-corpus.json`. It covers technical Q&A, code explanation, code review, commit descriptions, and task summaries. Every scenario records facts that must survive compression, including paths, identifiers, numbers, negation, risk, conditions, and uncertainty.

All declared modes are included: `off`, `lite`, `full`, `ultra`, `wenyan-lite`, `wenyan-full`, and `wenyan-ultra`. JSON Schema and tool-call cases remain deterministic bypass checks and do not need model requests.

The release-quality paired run requires:

- 5 scenarios;
- 6 active compression modes;
- one baseline and one candidate response per pair;
- 3 repetitions;
- **180 model requests** in total.

The machine-readable calculation is `docs/evidence/response-quality-budget-20260920.json`. Its status remains `authorization_required`, with `live_model_calls: 0`. The historical three-request remainder is not used for this evaluation. `response.paired_quality` remains “implemented, unverified” until all paired responses pass both protected-fact correctness and length checks.
