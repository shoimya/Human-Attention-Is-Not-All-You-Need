"""Stop this project's own Ollama server.

Press play on this file when you have finished running experiments. Only the server on this
project's port (see settings.py) is stopped; any other Ollama server on this computer keeps running.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Here we add the project folder and this folder to Python's search path, so this file can import
# settings.py and the start script when you press play on it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import settings
from start_ollama_server import ollama_server_is_running


def server_process_ids() -> list[int]:
    """Return the process ids of whatever is listening on this project's Ollama port."""
    # Here we ask macOS which processes listen on the port; -t prints only their process ids.
    lsof_result = subprocess.run(
        ["lsof", "-t", "-i", f"TCP:{settings.OLLAMA_PORT}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    return [int(process_id) for process_id in lsof_result.stdout.split()]


def stop_ollama_server() -> None:
    """Stop this project's Ollama server and wait until it no longer answers."""
    if not ollama_server_is_running():
        print(f"No Ollama server is running on port {settings.OLLAMA_PORT}. Nothing to stop.")
        return

    for process_id in server_process_ids():
        # Here we send the polite "please stop" signal, the same one the `kill` command sends.
        os.kill(process_id, signal.SIGTERM)

    # Here we wait until the server stops answering, so we only report success once it has really stopped.
    for _ in range(15):
        if not ollama_server_is_running():
            print(f"Stopped this project's Ollama server on port {settings.OLLAMA_PORT}.")
            return
        time.sleep(1)
    print(f"The Ollama server on port {settings.OLLAMA_PORT} is still running.")


if __name__ == "__main__":
    stop_ollama_server()
