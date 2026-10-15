# 04: Prover-estimator debate end to end

**Tag:** `<build>`
**Blocked by:** 02, 03
**Status:** ready-for-agent

**What to build:** the first method and the whole pipeline around it, run first on the pilot run (run 36, from `data/splits/pilot.json`). Every file runs with the play button.

**Where things go** (agreed with the owner, 2026-10-08):
- `methods/prover_estimator_debate.py`: the debate itself. The file maps each role to its model and system prompt at the top (prover and estimator: `settings.DEBATER_MODEL`; judge: `settings.JUDGE_MODEL`). The debate gets the Trajectory, `ask_model` and the `log` list as inputs; it asks the models only through `ask_model()`, adds a note to the log each round, and returns its predicted step. Its main section runs `run_prover_estimator_debate("36.json")` (importing from `run.py` **inside** the main section, with a comment saying why: `run.py` also imports this file).
- `run.py`: `run_prover_estimator_debate(json_file)` loads that Trajectory with `data.py`, runs the debate, scores the answer, writes the question's log with `write_log()`, and adds a line to `results.jsonl` (fill in the `write_results_file()` skeleton). Pressing play on `run.py` runs the pilot; one visible line switches to the test split (all 58 runs).

**Rules:** follow section 1 of `informatics.md` (how we differ from the paper, 15 rules, and decisions A–E still open). Settle A–E before building.

**Method (simplest version):** each round splits the current range of steps at the midpoint. The prover argues which half has the error; the estimator gives the probability that each half has the error; the First-error rule picks the next half. When one step is left, the judge checks it. Prompts are short.

**Logs:** `runs/prover_estimator_debate/<start time>/` holds one `run_<number>.md` per question (1 for the pilot, 58 for the test split) and one `results.jsonl`. Each log shows each role's system prompt at the top, then every prompt and reply in order, with the debate's notes, then the result.

- [ ] Each round's note shows: range of steps, both probabilities, chosen half.
- [ ] The log and `results.jsonl` hold: predicted step, hit (exact and within ±2), calls, tokens.
- [ ] The run prints the hit rate and the average calls.
- [ ] Tests with a fake `ask_model` (no server needed): the halving, the First-error rule, and the final step; tests write nothing to `runs/`.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every file runs with the play button.

*Changed 2026-10-08: the earlier "time yourselves checking 5 cases" box moved to the human review set in ticket 02.*
