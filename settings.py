"""Set up the project: create its folders and files, and install what ticket 01 needs.

Everything in this file is built specifically for Visual Studio Code on a Mac.

How to use it:
    1. Press play on this file in VS Code (any Python works; the environment itself is built with Python 3.12).
       It creates setup/, tests/, data.py, run.py and .venv/, and installs the libraries in requirements.txt.
    2. Then point VS Code at the project's Python, once:
       Cmd+Shift+P -> "Python: Select Interpreter" -> choose .venv
       (if .venv is not listed, choose "Enter interpreter path..." and type .venv/bin/python).
       From then on, the play button runs every file with the project's Python and its libraries.
    3. To download the models (about 9.3 GB, into models/ inside this project), add download_models()
       to the bottom of this file, under `if __name__ == "__main__":`, and press play.

It is safe to run again: anything that already exists is left as it is and not downloaded again.
"""

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

# Here we find the repo folder: the folder that holds this file.
REPO_FOLDER = Path(__file__).resolve().parent

# Here we name everything the setup creates. All of it lives inside the repo.
SETUP_FOLDER = REPO_FOLDER / "setup"
TESTS_FOLDER = REPO_FOLDER / "tests"
EMPTY_FILES = [REPO_FOLDER / "data.py", REPO_FOLDER / "run.py"]
VIRTUAL_ENVIRONMENT_FOLDER = REPO_FOLDER / ".venv"
PIP_CACHE_FOLDER = REPO_FOLDER / ".cache" / "pip"
REQUIREMENTS_FILE = REPO_FOLDER / "requirements.txt"

# Here we keep the Ollama models inside the project, wherever the project folder is on the computer.
MODELS_FOLDER = REPO_FOLDER / "models"

# Here we give this project its own Ollama port, so the code never talks to another Ollama server
# (the Ollama app or another project use the default port 11434).
OLLAMA_PORT = 11500
OLLAMA_ADDRESS = f"http://127.0.0.1:{OLLAMA_PORT}"

# Here we name the models with Ollama's own names. The judge is smaller than the debaters on purpose.
DEBATER_MODEL = "qwen3.5:9b"
JUDGE_MODEL = "qwen3.5:2b"


def create_project_structure() -> None:
    """Create the setup and tests folders and the empty data.py and run.py, keeping any that already exist."""
    for folder in [SETUP_FOLDER, TESTS_FOLDER]:
        # Here we create the folder only if it is missing; exist_ok leaves an existing folder untouched.
        folder.mkdir(exist_ok=True)
        print(f"Folder ready: {folder.name}/")

    for empty_file in EMPTY_FILES:
        # Here we create the file only if it is missing, so we never empty a file that already has code in it.
        if empty_file.exists():
            print(f"Already exists, left as it is: {empty_file.name}")
        else:
            empty_file.touch()
            print(f"Created empty file: {empty_file.name}")


def install_ticket_one_requirements() -> None:
    """Create the Python environment and install ticket 01's libraries, downloading only what is missing."""
    # Here we create the Python environment inside the repo, unless it already exists.
    if VIRTUAL_ENVIRONMENT_FOLDER.exists():
        print("Python environment already exists: .venv/")
    else:
        # Here we look for Python 3.12 ourselves, so this file works no matter which Python VS Code runs it with.
        python_3_12_program = shutil.which("python3.12")
        if python_3_12_program is None:
            print("Python 3.12 is not installed. Install it with: brew install python@3.12")
            return

        print("Creating the Python environment .venv/ with Python 3.12 ...")
        subprocess.run([python_3_12_program, "-m", "venv", str(VIRTUAL_ENVIRONMENT_FOLDER)], check=True)

    # Here we install the libraries in requirements.txt. pip skips any library that is already installed,
    # and --cache-dir keeps pip's downloads inside the repo instead of the home folder.
    pip_program = VIRTUAL_ENVIRONMENT_FOLDER / "bin" / "pip"
    subprocess.run(
        [str(pip_program), "install", "--cache-dir", str(PIP_CACHE_FOLDER), "-r", str(REQUIREMENTS_FILE)],
        check=True,
    )

    # Here we only check for Ollama: it is a program, not a Python library, and installing
    # system software is the owner's decision. Models are downloaded later, not here.
    if shutil.which("ollama"):
        print("Ollama is installed.")
    else:
        print("Ollama is not installed. Install it with: brew install ollama")


def print_next_step() -> None:
    """Remind the owner to point VS Code at the project's Python, so the play button uses it for every file."""
    print()
    print("Next step (once): point VS Code at the project's Python.")
    print('    Cmd+Shift+P -> "Python: Select Interpreter" -> choose .venv')
    print('    If .venv is not listed: "Enter interpreter path..." -> .venv/bin/python')


def model_is_downloaded(model_name: str) -> bool:
    """Return True if the model is already in models/, by looking for Ollama's small index file for it."""
    # Here we split an Ollama name like "qwen3.5:9b" into the model ("qwen3.5") and its size tag ("9b").
    model, size_tag = model_name.split(":")
    index_file = MODELS_FOLDER / "manifests" / "registry.ollama.ai" / "library" / model / size_tag
    return index_file.exists()


def ollama_environment() -> dict:
    """Return the settings Ollama needs to keep its models in models/ and use this project's port."""
    environment = dict(os.environ)
    # Here we tell Ollama to read and save models in this project's models/ folder.
    environment["OLLAMA_MODELS"] = str(MODELS_FOLDER)
    # Here we tell Ollama to use this project's port, both for the server and for `ollama pull`.
    environment["OLLAMA_HOST"] = f"127.0.0.1:{OLLAMA_PORT}"
    return environment


def download_models() -> None:
    """Download the debater and judge models into models/, skipping any model that is already there."""
    MODELS_FOLDER.mkdir(exist_ok=True)

    missing_models = [model for model in [DEBATER_MODEL, JUDGE_MODEL] if not model_is_downloaded(model)]
    if not missing_models:
        print(f"All models are already in models/: {DEBATER_MODEL}, {JUDGE_MODEL}")
        return

    if shutil.which("ollama") is None:
        print("Ollama is not installed. Install it with: brew install ollama")
        return

    # Here we start a temporary Ollama server that saves into models/, because `ollama pull` downloads
    # through a running server. Its messages go to a log file in models/.
    server_log = open(MODELS_FOLDER / "ollama-server.log", "a")
    server = subprocess.Popen(["ollama", "serve"], env=ollama_environment(), stdout=server_log, stderr=server_log)

    # Here we wait until the server answers before asking it to download anything.
    for _ in range(30):
        try:
            urllib.request.urlopen(OLLAMA_ADDRESS + "/api/version", timeout=2)
            break
        except OSError:
            time.sleep(1)

    for model_name in missing_models:
        print(f"Downloading {model_name} into models/ ...")
        subprocess.run(["ollama", "pull", model_name], env=ollama_environment(), check=True)

    # Here we stop the temporary server, so nothing is left running after the download.
    server.terminate()
    server.wait()

    # Here we add up the size of every file in models/, to show how much space the models use.
    models_size_in_bytes = sum(file.stat().st_size for file in MODELS_FOLDER.rglob("*") if file.is_file())
    print(f"Done. models/ now holds {models_size_in_bytes / 1e9:.1f} GB.")


def print_settings() -> None:
    """Print the settings every experiment uses: the models, the Ollama port and the project folders."""
    # Here we show folders relative to the project folder, so the lines stay short and readable.
    print()
    print("Project settings:")
    print(f"    Debater model:  {DEBATER_MODEL}  (downloaded: {model_is_downloaded(DEBATER_MODEL)})")
    print(f"    Judge model:    {JUDGE_MODEL}  (downloaded: {model_is_downloaded(JUDGE_MODEL)})")
    print(f"    Ollama server:  {OLLAMA_ADDRESS}")
    print(f"    Models folder:  {MODELS_FOLDER.relative_to(REPO_FOLDER)}/")
    print(f"    Python:         {VIRTUAL_ENVIRONMENT_FOLDER.relative_to(REPO_FOLDER)}/")
    print(f"    pip cache:      {PIP_CACHE_FOLDER.relative_to(REPO_FOLDER)}/")


if __name__ == "__main__":
    # This is how you will get started in terms of downloading the project requirements and setting up the models
    create_project_structure()
    install_ticket_one_requirements()
    print_next_step()

    # To download the models (about 9.3 GB, into models/), remove the # in front of the next line and press play.
    # download_models()

    print()
    print("To run any experiment in this project:")
    print("    1. First press play on setup/start_ollama_server.py")
    print("    2. Then run your experiments")
    print("    3. When you have finished everything, press play on setup/stop_ollama_server.py")

    # Here we show the settings every experiment uses.
    print_settings()
