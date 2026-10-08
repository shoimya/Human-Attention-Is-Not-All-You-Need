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

## What gets downloaded, and where

Everything the project downloads stays **inside this folder**, wherever you cloned it. None of it goes to GitHub.

| Folder | What it holds | Size | Created by |
|---|---|---|---|
| `.venv/` | The project's Python 3.12 and its libraries (from `requirements.txt`) | about 30 MB | `settings.py` |
| `.cache/pip/` | pip's copy of the downloaded libraries | a few MB | `settings.py` |
| `models/` | The two AI models: `qwen3.5:9b` (debater, 6.6 GB) and `qwen3.5:2b` (judge, 2.7 GB) | about 9.2 GB | `download_models()` in `settings.py` |

Two small exceptions, written by the programs themselves, outside this folder:
- Homebrew installs Python 3.12 and Ollama in `/opt/homebrew/` (one time, shared by all projects).
- Ollama writes a 2 KB file, `~/.ollama/cache/model-recommendations.json`, each time its server starts. It holds no model data.

## Get started (one time)

1. **Clone the repo and open the folder in VS Code.**

2. **Press play on `settings.py`.** Any Python works for this step. It:
   - creates the `setup/` and `tests/` folders and the empty `data.py` and `run.py` (anything that already exists is left alone)
   - builds `.venv/` with Python 3.12 and installs `requirements.txt`
   - checks that Ollama is installed

3. **Point VS Code at the project's Python** (once):
   Cmd+Shift+P → **Python: Select Interpreter** → choose `.venv`.
   If `.venv` is not listed: **Enter interpreter path…** → `.venv/bin/python`.
   From now on, the play button runs every file with the project's Python.

4. **Download the models (about 9.2 GB).** At the bottom of `settings.py`, remove the `#` in front of `# download_models()` and press play. Only missing models are downloaded, so running it again costs nothing. Put the `#` back afterwards if you like.

5. **Check everything.** Press play on `tests/test_1_settings.py`. All tests should pass.

## Every time you work

1. Press play on **`setup/start_ollama_server.py`**. It starts this project's own Ollama server in the background and confirms both models are there.
2. Run your experiments.
3. When you have finished, press play on **`setup/stop_ollama_server.py`**.

This project's server uses **port 11500** and reads models only from `models/`. It is separate from the Ollama app and from any other project's Ollama server (those use the default port 11434), so they never mix.

## Good to know

- **Don't use a plain `ollama pull`.** It talks to the default server on port 11434, so the model would land outside this project (usually in your home folder). To add a model, add it to `settings.py`. To use the `ollama` command by hand, put the port in front: `OLLAMA_HOST=127.0.0.1:11500 ollama list`.
- **Models load into memory only when used.** Ollama unloads a model after about 5 minutes without use. The server itself keeps running until you run the stop script.
- **If the server will not start**, its messages are in `models/ollama-server.log`.
- **Pressing play on `settings.py` again is safe.** It only adds what is missing.
