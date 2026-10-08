# 02: Load Who&When and read it

**Tag:** `<build>`
**Blocked by:** 01
**Status:** ready-for-agent

**What to build:** Load the Who&When Hand-Crafted failures as Trajectories (task question, steps, Decisive step, responsible agent) in `data.py`, and print a short summary from `run.py --check`. The dataset downloads into the project's Hugging Face cache, never the home folder.

- [ ] The loader returns the 55 usable Trajectories (58 minus 3 whose Decisive step lies outside the run, see below); `run.py --check` prints their count and length (median and max steps).
- [ ] Point the Hugging Face cache into the project (for example `.cache/huggingface/`) before the `datasets` library is loaded, so the download lands inside the project and the home folder's Hugging Face cache is unchanged. *(Moved here from ticket 01.)*
- [ ] For 5 runs read by hand: notes on what a step looks like, whether the label looks right, and the minutes it took to find the mistake. **(Team task.)**
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.

## Already known about the data

From a first look at all 58 Hand-Crafted runs on 2026-10-08 (the code from that attempt was deleted; these facts still hold):

- Fields: `history` (the steps), `question`, `groundtruth`, `mistake_step`, `mistake_agent`, `mistake_reason`, `question_ID`, `mistake_type`, `is_corrected`. One step is `{role, content}`.
- Length: median 32.5 steps (all 58), 37 steps (the 55 usable); max 130; median about 42,000 characters.
- **The Decisive step counts from 0.** For 47 of 58 runs the step at that position (counting from 0) belongs to the labelled agent; counting from 1 matches only 10.
- **3 runs are skipped** (rows 25, 39, 50): their `mistake_step` points past the last step. Team decision 2026-10-08: skip them and report it. The main set is **55 Trajectories**.
- 8 runs have a labelled step whose role does not match `mistake_agent`, and agent names are not consistently capitalized (`Websurfer` / `WebSurfer`). Relevant for ticket 09 and the paper.
- Gotcha: the `datasets` library picks its download folder when it is imported, so the Hugging Face cache setting must be in place **before** `datasets` is imported.
