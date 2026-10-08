# Tickets

Every step from an empty repo to final figures, extensions included. Work that does not fit this semester moves to next semester.

## How to work

- **Tags:** `<build>` covers anything from downloading data to implementing code. `<think>` is only for decisions the team makes together; write the decision at the bottom of the ticket under `## Decision`.
- **Order:** take the lowest-numbered ticket whose blockers are all done. Do one ticket at a time, and confirm it before starting.
- **Status:** `ready-for-agent` / `ready-for-team` → `doing` → `done`. Tick the boxes as you go.
- **Simplest first:** the smallest code that meets the ticket. Tickets after a `<think>` ticket get refined when that decision is made.
- **Code rules:** see `CLAUDE.md`.

## Folder structure

Built for VS Code on a Mac: every file runs with the play button. Files appear only when a ticket needs them; the right column says which ticket adds or fills each one.

```
settings.py                     project settings + setup (folders, models, port; builds .venv, downloads models)  01 ✓
setup/
  start_ollama_server.py        starts this project's Ollama server (port 11500, models from models/)            01 ✓
  stop_ollama_server.py         stops only that server                                                          01 ✓
tests/                          tests in pipeline order
  test_1_settings.py            the setup                                                                       01 ✓
data.py                         one loader per dataset, all returning the same Trajectory      exists empty;    02
run.py                          runs one scenario; --check is a quick check that logs nothing  exists empty;    02, 04
models.py                       call(): the only way to ask a model; counts calls and tokens                    03
score.py                        compares a predicted step with the Decisive step                                04
run_log.py                      writes each run to runs/<scenario>/<start time>/                                04
methods/                        one file per method, all with the same shape
  prover_estimator_debate.py                                                                                    04
  standard_debate.py                                                                                            06
  all_at_once.py                                                                                                07
  binary_search.py                                                                                              08
  single_critique.py                                                                                            08

Not in git (created on your machine):
.venv/                          the project's Python 3.12                                                        01 ✓
.cache/pip/                     pip's download cache                                                            01 ✓
models/                         the Ollama models (about 9.2 GB)                                                01 ✓
runs/                           run logs                                                                        04
```

Setup steps for a fresh clone are in the main [README](../README.md).

## Tickets

| # | Ticket | Tag | Blocked by |
|---|---|---|---|
| 01 | [Environment inside the repo](01-environment-inside-the-repo.md) ✅ | build | none |
| 02 | [Load Who&When and read it](02-load-who-and-when.md) | build | 01 |
| 03 | [Count every model call](03-count-every-model-call.md) | build | 01 |
| 04 | [Prover-estimator debate end to end](04-prover-estimator-debate-end-to-end.md) | build | 02, 03 |
| 05 | [Review the first version](05-review-the-first-version.md) | think | 04 |
| 06 | [Standard debate](06-standard-debate.md) | build | 05 |
| 07 | [All-at-once, with matched calls](07-all-at-once-with-matched-calls.md) | build | 06 |
| 08 | [Binary search and single critique, with matched calls](08-binary-search-and-single-critique.md) | build | 07 |
| 09 | [MP-Bench overlap and multi-expert scoring](09-mp-bench-overlap-and-scoring.md) | build | 02 |
| 10 | [Choose the test set and the hit rule](10-choose-test-set-and-hit-rule.md) | think | 09 |
| 11 | [Same pipeline on Kaggle](11-same-pipeline-on-kaggle.md) | build | 04 |
| 12 | [Development datasets and prompt tuning](12-development-datasets-and-prompt-tuning.md) | build | 08, 11 |
| 13 | [Freeze prompts and set the schedule](13-freeze-prompts-and-set-schedule.md) | think | 12 |
| 14 | [Main experiment](14-main-experiment.md) | build | 10, 13 |
| 15 | [Unfamiliar-task test and different-model test](15-unfamiliar-task-and-different-model.md) | build | 13 |
| 16 | [Design the human-time measurement](16-design-human-time-measurement.md) | think | 05 |
| 17 | [Author pilot and Review-minutes curves](17-author-pilot-and-review-minutes.md) | build | 14, 16 |
| 18 | [Failure analysis](18-failure-analysis.md) | build | 14 |
| 19 | [What did we find?](19-what-did-we-find.md) | think | 17, 18 |
| 20 | [Final figures and tables](20-final-figures-and-tables.md) | build | 19 |
| 21 | [Fine-tuned debaters](21-fine-tuned-debaters.md) | build | 13 |
| 22 | [Debate at a Checkpoint](22-debate-at-a-checkpoint.md) | build | 15 |

**Can run in parallel:** 02 and 03; 09 and 11 alongside 05–08; 16 alongside 06–15; 21 and 15 after 13.
