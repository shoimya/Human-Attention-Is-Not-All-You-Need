"""Stop this project's own Ollama server.

Only the server on this project's port is stopped. Any other Ollama server on the machine
(another project's, or the Ollama app on the default port 11434) keeps running.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Here we add the repo folder to Python's search path, so this file can import settings.py
# and the start script from the folders above when it runs on its own.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from settings import Settings, load_settings
from setup.start_model_server import server_is_running


def server_process_ids(settings: Settings) -> list[int]:
    """Return the process ids of whatever is listening on this project's Ollama port."""
    # Here we ask macOS which processes listen on the port: -t prints only process ids.
    lsof_result = subprocess.run(
        ["lsof", "-t", "-i", f"TCP:{settings.ollama_port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    return [int(process_id) for process_id in lsof_result.stdout.split()]


def stop_server(settings: Settings) -> None:
    """Ask this project's Ollama server to shut down."""
    for process_id in server_process_ids(settings):
        # Here we send the polite "please stop" signal, the same one the `kill` command sends.
        os.kill(process_id, signal.SIGTERM)


def wait_until_server_stops(settings: Settings, timeout_seconds: int = 15) -> None:
    """Wait until the server no longer answers, and stop with an error if it keeps running."""
    for _ in range(timeout_seconds):
        if not server_is_running(settings):
            return
        time.sleep(1)
    raise RuntimeError(f"Ollama server on port {settings.ollama_port} is still running.")


if __name__ == "__main__":
    # Here we load the settings on one visible line, so you can step over it in the debugger.
    settings = load_settings()

    if not server_is_running(settings):
        print(f"No Ollama server is running on port {settings.ollama_port}. Nothing to stop.")
    else:
        stop_server(settings)
        wait_until_server_stops(settings)
        print(f"Stopped the Ollama server on port {settings.ollama_port}.")
