# 01: Environment inside the repo

**Tag:** `<build>`
**Blocked by:** None (can start immediately)
**Status:** done

**What to build:** One setup step that makes this project run entirely from the SSD and independently of any other project. The Python environment, the package caches and the Ollama models all live inside the repo. This project starts its own Ollama server, on its own port, with its own models folder, and pulls the debater (Qwen3.5-9B) and judge (Qwen3.5-2B) models into it. A matching script stops that server. Settings live in one settings file, with defaults that work, and load on one visible line.

- [x] One setup script starts this project's Ollama server and pulls both models into the repo; the owner's other project is unaffected.
- [x] One setup script stops only this project's Ollama server.
- [x] Settings demo prints the active settings (models, port, folders).
- [x] Nothing new is written to the home folder (no `~/.ollama/models`, no new Hugging Face or pip cache there).
- [x] `.gitignore` also covers the environment, the caches and `runs/`; README explains setup in a few steps.
- [x] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.

## Outcome

Done 2026-10-08.

**Files added**
- `settings.py`: all settings, loaded with `settings = load_settings()`. The demo prints one setting per line.
  - Folders, all inside the repo: `.cache/pip`, `.cache/huggingface`, `.cache/ollama-models`, `runs/`.
  - Ollama port 11500 (Ollama's default 11434 stays free for other projects).
  - Debater `qwen3.5:9b`, judge `qwen3.5:2b`.
  - Loading the settings sets `HF_HOME`, so Hugging Face downloads go into the repo.
- `setup/start_model_server.py`: starts this project's own `ollama serve` (models in the repo, port 11500) if it is not already running, then downloads only missing models. Safe to rerun. Server messages go to `.cache/ollama-server.log`.
- `setup/stop_model_server.py`: stops only the server listening on port 11500, waits until it no longer answers, and says "Nothing to stop" if it is not running. It reuses the start script's check for whether the server is running.
- `tests/test_1_environment.py`: 4 tests, built red → green one at a time:
  1. every storage folder is inside the repo
  2. the Ollama port is not 11434
  3. loading the settings points `HF_HOME` into the repo
  4. the server environment keeps models in the repo and listens on 127.0.0.1:11500

  They run on their own or through `pytest`, and write nothing to `runs/`.
- `requirements.txt`: `pytest==9.1.1` only.
- `README.md`: setup in three commands, how to stop the server, and the `ollama pull` gotcha.
- `.gitignore`: `CLAUDE.md`, `proposal.md`, `.venv/`, `.cache/`, `runs/`, `__pycache__/`, `.pytest_cache/`, `.DS_Store`.

**Checks run**
- Venv: Python 3.12.14 in `.venv/` (26 MB); pip cache in `.cache/pip/`.
- Models: `qwen3.5:9b` (6.6 GB) and `qwen3.5:2b` (2.7 GB), 8.6 GB in total in `.cache/ollama-models/`, listed by `OLLAMA_HOST=127.0.0.1:11500 ollama list`.
- Home folder: `~/.ollama` has no `models` folder; no new pip or Hugging Face files.
- Rerunning the start script downloads nothing ("already installed").
- Stop script: stop → port 11500 free; stop again → "Nothing to stop"; start → listening; stop → free. Port 11434 was not in use during the check; the script only targets port 11500 by design.
- The server is left **stopped**. Start it with the start script before working.

**Gotchas**
- A plain `ollama pull` goes to the default server on port 11434, so the model would land outside this repo. Use the start script, or put `OLLAMA_HOST=127.0.0.1:11500` in front of `ollama` commands.
- Models load into memory only when called, and Ollama unloads them after about 5 minutes without use. The server itself keeps running until the stop script stops it.
- VS Code must use the `.venv` interpreter (Python: Select Interpreter → `.venv`) for Debug to find the installed packages.
