# Can debate reduce human review time?

We test whether a prover-estimator debate between AI models can find the step where a failed agent run went wrong, so a human checks one step instead of the whole run.

Tasks are in [tickets/](tickets/README.md).

## Setup (Mac)

Everything (Python packages, caches, models) is stored inside this folder. Needs Python 3.12 (`brew install python@3.12`) and Ollama (`brew install ollama`).

```bash
# 1. Create the Python environment inside the repo
/opt/homebrew/bin/python3.12 -m venv .venv

# 2. Install packages, keeping pip's download cache inside the repo
.venv/bin/pip install --cache-dir .cache/pip -r requirements.txt

# 3. Start this project's own Ollama server (port 11500) and download the models into .cache/
.venv/bin/python setup/start_model_server.py
```

Step 3 is safe to run again: it starts the server only if it is not running, and downloads only missing models. This server is separate from any other Ollama server on the machine.

When you are done working, stop the server. This stops only this project's server on port 11500:

```bash
.venv/bin/python setup/stop_model_server.py
```

To add a model, add it to `settings.py` and run step 3 again. A plain `ollama pull` talks to Ollama's default server (port 11434), so the model would land outside this repo. To use the `ollama` command by hand, put `OLLAMA_HOST=127.0.0.1:11500` in front, for example `OLLAMA_HOST=127.0.0.1:11500 ollama list`.

## Check that it works

```bash
.venv/bin/python settings.py          # prints the settings
.venv/bin/python -m pytest            # runs all tests
```
