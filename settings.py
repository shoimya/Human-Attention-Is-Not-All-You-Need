"""All project settings in one place. Every folder the project writes to lives inside this repo."""

import os
from dataclasses import dataclass
from pathlib import Path

# Here we find the repo folder: the folder that holds this file.
REPO_FOLDER = Path(__file__).resolve().parent

# Here we keep every downloaded or cached file together in one folder inside the repo.
CACHE_FOLDER = REPO_FOLDER / ".cache"


@dataclass
class Settings:
    """The settings one run of the project uses."""

    pip_cache_folder: Path
    huggingface_cache_folder: Path
    ollama_models_folder: Path
    runs_folder: Path
    ollama_port: int
    debater_model: str
    judge_model: str


def load_settings() -> Settings:
    """Return the project settings, with every storage folder inside the repo."""
    settings = Settings(
        pip_cache_folder=CACHE_FOLDER / "pip",
        huggingface_cache_folder=CACHE_FOLDER / "huggingface",
        ollama_models_folder=CACHE_FOLDER / "ollama-models",
        runs_folder=REPO_FOLDER / "runs",
        # Here we give this project its own Ollama port, so it never shares a server with another project.
        ollama_port=11500,
        # Here we pick the models: the judge is smaller than the debaters on purpose.
        debater_model="qwen3.5:9b",
        judge_model="qwen3.5:2b",
    )
    point_huggingface_cache_into_repo(settings)
    return settings


def point_huggingface_cache_into_repo(settings: Settings) -> None:
    """Make Hugging Face download into the repo instead of the home folder."""
    # Here we set HF_HOME, the variable Hugging Face reads to decide where its files go.
    # It must be set before any Hugging Face library is imported, which is why loading the settings does it.
    os.environ["HF_HOME"] = str(settings.huggingface_cache_folder)


if __name__ == "__main__":
    # Here we load the settings on one visible line, so you can step over it in the debugger.
    settings = load_settings()

    # Here we print one setting per line, so the output is easy to read.
    for setting_name, setting_value in vars(settings).items():
        print(f"{setting_name}: {setting_value}")
