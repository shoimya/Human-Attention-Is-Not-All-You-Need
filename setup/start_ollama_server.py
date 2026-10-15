"""Start this project's own Ollama server, so the experiments can use the models in models/.

Press play on this file to keep the server running across many runs (the models stay loaded, which is faster).
It keeps running in the background until you press play on setup/stop_ollama_server.py.
You do not have to: run.py and download_models() in settings.py start the server themselves when it is not running.

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
    # Here we ask the server for its version, the smallest question it answers; no answer means it is not running.
    try:
        urllib.request.urlopen(settings.OLLAMA_ADDRESS + "/api/version", timeout=2)
        return True
    except OSError:
        return False


def start_ollama_server() -> bool:
    """Start this project's Ollama server in the background, unless it is already running.

    Returns True if this call started the server, so the caller knows to stop it again when it has finished,
    and False if a server was already running, which the caller must then leave running.
    """
    if ollama_server_is_running():
        print(f"This project's Ollama server is already running on port {settings.OLLAMA_PORT}.")
        return False

    # Here we start `ollama serve` with this project's models folder and port. start_new_session lets it
    # keep running after this file finishes. Its messages go to a log file in models/.
    settings.MODELS_FOLDER.mkdir(exist_ok=True)
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
            return True
        time.sleep(1)
    print("The Ollama server did not answer. See models/ollama-server.log for its messages.")
    return True


def report_missing_models() -> None:
    """Warn if a model the experiments need is not in models/ yet."""
    # Here we check on disk, through settings.py, so a missing model is reported before any experiment needs it.
    for model_name in [settings.DEBATER_MODEL, settings.JUDGE_MODEL]:
        if settings.model_is_downloaded(model_name):
            print(f"Model ready: {model_name}")
        else:
            print(f"Model missing: {model_name}. Run download_models() in settings.py first.")


if __name__ == "__main__":
    # Here we start the server (or find it already running) and confirm both models are there.
    start_ollama_server()
    report_missing_models()
    print("When you have finished, press play on setup/stop_ollama_server.py.")
