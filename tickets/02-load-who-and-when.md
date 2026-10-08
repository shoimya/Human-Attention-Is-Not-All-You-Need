# 02: Load Who&When and read it

**Tag:** `<build>`
**Blocked by:** 01
**Status:** doing (everything done except the team filling in the 5 review files)

**What to build:** Everything about the data lives in `data.py`, and pressing play on `data.py` runs it. It downloads the 58 Who&When Hand-Crafted failures as plain JSON files into the project, turns them into Trajectories, removes any run whose Decisive step does not exist (saying why; in the JSON files there are none), prints any one Trajectory with its label, writes a pilot split and a test split, and writes a human review set without labels. `run.py` is not touched in this ticket; it is for the pilot and later runs.

**Functions in `data.py`, in this order** (agreed with the owner, 2026-10-08):
1. **Set up the data folder:** create `data/who_and_when/` (downloaded runs, not in git) and `data/splits/` (split files, pushed to git).
2. **Download the dataset:** download `1.json` … `58.json` from Hugging Face (`Kevin355/Who_and_When`, folder `Who&When/Hand-Crafted/`, about 4 MB) with Python's built-in tools, only the files that are missing, and return the 58 runs as Trajectories. No Hugging Face library and no Hugging Face cache (owner chose this over the `datasets` library: plain readable files, no new library, works offline after the first download).
3. **Remove the bad runs:** for each run whose Decisive step is outside the run, print the run and then why it was removed. Return the usable runs (all 58 with the JSON files).
4. **Print one Trajectory:** take a number from 1 to 58 and print that run's steps, then its label (Decisive step, agent and reason).
5. **`split_pilot_and_test`:** pick a random number from 1 to 58 as the pilot; delete the old split files and write new ones. Pilot = that 1 run; test = all 58 (the pilot is included). Each file lists the runs' numbers, IDs and file names, not copies of the runs. Commented out in the main block: remove the `#` to make a new split.
6. **`human_review_split`:** pick 5 different random runs from 1 to 58 (the pilot may be one of them) and write each to `data/human_review/run_<number>.md` with its steps and an empty answer section, but **without the label**. Refuses unless `data/human_review/` is empty (hidden files such as `.DS_Store` do not count), so typed answers are never lost. Pushed to git. Commented out in the main block.
7. **Data analysis:** done in a separate notebook, `data_analysis.ipynb` (owner's decision, 2026-10-08), not in `data.py`. It runs on Kaggle (clones branch `SC.V1`) or on the Mac, imports `data.py`, and saves its figures to `figures/` for the midterm report.

Run length = number of steps.

- [x] Pressing play on `data.py` sets up the data folder, downloads only missing files, removes bad runs with an explanation each (none in the JSON files), and prints one Trajectory.
- [x] Download stays inside the project: `data/who_and_when/` holds the 58 files; nothing is written to the home folder. `data/who_and_when/` is in `.gitignore`; `data/splits/` and `data/human_review/` are not.
- [x] A download that breaks off halfway leaves no broken file behind.
- [x] `split_pilot_and_test` writes `data/splits/pilot.json` (1 run) and `data/splits/test.json` (58 runs), replacing any old ones.
- [x] `human_review_split` writes 5 unlabelled runs to `data/human_review/` and refuses when that folder is not empty.
- [x] Follows the code standards in `CLAUDE.md`: tests written first, every file runs with the play button, comments explain the important lines.
- [x] Make the first split and the human review set. Done 2026-10-08: **pilot = run 36** (`36.json`, 91 steps, Decisive step 9 by Orchestrator), test = all 58 runs; **human review set = runs 2, 35, 45, 47, 50**. Both lines are commented out again in the main block, so the pilot does not change on the next play.
- [x] Data analysis notebook for the midterm report (`data_analysis.ipynb`), checked end to end.
- [x] README explains how a new user runs `settings.py`, `data.py` and the Kaggle notebook.
- [ ] For the 5 review runs: each person fills in the answer section (Decisive step, agent, minutes taken, how sure, notes), then compares with the label using `print_trajectory`. **(Team task.)**

## Known about the data

- Raw JSON fields: `history` (the steps), `question`, `groundtruth`, `is_corrected`, `question_ID`, `mistake_agent`, `mistake_step`, `mistake_reason`. One step is `{role, content}`. (The Parquet version also has `mistake_type`; we do not use it.)
- Length: median 32.5 steps, max 130, min 5.
- **The Decisive step counts from 0.** In the Parquet version, for 47 of 58 runs the step at that position (counting from 0) belongs to the labelled agent; counting from 1 matches only 10.
- **All 58 runs are usable (team decision 2026-10-08, option a).** The Parquet version has 3 broken labels that point past the last step (rows 25, 39, 50). The JSON files have the same steps but corrected labels for those runs: `53.json` step 24 (Assistant), `34.json` step 4 (WebSurfer), `54.json` step 15 (WebSurfer), and the agent at each corrected step matches the labelled agent. Across all 58 runs, the two versions differ only in these 3 labels. Found because a test expecting 55 runs failed. Worth a sentence in the paper.
- 8 runs (Parquet version) have a labelled step whose role does not match `mistake_agent`, and agent names are not consistently capitalized (`Websurfer` / `WebSurfer`). Relevant for the later data analysis, ticket 09 and the paper.
- Example: `1.json` has 29 steps, Decisive step 12, by WebSurfer.

## Outcome

Code done 2026-10-08, test-first.

**`data.py`** (press play to run it). Its opening description explains how to use it; every field of `Trajectory` has a comment; each step of the main block has a comment.
- `Step` (number from 0, agent, text) and `Trajectory` (file name, ID, question, steps, Decisive step, agent, reason).
1. `set_up_data_folder()`: creates `data/who_and_when/` and `data/splits/`.
2. `download_who_and_when()`: downloads `1.json` to `58.json` with Python's built-in tools, only missing ones (4.1 MB, no new library), in number order so run numbers match on every computer; returns 58 Trajectories. Each file downloads under a temporary `.partial` name and is renamed only when complete, so a broken-off download never leaves a half-written file for the next run to trust.
3. `remove_bad_runs()`: prints each run whose Decisive step does not exist, then why it was removed; returns the rest. On the JSON files: "Kept 58 of 58 runs (0 removed)".
4. `print_trajectory(usable_runs, run_number)`: number 1 to 58; steps first, then the label and the reason; a number outside the range prints the allowed range. `run_to_print` in the main block picks the run.
5. `split_pilot_and_test(usable_runs)`: random pilot from 1 to 58; deletes and rewrites `pilot.json` and `test.json` (each entry: number, ID, file name). Commented out in the main block.
6. `human_review_split(usable_runs)`: 5 different random runs written to `data/human_review/run_<number>.md` without labels, with an answer section. Refuses unless the folder is empty. Helpers: `folder_has_visible_files()` (ignores hidden files) and `write_human_review_file()`. Commented out in the main block.

**`tests/test_2_data.py`**: 10 tests, all passing (about 0.1 s). Every test failed first and then passed, except that the "usable runs" test failed because of the data (the corrected labels), which led to the 58-run decision.
1. folders inside the project
2. 58 runs downloaded and `1.json` read correctly (29 steps, Decisive step 12, WebSurfer)
3. a download that breaks off halfway leaves no `1.json` behind (the broken download is faked, because the real network cannot be broken on purpose)
4. a made-up run with a missing Decisive step is removed, with its reason printed
5. all 58 real runs are usable
6. run 1 is printed with the label after its last step
7. an out-of-range run number gives a clear message
8. the split (in a temporary folder) writes 1 pilot run and all runs as test, and replaces an old split
9. the human review set (in a temporary folder) writes 5 different runs with no label and with an answer section
10. the human review set refuses and writes nothing when the folder already holds a file

The split and review tests use temporary folders, so running the tests never touches the real `data/splits/` or `data/human_review/`.

**Checked before handing over:** both test files pass with the play button (10 + 10); pressing play on `data.py` prints "58 runs (0 newly downloaded)", "Kept 58 of 58 runs (0 removed)" and run 1; no `.partial` files, no `runs/`, no `data/human_review/` yet; the Ollama server is stopped.

**Other changes:** `.gitignore` has `data/who_and_when/` (with a comment that `data/splits/` and `data/human_review/` are pushed). `Documents Delivered/` (the brief PDF) goes to GitHub (owner's decision). The main README lists `data/who_and_when/` in the download table and has a "press play on `data.py`" setup step. `tickets/README.md` lists the new files and folders. `run.py` is untouched. Nothing is written to the home folder; no new library was added.

**Data analysis notebook (`data_analysis.ipynb`, added 2026-10-08).** 9 sections: usable runs; one Trajectory drawn step by step (text length per step, coloured by agent, Decisive step marked) with the steps around the mistake; run length (steps and estimated reading minutes); how runs end; where the mistake is (position, and minutes read to reach it); who is blamed (share of steps vs share of Decisive steps); label quality; how hard the task is (random and middle-step baselines, debate rounds and calls); summary table. Figures `1_one_trajectory.png` to `5_who_is_blamed.png` are saved to `figures/`. Checked by running every cell on the Mac (no errors) and by looking at every figure.

Key numbers from it: 58 of 58 runs usable; median 32.5 steps (5–130); median about 35 minutes to read a whole run but about 12 minutes to reach the mistake (estimates: characters ÷ 6 ÷ 200 words per minute); 31 of 58 runs were stopped by the system (21 with no agent chosen to speak, 6 at the 30-round limit, 4 at the 1500-second limit); WebSurfer writes 19% of steps but holds 57% of Decisive steps; the agent at the labelled step matches the labelled agent in 55 of 58 runs (`20.json`, `22.json`, `49.json` do not); random guessing hits the exact step 4.2% of the time (17.8% within ±2), always picking the middle step 1.7% (17.2%); the debate needs a median of 6 rounds, about 15 model calls.

**Split and review set made (2026-10-08):** `data/splits/pilot.json` holds run 36; `data/splits/test.json` holds all 58 runs; `data/human_review/` holds `run_2.md`, `run_35.md`, `run_45.md`, `run_47.md`, `run_50.md`, all with empty answer sections. These files are pushed, so the whole team uses the same pilot and review set; nobody should run the split again unless the team decides to.

**README updated** (2026-10-08) with the full path for a new user or teammate: install, press play on `settings.py`, select `.venv`, download models, press play on `data.py`, run the tests, run `data_analysis.ipynb` on Kaggle (step by step), plus a table of what is in the repo.

**Left:** each person fills in the answer section of the review files, timing themselves, then compares with the label using `print_trajectory`. When that is done, ticket 02 is done.
