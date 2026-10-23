"""One-shot: one model reads the whole run and names the step where it first went wrong, several times; the step
named most often is the answer. The rules are in informatics.md, section 3.

Everything in this file is built specifically for Visual Studio Code on a Mac.

How to use it:
    Press play on this file. It runs one-shot on the pilot run (data/splits/pilot.json) with the live model and
    writes the log to runs/one_shot/<date>/run_<number>_<time>.md. If this project's Ollama server is not running,
    it starts it and stops it again at the end.

Notes from paper:
GPT-4-turbo, GPT-4o-mini, Llama-3.1-8B and 70B, and Qwen-2.5-7B and 72B, on hand-crafted logs only.
at best 14% accuracy

and we are doing DEBATER_MODEL = "qwen3.5:9b" JUDGE_MODEL = "qwen3.5:2b"
"""

from ast import For
from datetime import datetime
import json
import sys
import time
from pathlib import Path

# Here we add the project folder to Python's search path, so this file can import runV2.py, data.py and settings.py
# when you press play on it from inside methods/.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))

import data
import runV2
import settings

# Here we set the role's rules. The run's task question is already step 0, so it is not added again.
# version 1
# SystemPrompt = (
#     "You review a failed run of a team of AI agents. The run is given as numbered steps, starting at Step 0. "
#     "Find the first step where the run went wrong: the earliest step where, had that step been done right, "
#     "the run would not have failed. when generating this answer you must produce your chain of thought for why you are choosing that step."
#     "Answer only in JSON: the step number and one sentence saying why."
# )
# version 3
SystemPrompt = (
    "You review a failed run of a team of agents. The run is given as numbered steps, starting at Step 0, "
    "which is the task. "
    "Find the decisive step: the step where, had that step been done right, the run would not have failed. "
    "A later step that only follows from an earlier mistake is not the decisive step. "
    "Answer only in JSON with three fields, in this order. "
    "reasoning: Think step by step go through the steps in order, note in a few words each step that looks wrong, and say whether the failure follows from it; "
    "stop once you have found the decisive step. "
    "step: the decisive step's number. "
    "reason: one sentence saying what went wrong at that step."
)

# Here we set how many times the model is asked. Once the experiments show the debate's average number of calls,
# that average replaces this number.
DefaultNoOfCalls = 10
# Here we set the question that comes after the steps.
question = "Which step is the first one where the run went wrong? Give its step number and one sentence saying why."

# Here we fix the randomness for now; both can be changed later.
Temperature = 0.7
Seed = 41

AnswerFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "step": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["reasoning", "step", "reason"],
}

def run_one_shot(run: data.Trajectory, run_number: int, log_folder: Path) -> int | None:
    """Run one-shot on one run, write its log into log_folder, and return the answer (None if no call gave a step)."""
    log = []
    votes = []
    vote_lines = []

    for call_number in range(1, DefaultNoOfCalls + 1):
        # Here we ask the model once; ask_for_one_step() tells us the step, or why this call gets no vote.
        call_seed = Seed + call_number #lets vary the seed for each call as we need some randomness
        #call_seed = Seed #to test a permanent seed

        step, vote_line = ask_for_one_step(run, log, call_seed)
        votes.append(step)
        vote_lines.append(f"Call {call_number}: {vote_line}")

        # Here we stop early if, after half of the calls, every call named the same step (rule 7).
        if call_number == DefaultNoOfCalls // 2 and all_votes_agree(votes):
            break

    # Here we pick the answer from the valid votes; with no valid vote there is no answer.
    valid_votes = [step for step in votes if step is not None]
    answer = most_named_step(valid_votes) if valid_votes else None

    # Here we add one-shot's own lines to the log's result: the calls allowed and used, and every call's vote.
    calls_used = len(votes)
    extra_result_lines = [
        f"Calls allowed: {DefaultNoOfCalls}",
        f"Calls used: {calls_used}",
        f"Stopped early: {'yes' if calls_used < DefaultNoOfCalls else 'no'}",
    ] + vote_lines
    runV2.write_log(log, log_folder, "One-shot", run_number, run, answer, extra_result_lines)
    return answer


def ask_for_one_step(run: data.Trajectory, log: list, dynamicseed: int) -> tuple[int | None, str]:
    """Ask the debater model once for the step; return the step and a line for the log, or None and why it has no vote."""
    try:
        answer = runV2.send_to_ollama("one-shot", settings.DEBATER_MODEL, SystemPrompt, run.steps, question,
                                      AnswerFormat, Temperature, dynamicseed, log)
    except json.JSONDecodeError:
        # Here a reply that is not valid JSON still counts as a call (it is already in the log), but gets no vote.
        return None, "no vote, the reply was not valid JSON"

    # Here a step that is not in the run gets no vote.
    if not 0 <= answer["step"] < len(run.steps):
        return None, f"no vote, step {answer['step']} is not in the run"
    return answer["step"], f"step {answer['step']} ({answer['reason']})"


def most_named_step(votes: list[int]) -> int:
    """Return the step named most often; if several steps tie, return the earliest one."""
    # Here we count how many times each step was named.
    votes_per_step = {step: votes.count(step) for step in votes}
    highest_count = max(votes_per_step.values())
    # Here we keep every step with the highest count and pick the earliest, like the first-error rule.
    tied_steps = [step for step, count in votes_per_step.items() if count == highest_count]
    return min(tied_steps)


def all_votes_agree(votes: list[int | None]) -> bool:
    """Return True if every call named the same step. A call with no valid answer (None) breaks the streak."""
    # Here we stop early only if there is no missing vote and only one step was named.
    return None not in votes and len(set(votes)) == 1


if __name__ == "__main__":
    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(PROJECT_FOLDER / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server
    
   
    
    log_folder = PROJECT_FOLDER / "runs" / "one_shot" / time.strftime("%Y-%m-%d")

    started_here = start_ollama_server()
    print("start - " + str(datetime.now()))

    # # For the pilot run and testing one example
    # try:
    #     pilot_entry = json.loads((data.SPLITS_FOLDER / "5_local.json").read_text())[0]
    #     pilot_run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / pilot_entry["file"])

    #     answer = run_one_shot(pilot_run, pilot_entry["number"], log_folder)
    #     print(f"Run {pilot_entry['number']}: answer = step {answer}, labelled Decisive step = {pilot_run.decisive_step}")
    #     print(f"Log folder: {log_folder}")
    # finally:
    #     if started_here:
    #         stop_ollama_server()



    
    split_file_name = "5_local.json"
    try:
        split_entries = json.loads((data.SPLITS_FOLDER / split_file_name).read_text())

        # Here we run one-shot on every run in the split, one after the other; each run gets its own log.
        for entry in split_entries:
            run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / entry["file"])
            answer = run_one_shot(run, entry["number"], log_folder)
            print(f"Run {entry['number']}: answer = step {answer}, labelled Decisive step = {run.decisive_step}")
        print(f"Log folder: {log_folder}")
    finally:
        if started_here:
            stop_ollama_server()

    print("end - " + str(datetime.now()))