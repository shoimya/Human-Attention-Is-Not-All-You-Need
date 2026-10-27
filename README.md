# Can debate reduce human review time?

When an AI agent fails a long task, a person has to read the whole run to find the step that caused the failure: the *decisive step*. This project tests whether AI debate can find that step, so the person checks one step instead of the whole run. We compare a prover-estimator debate with simpler methods (standard debate, one-shot, single critique, binary search), giving every method the same number of model calls, and measure how often each finds the decisive step and how much reading time it saves. Course project, due 1 December 2026.

## Project structure

```
settings.py               project settings (models, Ollama port 11500, context windows, Mac or Kaggle) and setup
data.py                   downloads Who&When, reads the runs, makes the splits and the human review set
runV2.py                  the only code that talks to a model (send_to_ollama) and writes each run's log
run.py                    the older version of the model calls (ticket 03), kept with its tests; methods do not use it
methods/
  one_shot.py             one model names the decisive step several times; the step named most often wins
  single_critique.py      a proposer names a step, a critic checks it, a judge picks if they disagree
Notebooks/
  One-Shot-Kaggle.ipynb          one-shot on all 58 runs, on Kaggle
  Single-Critique-Kaggle.ipynb   single critique on all 58 runs, on Kaggle
  data_analysis.ipynb            the data analysis for the midterm report
setup/
  start_ollama_server.py  starts this project's own Ollama server
  stop_ollama_server.py   stops it
tests/                    test_1_settings.py to test_5_single_critique.py, in pipeline order
data/
  splits/                 pilot.json (run 36), test.json (all 58 runs), 5_local.json (5 random runs for the Mac)
  human_review/           5 runs without their labels, for the team to fill in by hand
informatics.md            how each method works, and the rules for building it
tickets/                  the task list
Documents Delivered/      the project brief (PDF)
requirements.txt          the Python libraries (pytest)

Created on your machine, not in git:
.venv/, .cache/pip/       the project's Python 3.12 and pip's download cache
models/                   the two Ollama models (about 9.3 GB)
data/who_and_when/        the 58 downloaded runs (about 4 MB)
runs/<method>/<date>/     one log per run (run_<number>_<time>.md); the Kaggle notebooks add summary_<time>.csv
figures/                  the PNG figures from data_analysis.ipynb
```

## Set up and run

**Once:**
1. Install Homebrew, then `brew install python@3.12 ollama`, and VS Code with the Python extension. Keep about 10 GB free.
2. Clone the repo and open its folder in VS Code.
3. At the bottom of `settings.py`, remove the `#` signs in front of `create_project_structure()`, `install_ticket_one_requirements()`, `print_next_step()` and `download_models()`, then press play. This builds `.venv/` and downloads both models into `models/`. Put the `#` signs back afterwards.
4. Cmd+Shift+P → **Python: Select Interpreter** → `.venv`.
5. Press play on `data.py` to download the 58 runs. It also replaces `data/splits/5_local.json` with 5 new random runs; put a `#` in front of `create_splits(...)` to keep yours.
6. Press play on each file in `tests/`. Tests that need the live model are skipped when the server is off.

**A few runs on the Mac:** press play on `methods/one_shot.py` (runs `5_local.json`) or `methods/single_critique.py` (runs the pilot). Each starts and stops the Ollama server itself and writes its logs to `runs/<method>/<date>/`.

**All 58 runs on Kaggle:** push to branch `SC.V1`, import a notebook from `Notebooks/`, and follow its first cell.

## Data and models

**Dataset: Who&When, Hand-Crafted.** 58 failed runs of the Magentic-One multi-agent system, each labelled with the responsible agent, the decisive step (counting from 0) and the annotators' reason ([Zhang et al., ICML 2025](https://arxiv.org/abs/2505.00212)). We use the files `1.json` to `58.json` from Hugging Face, [Kevin355/Who_and_When](https://huggingface.co/datasets/Kevin355/Who_and_When), folder `Who&When/Hand-Crafted/`; `data.py` downloads them. These JSON files fix three labels that are broken in the dataset's Parquet version, so all 58 runs are usable.

**Models.** Both come from Ollama's library, [ollama.com/library/qwen3.5](https://ollama.com/library/qwen3.5), and run on Ollama 0.35.1. `settings.download_models()` downloads them with `ollama pull`; their names are set in `settings.py`.

| Role | Ollama name | Compression | Model ID |
|---|---|---|---|
| Debater: one-shot, proposer, critic | `qwen3.5:9b` | Q4_K_M | `56671c2ab938` |
| Judge | `qwen3.5:2b` | Q8_0 | `0689d44085e0` |

They are compressed versions of the Qwen team's Qwen3.5-9B and Qwen3.5-2B ([Hugging Face](https://huggingface.co/Qwen/Qwen3.5-9B)), which we do not download directly.

## Good to know

- **Don't run a plain `ollama pull`.** It uses Ollama's default server (port 11434) and puts the model outside this project. Add models in `settings.py`. To use the `ollama` command by hand: `OLLAMA_HOST=127.0.0.1:11500 ollama list`.
- **To keep the models loaded across many runs,** press play on `setup/start_ollama_server.py` first and on `setup/stop_ollama_server.py` when you have finished. If the server will not start, read `models/ollama-server.log`.
- **Thinking is off for every method.** Switch it with `THINKING_ON` in `runV2.py`.
- **Expect long runs on a Mac:** one call on the pilot (run 36, about 38,000 tokens) takes several minutes on an M4 with 16 GB.
- **Human review:** each `data/human_review/run_<number>.md` is one run without its label. Time yourself, find the decisive step, fill in **Your answer**, then compare with the label (`run_to_print` in `data.py`).
- **The splits are shared by the team.** Don't make a new `pilot.json` or `test.json` unless the team agrees.
