"""Binary search: one model halves the run until one step is left, as in the Who&When paper (Zhang et al., ICML 2025,
arXiv 2505.00212, section 4.1 and appendix A.3). The prompt is the authors' own, word for word, from their code for local
models (github.com/ag2ai/Agents_Failure_Attribution, Automated_FA/Lib/local_model.py).

Everything in this file is built specifically for Visual Studio Code on a Mac.

How one run goes:
    The search starts with every step, Step 0 included. Each round, the model sees only the steps still in play,
    written as "agent: content" lines, and says whether the most critical mistake is in the upper half (the earlier
    steps, middle step included) or the lower half (the later steps). The chosen half is kept. When one step is left,
    that step is the answer. One call per round, so a run of n steps takes about log2(n) calls.

Where we differ from the authors' code (report these):
    - The line giving the correct answer is left out. Their code reads it from "ground_truth", but the hand-crafted
      files call it "groundtruth", so in their runs the line was empty anyway.
    - The model answers in JSON, {"half": "upper half"} or {"half": "lower half"}, and can give nothing else.
      Their code reads the two phrases out of free text.
    - A reply that is not valid JSON keeps the upper half, as their code does for an unclear reply. Their code stops
      the run when the model call itself fails.
    - Temperature and seed are this project's (0.7 and 42); their local models used 0.6.

How to use it:
    Press play on this file. It runs binary search on the pilot run (data/splits/pilot.json, run 36) with the live model
    and writes the log to runs/binary_search/<date>/run_<number>_<time>.md. If this project's Ollama server is not
    running, it starts it and stops it again at the end.
"""

from datetime import datetime
from pathlib import Path
import json
import sys

# Here we add the project folder to Python's search path, so this file can import runV2.py, data.py and settings.py
# when you press play on it from inside methods/.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
import data
import runV2
import settings


# ---------- The authors' prompt ----------
# Here we keep the authors' system prompt and template word for word, including their curly apostrophe in "user’s".
SystemPrompt = "You are a helpful assistant skilled in analyzing conversations."


def binary_search_prompt(question: str, segment: str, first_step: int, last_step: int, middle_step: int) -> str:
    """Write the authors' prompt for one round: the task, the segment, and the two halves to choose between."""
    return (
        "You are an AI assistant tasked with analyzing a segment of a multi-agent conversation. Multiple agents are "
        "collaborating to address a user query, with the goal of resolving the query through their collective dialogue.\n"
        "Your primary task is to identify the location of the most critical mistake within the provided segment. "
        "Determine which half of the segment contains the single step where this crucial error occurs, ultimately "
        "leading to the failure in resolving the user’s query.\n"
        f"The problem to address is as follows: {question}\n"
        f"Review the following conversation segment from step {first_step} to step {last_step}:\n\n{segment}\n\n"
        "Based on your analysis, predict whether the most critical error is more likely to be located in the upper "
        f"half (from step {first_step} to step {middle_step}) or the lower half (from step {middle_step + 1} to step "
        f"{last_step}) of this segment.\n"
        "Please simply output either 'upper half' or 'lower half'. You should not output anything else."
    )


# Here the model can only answer with one of the authors' two phrases.
AnswerFormat = {
    "type": "object",
    "properties": {
        "half": {"type": "string", "enum": ["upper half", "lower half"]},
    },
    "required": ["half"],
}


# ---------- Settings ----------
# Here binary search uses one model, the debater model. The qwen3.8 notebook changes the name before this file is imported.
Model = settings.DEBATER_MODEL

# Here we use this project's temperature and seed, so binary search is run the same way as the other methods.
Temperature = 0.7
Seed = 42

# Here we keep the authors' reply limit; the answer is only a few tokens.
ReplyLimitInTokens = 1024


# ---------- The method ----------
def run_binary_search(run: data.Trajectory, run_number: int, log_folder: Path) -> int:
    """Run binary search on one run, write its log, and return the one step left at the end."""
    log = []
    round_lines = []

    # Here every step is in play at the start, Step 0 included, as in the authors' code.
    first_step = 0
    last_step = len(run.steps) - 1
    round_number = 0

    while first_step < last_step:
        round_number += 1
        middle_step = middle_of(first_step, last_step)
        half, choice_text = ask_which_half(run, first_step, last_step, middle_step, log)
        range_text = f"steps {first_step} to {last_step}"

        # Here the upper half is the earlier steps, middle step included; the lower half is the later steps.
        if half == "upper half":
            last_step = middle_step
        else:
            first_step = middle_step + 1
        round_lines.append(f"Round {round_number}: {range_text}, {choice_text}, kept {first_step} to {last_step}")

    # Here the one step left is the answer, and we note which agent took it.
    answer = first_step
    extra_result_lines = round_lines + [f"Rounds: {round_number}", f"Agent at the answer: {run.steps[answer].agent}"]
    runV2.write_log(log, log_folder, "Binary search", run_number, run, answer, extra_result_lines)
    return answer


def middle_of(first_step: int, last_step: int) -> int:
    """Return the middle step of a segment, rounded down, as in the authors' code."""
    return first_step + (last_step - first_step) // 2


def ask_which_half(run: data.Trajectory, first_step: int, last_step: int, middle_step: int,
                   log: list) -> tuple[str, str]:
    """Ask the model which half holds the most critical mistake.
    Return the half to keep, and how it was chosen, for the log."""
    segment = segment_text(run, first_step, last_step)
    prompt = binary_search_prompt(run.question, segment, first_step, last_step, middle_step)

    # Here we pass no steps, because the segment is already in the prompt, written the authors' way.
    try:
        answer = runV2.send_to_ollama("binary search", Model, SystemPrompt, [], prompt, AnswerFormat,
                                      Temperature, Seed, log, reply_limit=ReplyLimitInTokens)
    except json.JSONDecodeError:
        # Here a broken reply still counts as a call (it is already in the log) and keeps the earlier half,
        # as the authors' code does for a reply it cannot read.
        return "upper half", "no usable reply (not valid JSON) so upper half"

    return answer["half"], answer["half"]


def segment_text(run: data.Trajectory, first_step: int, last_step: int) -> str:
    """Write the steps from first_step to last_step as the authors do: one "agent: content" line per step,
    with no step numbers."""
    segment_steps = run.steps[first_step:last_step + 1]
    return "\n".join(f"{step.agent}: {step.text}" for step in segment_steps)


if __name__ == "__main__":
    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(PROJECT_FOLDER / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server

    # Here we put today's logs in one folder per day: runs/binary_search/<date>/.
    log_folder = PROJECT_FOLDER / "runs" / "binary_search" / datetime.now().strftime("%Y-%m-%d")

    started_here = start_ollama_server()
    print(f"Start: {datetime.now():%H:%M:%S}")
    print("-------Starting binary search-------")
    # Here "try ... finally" makes sure the server we started is stopped even if something below fails.
    try:
        # Here we read the pilot run from data/splits/pilot.json (run 36).
        pilot_entry = json.loads((data.SPLITS_FOLDER / "pilot.json").read_text())[0]
        pilot_run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / pilot_entry["file"])

        # Here we run binary search on the pilot run; it writes its own log into log_folder.
        answer = run_binary_search(pilot_run, pilot_entry["number"], log_folder)
        print(f"Run {pilot_entry['number']}: answer = step {answer}, labelled Decisive step = {pilot_run.decisive_step}")
        print(f"Log folder: {log_folder}")
    finally:
        if started_here:
            stop_ollama_server()
    print("-------Finished binary search-------")
    print(f"End: {datetime.now():%H:%M:%S}")
