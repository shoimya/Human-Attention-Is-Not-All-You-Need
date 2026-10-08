# Can debate reduce human review time?

When an AI agent fails a long task, a person has to read the whole run to find the step that caused the failure. This project tests whether a **prover-estimator debate** between two AI models can find that step, so the person checks one step instead of the whole run.

The tasks are in [tickets/](tickets/README.md).

## Before you start

The setup is built for **VS Code on a Mac**. You need:

| What | Why | How to get it |
|---|---|---|
| [Homebrew](https://brew.sh) | Installs the two programs below | See brew.sh |
| Python 3.12 | The project's Python environment is built with it | `brew install python@3.12` |
| Ollama | Runs the AI models on your Mac | `brew install ollama` |
| VS Code with the Python extension | Every file runs with the play button | [code.visualstudio.com](https://code.visualstudio.com) |
| About **10 GB free** where you keep this folder | Mostly for the models | |
| A [Kaggle](https://www.kaggle.com) account | Runs the data analysis notebook | Free sign-up |

## What gets downloaded, and where

Everything the project downloads stays **inside this folder**, wherever you cloned it. None of it goes to GitHub.

| Folder | What it holds | Size | Created by |
|---|---|---|---|
| `.venv/` | The project's Python 3.12 and its libraries (from `requirements.txt`) | about 30 MB | `settings.py` |
| `.cache/pip/` | pip's copy of the downloaded libraries | a few MB | `settings.py` |
| `models/` | The two AI models: `qwen3.5:9b` (debater, 6.6 GB) and `qwen3.5:2b` (judge, 2.7 GB) | about 9.2 GB | `download_models()` in `settings.py` |
| `data/who_and_when/` | The 58 failed agent runs from the Who&When dataset, as JSON files | about 4 MB | pressing play on `data.py` |

Two small exceptions, written by the programs themselves, outside this folder:
- Homebrew installs Python 3.12 and Ollama in `/opt/homebrew/` (one time, shared by all projects).
- Ollama writes a 2 KB file, `~/.ollama/cache/model-recommendations.json`, each time its server starts. It holds no model data.

## What is already in the repo

| Path | What it is |
|---|---|
| `settings.py` | Sets up the project and holds its settings (folders, models, Ollama port 11500) |
| `setup/start_ollama_server.py`, `setup/stop_ollama_server.py` | Start and stop this project's own Ollama server |
| `data.py` | Downloads the data, prints a run, and makes the splits and the human review set |
| `data_analysis.ipynb` | The data analysis for the midterm report (run it on Kaggle) |
| `data/splits/pilot.json`, `data/splits/test.json` | The team's split: **pilot = run 36**, test = all 58 runs |
| `data/human_review/run_*.md` | The team's 5 runs without labels (runs 2, 35, 45, 47, 50), to fill in by hand |
| `tests/` | Tests for the setup and the data; press play on a test file to run it |
| `tickets/` | The task list |

The split and the human review set are **shared by the whole team**. Do not make new ones unless the team agrees: a new split changes the pilot run for everyone.

## Get started (one time)

1. **Clone the repo and open the folder in VS Code.**

2. **Press play on `settings.py`.** Any Python works for this step. It:
   - creates the `setup/` and `tests/` folders and the empty `data.py` and `run.py` if they are missing (anything that already exists is left alone)
   - builds `.venv/` with Python 3.12 and installs `requirements.txt`
   - checks that Ollama is installed

3. **Point VS Code at the project's Python** (once):
   Cmd+Shift+P → **Python: Select Interpreter** → choose `.venv`.
   If `.venv` is not listed: **Enter interpreter path…** → `.venv/bin/python`.
   From now on, the play button runs every file with the project's Python.

4. **Download the models (about 9.2 GB).** At the bottom of `settings.py`, remove the `#` in front of `# download_models()` and press play. Only missing models are downloaded, so running it again costs nothing. Put the `#` back afterwards. *(Not needed for the data analysis notebook; needed for the experiments.)*

5. **Download the data (about 4 MB).** Press play on `data.py`. It downloads the 58 runs into `data/who_and_when/` (only missing files) and prints run 1. To read another run, change `run_to_print` at the bottom of `data.py`.

6. **Check everything.** Press play on `tests/test_1_settings.py` and on `tests/test_2_data.py`. All tests should pass.

## Run the data analysis notebook on Kaggle

The notebook downloads this project from GitHub by itself, so it always uses the code on the `SC.V1` branch. **Push your changes first** if you want the notebook to see them.

1. Download `data_analysis.ipynb` from the GitHub repo (open the file on GitHub → **Download raw file**).
2. On Kaggle: **Create → New Notebook**, then **File → Import Notebook** and upload `data_analysis.ipynb`.
3. In the notebook's right-hand panel (**Settings**):
   - **Internet: On** (needed to clone the repo and download the data)
   - **Accelerator: None** (no GPU needed)
4. **Only if the GitHub repo is private:** **Add-ons → Secrets → Add a new secret**, named `GITHUB_TOKEN`, with a GitHub token that can read this repo. Switch it on for this notebook.
5. **Run All.** It takes about a minute. The first cell clones the repo; the rest downloads the 58 runs and draws the figures.
6. **Get the figures:** in the right-hand panel under **Output**, open `can-debate-be-used-to-reduce-human-review-time/figures/` and download the PNG files.

You can also run the notebook on your Mac: open it in VS Code from the project folder and press **Run All**. It needs `pandas` and `matplotlib`, which Kaggle already has but this project's `.venv` does not.

## Fill in a human review file

Each `data/human_review/run_<number>.md` shows one run without its label. Note the time, read the run, find the step where it went wrong, and fill in the **Your answer** section at the bottom (Decisive step, agent, minutes taken, how sure, notes). Then compare with the real label: set `run_to_print` in `data.py` to that run's number and press play.

## Every time you run experiments

1. Press play on **`setup/start_ollama_server.py`**. It starts this project's own Ollama server in the background and confirms both models are there.
2. Run your experiments.
3. When you have finished, press play on **`setup/stop_ollama_server.py`**.

This project's server uses **port 11500** and reads models only from `models/`. It is separate from the Ollama app and from any other project's Ollama server (those use the default port 11434), so they never mix.

## Good to know

- **Don't use a plain `ollama pull`.** It talks to the default server on port 11434, so the model would land outside this project (usually in your home folder). To add a model, add it to `settings.py`. To use the `ollama` command by hand, put the port in front: `OLLAMA_HOST=127.0.0.1:11500 ollama list`.
- **Models load into memory only when used.** Ollama unloads a model after about 5 minutes without use. The server itself keeps running until you run the stop script.
- **If the server will not start**, its messages are in `models/ollama-server.log`.
- **Pressing play on `settings.py` or `data.py` again is safe.** They only add what is missing.
