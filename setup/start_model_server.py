"""Start this project's own Ollama server and download the models it needs.

The server keeps its models inside the repo and listens on this project's own port,
so it never touches another project's Ollama server or models.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Here we add the repo folder to Python's search path, so this file can import settings.py
# from the folder above when it runs on its own.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from settings import Settings, load_settings


def model_server_environment(settings: Settings) -> dict:
    """Return the environment variables for this project's Ollama server and Ollama commands."""
    server_environment = dict(os.environ)
    # Here we tell Ollama to keep its models inside the repo.
    server_environment["OLLAMA_MODELS"] = str(settings.ollama_models_folder)
    # Here we tell Ollama to use this project's port, both for the server and for commands like `ollama pull`.
    server_environment["OLLAMA_HOST"] = f"127.0.0.1:{settings.ollama_port}"
    return server_environment


def server_address(settings: Settings) -> str:
    """Return the web address of this project's Ollama server."""
    return f"http://127.0.0.1:{settings.ollama_port}"


def server_is_running(settings: Settings) -> bool:
    """Return True if this project's Ollama server answers."""
    try:
        urllib.request.urlopen(server_address(settings) + "/api/version", timeout=2)
        return True
    except OSError:
        return False


def start_server(settings: Settings) -> None:
    """Start this project's Ollama server in the background, writing its messages to a log file in the repo."""
    settings.ollama_models_folder.mkdir(parents=True, exist_ok=True)
    server_log_path = settings.ollama_models_folder.parent / "ollama-server.log"
    server_log = open(server_log_path, "a")

    # Here we start `ollama serve` as its own process, so it keeps running after this script ends.
    subprocess.Popen(
        ["ollama", "serve"],
        env=model_server_environment(settings),
        stdout=server_log,
        stderr=server_log,
        start_new_session=True,
    )
    print(f"Started Ollama server on port {settings.ollama_port}. Log: {server_log_path}")


def wait_until_server_answers(settings: Settings, timeout_seconds: int = 30) -> None:
    """Wait until the server answers, and stop with an error if it never does."""
    for _ in range(timeout_seconds):
        if server_is_running(settings):
            return
        time.sleep(1)
    raise RuntimeError(f"Ollama server did not answer on port {settings.ollama_port}.")


def installed_model_names(settings: Settings) -> list[str]:
    """Return the names of the models already in this project's models folder."""
    response = urllib.request.urlopen(server_address(settings) + "/api/tags", timeout=10)
    model_list = json.load(response)["models"]
    return [model["name"] for model in model_list]


def download_model(settings: Settings, model_name: str) -> None:
    """Download one model into this project's models folder, showing Ollama's progress bar."""
    print(f"Downloading {model_name} ...")
    subprocess.run(["ollama", "pull", model_name], env=model_server_environment(settings), check=True)


def download_missing_models(settings: Settings) -> None:
    """Download the debater and judge models if they are not already in the repo."""
    already_installed = installed_model_names(settings)
    for model_name in [settings.debater_model, settings.judge_model]:
        if model_name in already_installed:
            print(f"{model_name} is already installed.")
        else:
            download_model(settings, model_name)


if __name__ == "__main__":
    # Here we load the settings on one visible line, so you can step over it in the debugger.
    settings = load_settings()

    if server_is_running(settings):
        print(f"Ollama server is already running on port {settings.ollama_port}.")
    else:
        start_server(settings)
        wait_until_server_answers(settings)

    download_missing_models(settings)
    print("Installed models:", installed_model_names(settings))
