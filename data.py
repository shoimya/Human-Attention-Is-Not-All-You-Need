"""Everything about the data: download Who&When, remove bad runs, print a run, split into pilot and test,
and make a human review set.

Everything in this file is built specifically for Visual Studio Code on a Mac.

How to use it:
    Press play. It downloads the 58 Who&When runs into data/who_and_when/ (only missing files, about 4 MB),
    removes any run whose Decisive step does not exist, and prints run 1 (change run_to_print at the bottom).
    Two more steps are switched off at the bottom of this file; remove the # in front of one and press play:
      - split_pilot_and_test   writes data/splits/pilot.json (1 random run) and test.json (all runs)
      - human_review_split     writes 5 random runs without their labels to data/human_review/ for people to fill in

Why the runs are kept as JSON files:
    - One run is one plain-text file (17.json is run 17), so you can open any run in VS Code and read it.
    - Every part has a name: "history" is the list of steps in order, each step has a "role" (the agent) and
      "content" (what it wrote), and the label sits in separate fields ("mistake_step", "mistake_agent",
      "mistake_reason"). Because the label is apart from the steps, we can hide it (human review) or
      score against it without touching the steps.
    - The step number is simply the step's position in "history", counting from 0, the same way the label counts.
    - Python reads JSON with its built-in json module, so no extra library is needed.
    - A JSON file looks shorter than the run really is: line breaks inside a step's text are stored as the two
      characters \n, so each step sits on one long line. Nothing is lost; printing a run shows the real line breaks.

How the models and methods read the runs:
    - Only this file reads the JSON files. read_who_and_when_file() turns each one into a Trajectory
      (the steps, plus the label kept in its own fields), and everything else in the project works with Trajectories.
    - A method (the prover-estimator debate first, in ticket 04) receives one Trajectory, turns the steps it needs
      into plain text in the same "--- Step 12 | WebSurfer ---" form that print_trajectory() uses, and sends
      that text to the models through the Ollama server. The models never see the JSON file itself.
    - The label (decisive_step, decisive_agent, decisive_reason) is never put in the text a model reads. It is used
      only afterwards, to score whether the method picked the right step.
"""

import json
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Here we find the project folder: the folder that holds this file.
PROJECT_FOLDER = Path(__file__).resolve().parent

# Here we name the data folders. All of them live inside the project.
DATA_FOLDER = PROJECT_FOLDER / "data"
WHO_AND_WHEN_FOLDER = DATA_FOLDER / "who_and_when"    # the downloaded runs (not pushed to GitHub)
SPLITS_FOLDER = DATA_FOLDER / "splits"                # pilot.json and test.json (pushed)
HUMAN_REVIEW_FOLDER = DATA_FOLDER / "human_review"    # the files people fill in (pushed)

# Here we say how many runs a human review set has.
NUMBER_OF_HUMAN_REVIEW_RUNS = 5

# Here we say where Who&When's Hand-Crafted runs are on Hugging Face: files 1.json to 58.json.
# "%26" is how "&" in the folder name "Who&When" is written in a web address.
WHO_AND_WHEN_ADDRESS = "https://huggingface.co/datasets/Kevin355/Who_and_When/resolve/main/Who%26When/Hand-Crafted/"
NUMBER_OF_WHO_AND_WHEN_RUNS = 58


@dataclass
class Step:
    """One step of an agent run: its number (counting from 0), who acted, and what they wrote."""

    index: int
    agent: str
    text: str


@dataclass
class Trajectory:
    """One failed agent run, with the step where it went wrong (the Decisive step)."""

    file_name: str          # the downloaded file it came from, for example "17.json"
    id: str                 # Who&When's ID for the task (question_ID)
    question: str           # the task the agents were asked to solve
    steps: list[Step]       # every step of the run, in order
    decisive_step: int      # the label: the number of the step where the run went wrong
    decisive_agent: str     # the label: the agent that made that mistake
    decisive_reason: str    # the label: why the annotators chose that step


def set_up_data_folder() -> None:
    """Create the folders for the downloaded runs and for the split files, keeping any that already exist."""
    for folder in [WHO_AND_WHEN_FOLDER, SPLITS_FOLDER]:
        # Here we create the folder (and data/ above it) only if it is missing.
        folder.mkdir(parents=True, exist_ok=True)


def download_who_and_when() -> list[Trajectory]:
    """Download the 58 Who&When Hand-Crafted runs into data/who_and_when/ (only missing files) and return them."""
    # Here we make sure the folder exists, so this function also works when called on its own.
    set_up_data_folder()

    all_runs = []
    number_of_new_downloads = 0
    # Here we go through the files in number order (1, 2, ... 58), so the runs are in the same order on every computer.
    for file_number in range(1, NUMBER_OF_WHO_AND_WHEN_RUNS + 1):
        file_name = f"{file_number}.json"
        file_path = WHO_AND_WHEN_FOLDER / file_name

        # Here we download the file only if it is not on disk yet.
        if not file_path.exists():
            # Here we download under a temporary name first and rename it only when the download is complete.
            # If the download breaks off, no half-written file is left under the real name for the next run to trust.
            partial_file_path = file_path.with_name(file_name + ".partial")
            urllib.request.urlretrieve(WHO_AND_WHEN_ADDRESS + file_name, partial_file_path)
            partial_file_path.rename(file_path)
            number_of_new_downloads += 1

        all_runs.append(read_who_and_when_file(file_path))

    print(f"Who&When: {len(all_runs)} runs in data/who_and_when/ ({number_of_new_downloads} newly downloaded).")
    return all_runs


def read_who_and_when_file(file_path: Path) -> Trajectory:
    """Read one downloaded Who&When file and turn it into a Trajectory."""
    # Here we read the JSON file into a Python dictionary, for example run["question"].
    run = json.loads(file_path.read_text())

    # Here we number the steps from 0, because Who&When's mistake_step counts from 0.
    steps = [
        Step(index=step_number, agent=step["role"], text=step["content"])
        for step_number, step in enumerate(run["history"])
    ]
    return Trajectory(
        file_name=file_path.name,
        id=run["question_ID"],
        question=run["question"],
        steps=steps,
        # Here we turn mistake_step into a number, because Who&When stores it as text (for example "12").
        decisive_step=int(run["mistake_step"]),
        decisive_agent=run["mistake_agent"],
        decisive_reason=run["mistake_reason"],
    )


def remove_bad_runs(all_runs: list[Trajectory]) -> list[Trajectory]:
    """Remove every run whose Decisive step does not exist in the run, printing the run and why it was removed."""
    usable_runs = []
    for run in all_runs:
        last_step = len(run.steps) - 1

        # Here we keep the run only if its labelled Decisive step is one of its steps (0 to last_step).
        if 0 <= run.decisive_step <= last_step:
            usable_runs.append(run)
        else:
            print_steps_and_label(run)
            print(f"REMOVED {run.file_name}: the label says the Decisive step is step {run.decisive_step}, "
                  f"but this run only has steps 0 to {last_step}, so that step does not exist.\n")

    print(f"Kept {len(usable_runs)} of {len(all_runs)} runs ({len(all_runs) - len(usable_runs)} removed).")
    return usable_runs


def print_trajectory(usable_runs: list[Trajectory], run_number: int) -> None:
    """Print one run, chosen by its number (1 = the first run), with its steps first and its label last."""
    # Here we check the number exists; people count from 1, so the allowed numbers are 1 to the number of runs.
    if not 1 <= run_number <= len(usable_runs):
        print(f"There is no run number {run_number}. Choose a number from 1 to {len(usable_runs)}.")
        return

    # Here we turn the run number (counting from 1) into a list position (counting from 0).
    print_steps_and_label(usable_runs[run_number - 1])


def split_pilot_and_test(usable_runs: list[Trajectory], splits_folder: Path = SPLITS_FOLDER) -> None:
    """Pick one random run as the pilot, then replace the old split files: pilot.json (1 run) and test.json (all runs)."""
    # Here we pick the pilot at random: any run number from 1 to the number of runs.
    pilot_number = random.randint(1, len(usable_runs))

    # Here we describe each run by its number, ID and file name, not by a copy of the whole run.
    all_entries = [
        {"number": run_number, "id": run.id, "file": run.file_name}
        for run_number, run in enumerate(usable_runs, start=1)
    ]
    pilot_entries = [all_entries[pilot_number - 1]]

    # Here we delete the current split files, then write the new ones.
    splits_folder.mkdir(parents=True, exist_ok=True)
    pilot_file = splits_folder / "pilot.json"
    test_file = splits_folder / "test.json"
    pilot_file.unlink(missing_ok=True)
    test_file.unlink(missing_ok=True)
    pilot_file.write_text(json.dumps(pilot_entries, indent=2))
    test_file.write_text(json.dumps(all_entries, indent=2))

    print(f"New split: pilot = run {pilot_number} ({pilot_entries[0]['file']}), test = all {len(all_entries)} runs.")


def human_review_split(usable_runs: list[Trajectory], review_folder: Path = HUMAN_REVIEW_FOLDER) -> None:
    """Write 5 random runs, without their labels, as files a person fills in. Refuses unless the folder is empty."""
    review_folder.mkdir(parents=True, exist_ok=True)

    # Here we refuse to write anything if review files are already there, so typed answers are never lost.
    if folder_has_visible_files(review_folder):
        print(f"{review_folder} is not empty, so no new review files were written. "
              "Move or delete the files in it first, then run this again.")
        return

    # Here we pick 5 different run numbers from 1 to the number of runs; sample never picks the same number twice.
    review_numbers = sorted(random.sample(range(1, len(usable_runs) + 1), NUMBER_OF_HUMAN_REVIEW_RUNS))

    for run_number in review_numbers:
        # Here we turn the run number (counting from 1) into a list position (counting from 0).
        write_human_review_file(usable_runs[run_number - 1], run_number, review_folder)

    print(f"Human review set written to {review_folder}: runs {review_numbers}.")


def folder_has_visible_files(folder: Path) -> bool:
    """Return True if the folder holds any file or folder whose name does not start with a dot."""
    # Here we ignore hidden files such as .DS_Store, which macOS adds to any folder opened in Finder.
    return any(not path.name.startswith(".") for path in folder.iterdir())


def write_human_review_file(run: Trajectory, run_number: int, review_folder: Path) -> None:
    """Write one run as a Markdown file with its steps and an empty answer section, but without its label."""
    lines = [
        f"# Human review: run {run_number} ({run.file_name})",
        "",
        "Read the steps, find the step where the run went wrong, and fill in the answer section at the bottom.",
        "Note the time when you start and when you finish.",
        "",
        f"**Question:** {run.question}",
        "",
    ]

    for step in run.steps:
        lines.append(f"--- Step {step.index} | {step.agent} ---")
        lines.append(step.text)
        lines.append("")

    # Here we add the empty answer section instead of the label.
    lines += [
        "## Your answer",
        "",
        "- Decisive step (number):",
        "- Agent:",
        "- Minutes taken:",
        "- How sure are you (low / medium / high):",
        "- Notes:",
        "",
    ]

    # Here we join the lines into one text, one line each, and save it as run_<number>.md.
    review_file = review_folder / f"run_{run_number}.md"
    review_file.write_text("\n".join(lines))


def print_steps_and_label(run: Trajectory) -> None:
    """Print a run step by step, and only then its label, so a reader can look for the mistake first."""
    print("=" * 80)
    print(f"{run.file_name} | QUESTION: {run.question}\n")
    for step in run.steps:
        print(f"--- Step {step.index} | {step.agent} ---")
        print(step.text)
        print()

    # Here we print the label last, so you can find the mistake yourself before seeing the answer.
    print("-" * 80)
    print(f"LABEL: Decisive step {run.decisive_step}, by {run.decisive_agent}")
    print(f"WHY:   {run.decisive_reason}")
    print("=" * 80)


if __name__ == "__main__":
    # Here we create data/who_and_when/ and data/splits/ if they are missing.
    set_up_data_folder()

    # Here we download any missing runs and read all 58 of them.
    all_runs = download_who_and_when()

    # Here we keep only the runs whose Decisive step exists (all 58 with the JSON files).
    usable_runs = remove_bad_runs(all_runs)

    # Here we choose which run to print: change this number to any run from 1 to the number of usable runs (58).
    run_to_print = 1
    print_trajectory(usable_runs, run_to_print)

    # To make a new pilot and test split, remove the # in front of the next line and press play.
    # This replaces the current split files in data/splits/.
    # split_pilot_and_test(usable_runs)

    # To make a human review set (5 random runs without their labels, in data/human_review/),
    # remove the # in front of the next line and press play. It only works when data/human_review/ is empty.
    # human_review_split(usable_runs)
