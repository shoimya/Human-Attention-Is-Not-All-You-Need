# 06: Standard debate

**Tag:** `<build>`
**Blocked by:** 05
**Status:** ready-for-agent

**What to build:** The second method, the standard (open) debate. Two debaters argue for a few rounds about which step is the Decisive step, then the judge picks one. The debate lives in `methods/standard_debate.py` (its own system prompts at the top; it asks the models only through `ask_model()`). `run.py` gets `run_standard_debate(json_file)`, which writes its logs to `runs/standard_debate/<start time>/`: one `run_<number>.md` per question (58 for the test split) and one `results.jsonl`.

- [ ] Same log layout as 04 (system prompts at the top, every prompt and reply in order, result at the bottom), with this debate's own notes, so the two methods' logs for the same question compare line by line.
- [ ] The run prints both methods' hit rates and average calls.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
