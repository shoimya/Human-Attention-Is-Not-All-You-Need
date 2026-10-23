'''
The paper states the method to be as following:
Proposer: reads the whole failed run and names the step where things went wrong, with a short reason.
Critic: reads the whole run and the proposer’s answer. It checks that answer and says whether it agrees or disagrees, pointing to specific steps and quotes as evidence. It does not reply again after this.
Judge: reads the whole run, the proposer’s answer, and the critic’s response. It checks their claims against the run itself, then decides whether the proposer’s step is correct or incorrect.
There is no back-and-forth: one answer, one critique, one decision.

-------------------------

We had to modify this approach a little bit because in their approach, they're just seeing whether or not the judge is able to understand and give the correct verdict in our study. We will actually have to pick a step.
Proposer: reads the whole failed run and names the one step where things went wrong, with a short reason. This is the same as in the paper.

Critic: reads the whole run and the proposer’s answer, and checks it. If it agrees, it says so and gives evidence. If it disagrees, it names the step it thinks is really responsible, again with evidence from the run.

Judge: reads the whole run and both answers, and checks their evidence against the run. It then picks the final step, either the proposer’s or the critic’s, and explains why. It also gives a confidence score showing how sure it is.
'''

from datetime import datetime
from pathlib import Path
import sys
import json


# Here we add the project folder to Python's search path, so this file can import runV2.py, data.py and settings.py
# when you press play on it from inside methods/.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
import settings
import runV2
import data

# ---------- Proposer (strong model) ----------
ProposerPrompt = (
    "You review a failed run of a team of agents. The run is given as numbered steps, starting at Step 0, "
    "which is the task. "
    "Find the decisive step: the step where, had that step been done right, the run would not have failed. "
    "A later step that only follows from an earlier mistake is not the decisive step. "
    "Use only what is in the run; quote it where it matters. "
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step. Go through the steps in order, note in a few words each step that looks wrong, "
    "and say whether the failure follows from it; stop once you have found the decisive step. "
    "step: the decisive step's number. "
    "reason: one sentence saying what went wrong at that step."
    "Remember think step by step before giving your final answer."
)

ProposerFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "step": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["reasoning", "step", "reason"],
}

ProposerQuestion = "Which step is the first one where the run went wrong? Give its step number and one sentence saying why."


# ---------- Critic (same strong model, separate call) ----------
CriticPrompt = (
    "You review another reviewer's claim about a failed run of a team of agents. The run is given as numbered steps, "
    "starting at Step 0, which is the task. "
    "The claim names one step as the decisive step: the step where, had that step been done right, the run would not "
    "have failed. A later step that only follows from an earlier mistake is not the decisive step. "
    "Check this one claim against the run. "
    "Disagree if the run shows the claim is wrong: the mistake already happened at an earlier step, "
    "the claimed step was actually done right, or the claim misreads what the run says. "
    "If you disagree, name the step you think is the decisive step. "
    "Agree if the run supports the claim. "
    "Give evidence a reader can check: quote the run and name step numbers. Do not argue from general plausibility. "
    "Answer only in JSON with four fields, in this order. "
    "reasoning: think step by step. Check the claimed step against the run, then check the steps before it for an "
    "earlier mistake that caused the failure. "
    "stance: AGREE or DISAGREE. "
    "step: if you disagree, the step you think is the decisive step; if you agree, the claimed step. "
    "evidence: two to four sentences with the quotes and step numbers that support your stance."
    "Remember think step by step before giving your final answer."
)

CriticFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "stance": {"type": "string", "enum": ["AGREE", "DISAGREE"]},
        "step": {"type": "integer"},
        "evidence": {"type": "string"},
    },
    "required": ["reasoning", "stance", "step", "evidence"],
}

# ---------- Judge, single critique (weak model) ----------
JudgePrompt = (
    "You decide which of two answers about a failed run of a team of agents names the decisive step. "
    "The run is given as numbered steps, starting at Step 0, which is the task. "
    "The decisive step is the step where, had that step been done right, the run would not have failed. "
    "A later step that only follows from an earlier mistake is not the decisive step. "
    "You are given the proposer's step with its reason, and the critic's step with its evidence. "
    "Both may be wrong. Treat what they say as claims to check, not as facts. "
    "Look up every step and quote they cite in the run and confirm it yourself before you decide. "
    "Answer only in JSON with four fields, in this order. "
    "reasoning: think step by step. Check the proposer's reason against the run, then check the critic's evidence "
    "against the run, and say which holds up. "
    "winner: PROPOSER if the proposer's step is the decisive step, CRITIC if the critic's step is. "
    "reason: one sentence saying why you chose that step. "
    "confidence: a number from 0 to 1 saying how sure you are that the chosen step is the decisive step."
    "Remember think step by step before giving your final answer."

)


JudgeFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "winner": {"type": "string", "enum": ["PROPOSER", "CRITIC"]},
        "reason": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["reasoning", "winner", "reason", "confidence"],
}


# ---------- Settings ----------
# Here we map each role to its model: the proposer and the critic are the strong debater, the judge is weaker.
ProposerModel = settings.DEBATER_MODEL
CriticModel = settings.DEBATER_MODEL
JudgeModel = settings.JUDGE_MODEL

# Here we set how many rounds to run. One round uses 2 calls when the critic agrees, 3 when the judge must decide.
NumberOfRounds = 3

# Here we fix the randomness; each round adds its round number to the base seed.
Temperature = 0.7
Seed = 41


# ---------- The method ----------
# Here we reuse one-shot's vote, so both methods choose their answer the same way: the step named most often,
# and the earliest step if several tie.
from one_shot import most_named_step


def run_single_critique(run: data.Trajectory, run_number: int, log_folder: Path) -> int | None:
    """Run single critique on one run for NumberOfRounds rounds, write its log, and return the step chosen
    most often (None if no round chose a valid step)."""
    log = []
    chosen_steps = []
    round_lines = []

    for round_number in range(1, NumberOfRounds + 1):
        # Here we give each round its own seed, so rounds can differ but repeat exactly when run again.
        round_seed = Seed + round_number
        chosen_step, round_line = run_one_round(run, log, round_seed)
        chosen_steps.append(chosen_step)
        round_lines.append(f"Round {round_number}: {round_line}")

    # Here we vote over the rounds that chose a valid step; with no valid step there is no answer.
    valid_steps = [step for step in chosen_steps if step is not None]
    answer = most_named_step(valid_steps) if valid_steps else None

    # Here we add single critique's own lines to the log's result: the number of rounds and what each round chose.
    extra_result_lines = [f"Rounds: {NumberOfRounds}"] + round_lines
    runV2.write_log(log, log_folder, "Single critique", run_number, run, answer, extra_result_lines)
    return answer


def run_one_round(run: data.Trajectory, log: list, seed: int) -> tuple[int | None, str]:
    """One round: the proposer names a step, the critic checks it, and the judge decides only if they disagree.
    Return the round's step and a line for the log, or None and why the round has no step."""
    # Here the proposer reads the whole run and names a step.
    claim = ask_role("proposer", ProposerModel, ProposerPrompt, run, ProposerQuestion, ProposerFormat, seed, log)
    if claim is None:
        return None, "no step, the proposer's reply was not valid JSON"
    if not step_is_in_run(claim["step"], run):
        return None, f"no step, the proposer's step {claim['step']} is not in the run"

    # Here the critic reads the whole run and the proposer's step and reason, then agrees or names its own step.
    critique = ask_role("critic", CriticModel, CriticPrompt, run, critic_question(claim), CriticFormat, seed, log)
    if critique is None:
        return None, f"no step, the critic's reply was not valid JSON (proposer said {claim['step']})"

    # Here we stop when the critic agrees: only one step is on the table, so the judge has nothing to choose.
    if critique["stance"] == "AGREE":
        return claim["step"], f"step {claim['step']} (critic agreed)"
    if not step_is_in_run(critique["step"], run):
        return None, f"no step, the critic's step {critique['step']} is not in the run"

    # Here the judge reads the whole run and both answers, and picks the proposer's step or the critic's.
    decision = ask_role("judge", JudgeModel, JudgePrompt, run, judge_question(claim, critique), JudgeFormat, seed, log)
    if decision is None:
        return None, f"no step, the judge's reply was not valid JSON (proposer {claim['step']}, critic {critique['step']})"

    # Here we take the step of whichever side the judge chose.
    chosen_step = claim["step"] if decision["winner"] == "PROPOSER" else critique["step"]
    round_line = (f"step {chosen_step} (proposer {claim['step']}, critic {critique['step']}, "
                  f"judge chose {decision['winner']}, confidence {decision['confidence']})")
    return chosen_step, round_line


# ---------- Small helpers ----------
def ask_role(role: str, model: str, system_prompt: str, run: data.Trajectory, question: str,
             answer_format: dict, seed: int, log: list) -> dict | None:
    """Ask one role once and return its JSON answer, or None if the reply was not valid JSON (it still counts as a call)."""
    try:
        return runV2.send_to_ollama(role, model, system_prompt, run.steps, question, answer_format,
                                    Temperature, seed, log)
    except json.JSONDecodeError:
        return None


def step_is_in_run(step: int, run: data.Trajectory) -> bool:
    """Return True if the step number is one of the run's steps."""
    return 0 <= step < len(run.steps)


def critic_question(claim: dict) -> str:
    """Write the critic's question: the proposer's step and reason (not its reasoning), then what to decide."""
    return (f"The claim to check: the decisive step is Step {claim['step']}.\n"
            f"Its reason: {claim['reason']}\n"
            "Do you agree that this is the decisive step? If not, which step is?")


def judge_question(claim: dict, critique: dict) -> str:
    """Write the judge's question: the proposer's step and reason, the critic's step and evidence, then the choice."""
    return (f"The proposer says the decisive step is Step {claim['step']}. Its reason: {claim['reason']}\n"
            f"The critic disagrees and says it is Step {critique['step']}. Its evidence: {critique['evidence']}\n"
            "Which answer names the decisive step: PROPOSER or CRITIC?")


if __name__ == "__main__":
    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(PROJECT_FOLDER / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server

    # Here we put today's logs in one folder per day: runs/single_critique/<date>/.
    log_folder = PROJECT_FOLDER / "runs" / "single_critique" / datetime.now().strftime("%Y-%m-%d")

    started_here = start_ollama_server()
    print(f"Start: {datetime.now():%H:%M:%S}")
    print("-------Starting Single Critique-------")
    # Here "try ... finally" makes sure the server we started is stopped even if something below fails.
    try:
        # Here we read the pilot run from data/splits/pilot.json (run 36).
        pilot_entry = json.loads((data.SPLITS_FOLDER / "pilot.json").read_text())[0]
        pilot_run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / pilot_entry["file"])

        # Here we run single critique on the pilot run; it writes its own log into log_folder.
        answer = run_single_critique(pilot_run, pilot_entry["number"], log_folder)
        print(f"Run {pilot_entry['number']}: answer = step {answer}, labelled Decisive step = {pilot_run.decisive_step}")
        print(f"Log folder: {log_folder}")
    finally:
        if started_here:
            stop_ollama_server()
    print("-------Finished Single Critique-------")
    print(f"End: {datetime.now():%H:%M:%S}")


