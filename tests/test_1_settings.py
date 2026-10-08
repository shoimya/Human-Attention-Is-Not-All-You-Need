"""Tests for settings.py and the start and stop scripts: confirm the project has everything ticket 01 set up.

Press play on this file to run all its tests.
"""

import json
import shutil
import sys
import urllib.request
from pathlib import Path

# Here we add the project folder and the setup folder to Python's search path, so this file can import
# settings.py and the start and stop scripts when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "setup"))

import pytest

import settings
from start_ollama_server import ollama_server_is_running, start_ollama_server
from stop_ollama_server import stop_ollama_server


def test_every_storage_folder_is_inside_the_project():
    """The models, the Python environment and pip's cache must all live inside the project folder."""
    storage_folders = [settings.MODELS_FOLDER, settings.VIRTUAL_ENVIRONMENT_FOLDER, settings.PIP_CACHE_FOLDER]

    for folder in storage_folders:
        # Here we check that the project folder is one of the folder's parents.
        assert PROJECT_FOLDER in folder.parents, f"{folder} is outside the project"


def test_ollama_port_is_not_the_default_port():
    """This project has its own Ollama server, so it must not use Ollama's default port 11434."""
    assert settings.OLLAMA_PORT != 11434


def test_ollama_keeps_its_models_in_the_project_and_uses_this_projects_port():
    """Ollama must be told to use models/ inside the project and to listen on 127.0.0.1:11500."""
    environment = settings.ollama_environment()

    assert Path(environment["OLLAMA_MODELS"]) == PROJECT_FOLDER / "models"
    assert environment["OLLAMA_HOST"] == "127.0.0.1:11500"


def test_project_folders_and_files_exist():
    """The setup creates these folders and files; the start and stop scripts must be in setup/."""
    expected_paths = [
        PROJECT_FOLDER / "setup",
        PROJECT_FOLDER / "tests",
        PROJECT_FOLDER / "data.py",
        PROJECT_FOLDER / "run.py",
        PROJECT_FOLDER / "setup" / "start_ollama_server.py",
        PROJECT_FOLDER / "setup" / "stop_ollama_server.py",
    ]

    for path in expected_paths:
        assert path.exists(), f"Missing: {path.relative_to(PROJECT_FOLDER)}"


def test_python_environment_uses_python_3_12():
    """The project's Python environment must be Python 3.12, the version the project is built for."""
    # Here we read the version from the environment's own settings file, which venv writes when it is created.
    environment_settings = (settings.VIRTUAL_ENVIRONMENT_FOLDER / "pyvenv.cfg").read_text()

    assert "version = 3.12" in environment_settings


def test_ollama_is_installed():
    """Ollama must be installed on this computer, because it serves the models."""
    assert shutil.which("ollama") is not None


def test_both_models_are_downloaded():
    """The debater and judge models must both be in models/."""
    assert settings.model_is_downloaded(settings.DEBATER_MODEL)
    assert settings.model_is_downloaded(settings.JUDGE_MODEL)


def test_a_model_that_was_never_downloaded_is_reported_missing():
    """The download check must say "no" for a model that is not in models/, or it would skip real downloads."""
    assert not settings.model_is_downloaded("qwen3.5:999b")


def test_models_and_environment_are_kept_off_github():
    """The models (about 9 GB) and the Python environment must be listed in .gitignore."""
    ignored_lines = (PROJECT_FOLDER / ".gitignore").read_text().splitlines()

    assert "models/" in ignored_lines
    assert ".venv/" in ignored_lines


def test_start_and_stop_scripts_start_and_stop_this_projects_server():
    """Starting gives a server that lists both models; stopping leaves no server on this project's port."""
    # Here we skip the test if the server is already running, so a test never stops a server you are using.
    if ollama_server_is_running():
        pytest.skip("This project's Ollama server is already running; stop it first to run this test.")

    start_ollama_server()
    assert ollama_server_is_running()

    # Here we ask the running server which models it can see in models/.
    tags_response = urllib.request.urlopen(settings.OLLAMA_ADDRESS + "/api/tags", timeout=10)
    model_names = [model["name"] for model in json.load(tags_response)["models"]]
    assert settings.DEBATER_MODEL in model_names
    assert settings.JUDGE_MODEL in model_names

    stop_ollama_server()
    assert not ollama_server_is_running()


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
