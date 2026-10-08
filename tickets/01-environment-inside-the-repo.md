# 01: Environment inside the repo

**Tag:** `<build>`
**Blocked by:** None (can start immediately)
**Status:** done

**What to build:** A setup that makes this project run entirely from its own folder and independently of any other project, built for VS Code on a Mac. The Python environment, the package cache and the Ollama models all live inside the project folder, wherever it was cloned. This project runs its own Ollama server, on its own port, reading models only from the project's `models/` folder. Every file runs with the play button.

- [x] Pressing play on `settings.py` creates the project folders and files and the Python environment, and installs the requirements, skipping anything that already exists.
- [x] One function downloads the debater (`qwen3.5:9b`) and judge (`qwen3.5:2b`) models into `models/`, skipping models already there.
- [x] One script starts this project's Ollama server; one script stops only that server.
- [x] Settings demo prints the active settings (models, port, folders).
- [x] No models in the home folder (`~/.ollama/models` does not exist); pip's cache is inside the project.
- [x] `.gitignore` covers the environment, the caches, the models and `runs/`; README explains setup step by step.
- [x] Tests confirm the setup (written after the code, at the owner's request).

## Outcome

Rebuilt from scratch 2026-10-08, step by step with the owner, after the first version was deleted.

**Project folder now**
```
settings.py                    setup functions + project settings (built for VS Code on a Mac)
setup/start_ollama_server.py   starts this project's Ollama server
setup/stop_ollama_server.py    stops it
tests/test_1_settings.py       10 tests for the setup
data.py, run.py                empty, filled by later tickets
requirements.txt               pytest==9.1.1
README.md, .gitignore, tickets/
.venv/        Python 3.12.14 (about 30 MB)          not in git
.cache/pip/   pip's download cache (a few MB)        not in git
models/       qwen3.5:9b 6.6 GB + qwen3.5:2b 2.7 GB   not in git
```

**`settings.py`**
- Settings at the top: `MODELS_FOLDER` (`models/`), `OLLAMA_PORT` (11500), `OLLAMA_ADDRESS`, `DEBATER_MODEL` (`qwen3.5:9b`), `JUDGE_MODEL` (`qwen3.5:2b`), and the setup paths. All paths are worked out from where `settings.py` is, so they work in any clone.
- `create_project_structure()`: creates `setup/`, `tests/`, and empty `data.py` and `run.py`; never empties an existing file.
- `install_ticket_one_requirements()`: finds Python 3.12 by itself (so any Python can press play), builds `.venv/`, installs `requirements.txt` with pip's cache in `.cache/pip/`, and checks that Ollama is installed (it never installs it).
- `print_next_step()`: reminds you to select the `.venv` interpreter in VS Code once.
- `model_is_downloaded()`: checks on disk for Ollama's index file of a model, with no server needed.
- `ollama_environment()`: tells Ollama to use `models/` and port 11500.
- `download_models()`: downloads only missing models, through a temporary server it starts and stops itself. It does not run on play; you add it to the main block yourself.
- `print_settings()`: the settings demo.
- The main block runs the setup, prints how to start and stop the server for experiments, then prints the settings.

**`setup/start_ollama_server.py`**: starts `ollama serve` in the background with `models/` and port 11500, unless already running; waits until it answers; reports whether both models are there. Server messages go to `models/ollama-server.log`.

**`setup/stop_ollama_server.py`**: stops only whatever listens on port 11500 and waits until it has stopped; says "Nothing to stop" if nothing is running.

**`tests/test_1_settings.py`** (10 tests, all passing, about 1 second, nothing written to `runs/`):
1. storage folders inside the project
2. port not 11434
3. Ollama told to use `models/` and 127.0.0.1:11500
4. project folders and files exist
5. environment is Python 3.12
6. Ollama installed
7. both models downloaded
8. a never-downloaded model reported missing
9. `models/` and `.venv/` in `.gitignore`
10. start → server lists both models → stop → port free (skipped if the server is already running, so a test never stops a server you are using)

**Checks run**
- Download: both models into `models/` (9.2 GB); temporary server stopped afterwards; no `~/.ollama/models`.
- Start and stop: stop with nothing running → "Nothing to stop"; start → listening, both models listed; start again → "already running"; stop → port free.
- `git status` shows nothing from `models/`, `.venv/` or `.cache/`.

**Gotchas**
- A plain `ollama pull` talks to the default server on port 11434, so the model lands outside the project. Add models in `settings.py`, or put `OLLAMA_HOST=127.0.0.1:11500` in front of `ollama` commands.
- Ollama writes `~/.ollama/cache/model-recommendations.json` (about 2 KB, no model data) each time a server starts, whatever `OLLAMA_MODELS` says. It cannot be prevented from our side.
- VS Code must use the `.venv` interpreter for files that need the project's libraries (`print_next_step()` explains how).
- Ollama unloads a model from memory after about 5 minutes without use; the server keeps running until the stop script stops it.

**Moved to ticket 02 (owner's decision, 2026-10-08):** pointing the Hugging Face cache into the project. Nothing in this ticket downloads from Hugging Face; the first download is ticket 02's dataset, so it belongs there.
