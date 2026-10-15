# 07: All-at-once, with matched calls

**Tag:** `<build>`
**Blocked by:** 06
**Status:** ready-for-agent

**What to build:** The third method, plus the Matched-call baseline rule. One model reads the whole Trajectory and names the Decisive step. On each Trajectory it gets exactly as many calls as the Prover-estimator debate used there (read from that debate's `results.jsonl`), and the majority answer wins. The method lives in `methods/all_at_once.py`; `run.py` gets `run_all_at_once(json_file)`, with logs in `runs/all_at_once/<start time>/` in the same layout as 04.

- [ ] The log shows, per Trajectory, the debate's calls and the baseline's calls, and they are equal.
- [ ] The run prints all three methods side by side.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
