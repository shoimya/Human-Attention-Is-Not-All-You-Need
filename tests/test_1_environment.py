"""Tests for the project environment: everything this project stores stays inside the repo,
and its Ollama server is separate from any other project's."""

import os
import sys
from pathlib import Path

# Here we add the repo folder to Python's search path, so this file can import settings.py
# from the folder above, whether it runs through pytest or on its own.
REPO_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_FOLDER))

import pytest

from settings import load_settings
from setup.start_model_server import model_server_environment


def test_every_storage_folder_is_inside_the_repo():
    """Caches, models and run logs must all live inside the repo on the SSD, never in the home folder."""
    settings = load_settings()

    storage_folders = [
        settings.pip_cache_folder,
        settings.huggingface_cache_folder,
        settings.ollama_models_folder,
        settings.runs_folder,
    ]

    for folder in storage_folders:
        # Here we check that the repo folder is one of the folder's parents.
        assert REPO_FOLDER in folder.parents, f"{folder} is outside the repo"


def test_ollama_port_is_not_the_default_port():
    """This project runs its own Ollama server, so it must not share Ollama's default port 11434 with other projects."""
    settings = load_settings()

    assert settings.ollama_port != 11434


def test_loading_settings_points_the_huggingface_cache_into_the_repo(monkeypatch):
    """Hugging Face reads HF_HOME to decide where downloads go, so loading the settings must point it into the repo."""
    # Here we remove any existing HF_HOME, so the test shows that load_settings sets it.
    monkeypatch.delenv("HF_HOME", raising=False)

    load_settings()

    huggingface_home = Path(os.environ["HF_HOME"])
    assert REPO_FOLDER in huggingface_home.parents


def test_model_server_keeps_its_models_in_the_repo_and_listens_on_its_own_port():
    """This project's Ollama server must store models inside the repo and listen only on port 11500."""
    settings = load_settings()

    server_environment = model_server_environment(settings)

    models_folder = Path(server_environment["OLLAMA_MODELS"])
    assert REPO_FOLDER in models_folder.parents
    assert server_environment["OLLAMA_HOST"] == "127.0.0.1:11500"


if __name__ == "__main__":
    # Here we run the tests in this file when it is started on its own (Debug or `python <file>`).
    pytest.main([__file__, "-v"])
