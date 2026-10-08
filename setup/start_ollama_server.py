"""Start this project's own Ollama server, so the experiments can use the models in models/.

Press play on this file before running any experiment. The server keeps running in the background
until you press play on setup/stop_ollama_server.py.

The server reads its models from this project's models/ folder and listens on this project's own port
(see settings.py), so it never touches another Ollama server on this computer.
"""

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Here we add the project folder to Python's search path, so this file can import settings.py
# from the folder above when you press play on it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import settings


def ollama_server_is_running() -> bool:
    """Return True if this project's Ollama server answers on its port."""
    try:
        urllib.request.urlopen(settings.OLLAMA_ADDRESS + "/api/version", timeout=2)
        return True
    except OSError:
        return False


def start_ollama_server() -> None:
    """Start this project's Ollama server in the background, unless it is already running."""
    if ollama_server_is_running():
        print(f"This project's Ollama server is already running on port {settings.OLLAMA_PORT}.")
        return

    # Here we start `ollama serve` with this project's models folder and port. start_new_session lets it
    # keep running after this file finishes. Its messages go to a log file in models/.
    server_log = open(settings.MODELS_FOLDER / "ollama-server.log", "a")
    subprocess.Popen(
        ["ollama", "serve"],
        env=settings.ollama_environment(),
        stdout=server_log,
        stderr=server_log,
        start_new_session=True,
    )

    # Here we wait until the server answers, so the experiments can use it straight away.
    for _ in range(30):
        if ollama_server_is_running():
            print(f"Started this project's Ollama server on port {settings.OLLAMA_PORT}.")
            return
        time.sleep(1)
    print("The Ollama server did not answer. See models/ollama-server.log for its messages.")


def report_missing_models() -> None:
    """Warn if a model the experiments need is not in models/ yet."""
    for model_name in [settings.DEBATER_MODEL, settings.JUDGE_MODEL]:
        if settings.model_is_downloaded(model_name):
            print(f"Model ready: {model_name}")
        else:
            print(f"Model missing: {model_name}. Run download_models() in settings.py first.")


if __name__ == "__main__":
    start_ollama_server()
    report_missing_models()
    print("When you have finished, press play on setup/stop_ollama_server.py.")
