'''
The Interrogation Room: two models search a failed run by halving it, with no judge and no vote.
The Witness (the strong model) first sums up what the task needs, from the task alone. Then, every round:
the Witness names a suspect step, the Interrogator (the weak model) presses it, and the Witness gives its final step.
The steps kept for the next round are the half centred on that final step. The search stops once halving would leave
5 steps or fewer, and the Witness's last step is the answer.
'''

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

# Here we reuse small helpers from The Blame Chain, so the methods write discussions, steps and log lines the same way.
from The_Blame_Chain import question_after_discussion, summary_of_turn
from The_Blame_ChainV2 import format_with_steps_limited_to, problem_with_answer, steps_for_close_up


# ---------- Shared wording ----------
# Here we use the same definition as The Blame Chain V2, word for word, so both methods look for the same step.
# It is copied, not imported, so a later change to V2 cannot quietly change this method.
DecisiveStepDefinition = (
    "Steps are numbered from Step 0, the task. "
    "The decisive step is the earliest step where an agent's action or decision put the run on a path it never "
    "recovered from, while the correct answer was still reachable. "
    "It can be retrieval that brought back wrong, incomplete or no information; accepting too little or stopping too early; "
    "a wrong instruction or plan; or wrong code or reasoning. "
    "It often looks routine and reports no error. "
    "Later steps that only follow from it, or merely reveal the failure, are not decisive. "
    "A run-ending error counts only if nothing earlier went wrong. "
)

# Here we tell the Witness how answers are scored, because its step decides which steps survive each round.
ScoringHint = "An answer counts as correct if it is within 2 steps of the true decisive step. "

LengthRule = "Use only what you are shown, and quote it where it matters. Write at most 200 words across all fields. "


# ---------- Call 1: Witness, summary ----------
WitnessSummaryPrompt = (
    "You are the Witness, a sharp expert who has reviewed a thousand failed runs and is about to testify on this one. "
    "Before you look at any evidence, you pin down what the job actually required. "
    "You are given only the task, at Step 0, and nothing the team did. "
    "Your job: sum up what the team must find or do to solve this task, as a checklist, in the order it must happen. "
    "List only what the task itself requires. Do not solve the task. Do not guess the answer. "
    "Write at most 200 words across all fields. "
    "Answer only in JSON with two fields, in this order. "
    "reasoning: think step by step about what the task requires. "
    "summary: a numbered checklist of 3 to 7 short items, each one fact to find or one action to complete."
)

WitnessSummaryFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["reasoning", "summary"],
}


# ---------- Each round, call A: Witness, testimony ----------
WitnessTestimonyPrompt = (
    "You are the Witness, a sharp expert testifying about a failed run. You are proud of your precision, "
    "and you never name a step you cannot back with a quote. "
    + DecisiveStepDefinition +
    "You are given the task, your own checklist, and the steps still in question. "
    "Each round, the steps kept for the next round are centred on the step you name, and the rest are thrown away for good. "
    "So a step named too late cannot be taken back. "
    "Your job: for each step shown, ask what it was meant to do, what it actually produced, and whether the correct "
    "answer was still reachable before it. Judge each step by what it produced, not by how the run ended. "
    "Then name the decisive step. It must be a step an agent took, so not Step 0, and it must be one of the steps shown. "
    + ScoringHint
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step through the steps shown, in order. "
    "step: the step number you think is decisive. "
    "reason: one or two sentences, with a quote, saying what went wrong at that step."
)


# ---------- Each round, call B: Interrogator ----------
InterrogatorPrompt = (
    "You are the Interrogator. You have broken a hundred confident witnesses, and you trust none of them. "
    "Every answer gets the same three questions: why, are you sure, and what happened before that? "
    + DecisiveStepDefinition +
    "You are given the task, the Witness's checklist, the steps still in question and the Witness's testimony. "
    "Your job: press the Witness. Check its quote against the steps shown, and say if it is missing, misquoted or "
    "does not prove what the Witness claims. Ask why that step, and not a nearby one. "
    "Always look at the steps shown before the Witness's step, and name any earlier step that may have caused the failure. "
    "Do not invent problems. If the testimony holds up, say so plainly. "
    "You do not decide the answer. The Witness does. "
    + LengthRule +
    "Answer only in JSON with two fields, in this order. "
    "reasoning: think step by step, checking the testimony against the steps shown. "
    "feedback: two to four sentences to the Witness, with your questions and any earlier step it should check."
)

InterrogatorFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "feedback": {"type": "string"},
    },
    "required": ["reasoning", "feedback"],
}


# ---------- Each round, call C: Witness, final answer ----------
WitnessFinalPrompt = (
    "You are the Witness, and the Interrogator has just pressed you on your testimony. "
    "Pride is not evidence. If the Interrogator is right, change your step. If not, hold your ground and say why. "
    + DecisiveStepDefinition +
    "You are given the task, your checklist, the steps still in question, your testimony and the Interrogator's feedback. "
    "Your job: go back to the steps shown, answer each point the Interrogator raised, then give your final step for this round. "
    "Change your step only if the steps shown give you a reason. "
    "The steps kept for the next round are centred on this step, and the rest are thrown away for good. "
    "It must be a step an agent took, so not Step 0, and it must be one of the steps shown. "
    + ScoringHint
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step, answering each of the Interrogator's points against the steps shown. "
    "step: your final step for this round. "
    "reason: one or two sentences, with a quote, saying what went wrong at that step."
)

# Here the Witness's testimony and its final answer share one format.
WitnessStepFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "step": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["reasoning", "step", "reason"],
}


# ---------- Settings ----------
# Here the Witness is the strong model and the Interrogator the weak one. The qwen3.8 notebook changes both names
# in settings before this file is imported.
WitnessModel = settings.DEBATER_MODEL
InterrogatorModel = settings.JUDGE_MODEL

# Here we fix the randomness: every call uses the same temperature and seed.
Temperature = 0.7
Seed = 42

# Here we cap each reply. Thinking counts towards this cap, so with thinking on we keep the larger shared limit.
ReplyLimitInTokens = runV2.ROOM_FOR_REPLY_IN_TOKENS if runV2.THINKING_ON else 2000

# Here we stop the search once halving would leave this many steps or fewer: that is the ±2 tolerance around one step.
StepsLeftAtTheEnd = 5

SummaryQuestion = "What must the team find or do to solve this task?"


# ---------- The method ----------
def run_interrogation_room(run: data.Trajectory, run_number: int, log_folder: Path) -> int | None:
    """Run The Interrogation Room on one run, write its log, and return the Witness's last step (None if it gave none)."""
    log = []

    # Here the Witness sees only the task, so its checklist cannot be shaped by how the run ended.
    summary_turn = take_turn("witness summary", "Summary", WitnessModel, WitnessSummaryPrompt, run.steps[:1],
                             SummaryQuestion, WitnessSummaryFormat, log)

    answer, round_lines, number_of_rounds = search_by_halving(run, summary_turn, log)

    # Here we add this method's own lines to the log's result: the summary, every round, and how many rounds it took.
    extra_result_lines = [f"Summary: {summary_of_turn(summary_turn)}"] + round_lines + [f"Rounds: {number_of_rounds}"]
    runV2.write_log(log, log_folder, "The Interrogation Room", run_number, run, answer, extra_result_lines)
    return answer


def search_by_halving(run: data.Trajectory, summary_turn: dict, log: list) -> tuple[int | None, list[str], int]:
    """Run rounds until halving would leave 5 steps or fewer. Return the last step, the log lines and the rounds run."""
    # Here every agent step is in play at the start; Step 0 is the task, not an agent's action.
    steps_in_play = list(range(1, len(run.steps)))
    answer = None
    round_lines = []
    round_number = 0

    while True:
        round_number += 1
        round_turns, step_of_this_round = run_one_round(run, summary_turn, steps_in_play, round_number, log)
        round_lines += [f"{turn['label']}: {summary_of_turn(turn)}" for turn in round_turns]
        range_text = f"steps {steps_in_play[0]} to {steps_in_play[-1]}"

        # Here a round with no usable step ends the search, and the last step we have is the answer.
        if step_of_this_round is None:
            round_lines.append(f"Round {round_number}: no usable step, so the search stops here")
            return answer, round_lines, round_number
        answer = step_of_this_round

        # Here halving would leave 5 steps or fewer, so this round's step is the answer.
        if len(steps_in_play) <= 2 * StepsLeftAtTheEnd:
            round_lines.append(f"Round {round_number}: {range_text}, search finished")
            return answer, round_lines, round_number

        steps_in_play = half_centred_on(step_of_this_round, steps_in_play)
        round_lines.append(f"Round {round_number}: {range_text}, kept {steps_in_play[0]} to {steps_in_play[-1]}")


def run_one_round(run: data.Trajectory, summary_turn: dict, steps_in_play: list[int], round_number: int,
                  log: list) -> tuple[list[dict], int | None]:
    """Run one round: the Witness testifies, the Interrogator presses it, the Witness gives its final step.
    Return the three turns and the round's step (None if neither Witness answer was usable)."""
    # Here all three calls see the task and the steps in play, each with its own number.
    shown_steps = steps_for_close_up(run, steps_in_play)
    step_format = format_with_steps_limited_to(WitnessStepFormat, steps_in_play)
    range_text = f"steps {steps_in_play[0]} to {steps_in_play[-1]}"

    # Here the Witness names a suspect step, after reading its own checklist.
    testimony_question = question_after_discussion(
        [summary_turn], f"Round {round_number}. The steps in question are {range_text}. Which one is the decisive step?")
    testimony_turn = take_turn("witness testimony", f"Round {round_number}, Witness testimony", WitnessModel,
                               WitnessTestimonyPrompt, shown_steps, testimony_question, step_format, log, steps_in_play)

    # Here the Interrogator presses the Witness on that testimony. It gives feedback only, never a step.
    interrogator_question = question_after_discussion(
        [summary_turn, testimony_turn], "Press the Witness on this testimony.")
    interrogator_turn = take_turn("interrogator", f"Round {round_number}, Interrogator", InterrogatorModel,
                                  InterrogatorPrompt, shown_steps, interrogator_question, InterrogatorFormat, log)

    # Here the Witness answers the feedback and gives the step that decides which half is kept.
    final_question = question_after_discussion(
        [summary_turn, testimony_turn, interrogator_turn],
        f"Answer the Interrogator, then give your final step for this round, from {range_text}.")
    final_turn = take_turn("witness final", f"Round {round_number}, Witness final", WitnessModel,
                           WitnessFinalPrompt, shown_steps, final_question, step_format, log, steps_in_play)

    round_turns = [testimony_turn, interrogator_turn, final_turn]
    return round_turns, step_of_the_round(testimony_turn, final_turn)


def step_of_the_round(testimony_turn: dict, final_turn: dict) -> int | None:
    """Return the Witness's final step, or its testimony's step if the final answer failed, or None if both failed."""
    for turn in [final_turn, testimony_turn]:
        if turn["answer"] is not None:
            return turn["answer"]["step"]
    return None


def half_centred_on(step: int, steps_in_play: list[int]) -> list[int]:
    """Return the half of the steps in play centred on one step, pushed back inside if it would run past either end."""
    size_of_half = (len(steps_in_play) + 1) // 2

    # Here we put the step in the middle, then move the half back inside the steps in play if it sticks out.
    first_step = step - size_of_half // 2
    first_step = min(first_step, steps_in_play[-1] - size_of_half + 1)
    first_step = max(first_step, steps_in_play[0])
    return list(range(first_step, first_step + size_of_half))


# ---------- Small helpers ----------
def take_turn(role: str, label: str, model: str, system_prompt: str, steps: list[data.Step], question: str,
              answer_format: dict, log: list, allowed_steps: list[int] | None = None) -> dict:
    """Ask one role once and return its turn: its label, its answer (None if unusable), and any problem with it."""
    answer = ask_role(role, model, system_prompt, steps, question, answer_format, log)
    problem = problem_with_answer(answer, allowed_steps)

    # Here an unusable answer becomes no answer, so the next calls never read a step that is not in play.
    usable_answer = None if problem else answer
    return {"label": label, "answer": usable_answer, "problem": problem}


def ask_role(role: str, model: str, system_prompt: str, steps: list[data.Step], question: str,
             answer_format: dict, log: list) -> dict | None:
    """Ask one role once and return its JSON answer, or None if the reply was not valid JSON (it still counts as a call)."""
    try:
        return runV2.send_to_ollama(role, model, system_prompt, steps, question, answer_format,
                                    Temperature, Seed, log, reply_limit=ReplyLimitInTokens)
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(PROJECT_FOLDER / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server

    # Here we put today's logs in one folder per day: runs/the_interrogation_room/<date>/.
    log_folder = PROJECT_FOLDER / "runs" / "the_interrogation_room" / datetime.now().strftime("%Y-%m-%d")

    started_here = start_ollama_server()
    print(f"Start: {datetime.now():%H:%M:%S}")
    print("-------Starting The Interrogation Room-------")
    # Here "try ... finally" makes sure the server we started is stopped even if something below fails.
    try:
        # Here we read the pilot run from data/splits/pilot.json (run 36).
        pilot_entry = json.loads((data.SPLITS_FOLDER / "pilot.json").read_text())[0]
        pilot_run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / pilot_entry["file"])

        # Here we run the method on the pilot run; it writes its own log into log_folder.
        answer = run_interrogation_room(pilot_run, pilot_entry["number"], log_folder)
        print(f"Run {pilot_entry['number']}: answer = step {answer}, labelled Decisive step = {pilot_run.decisive_step}")
        print(f"Log folder: {log_folder}")
    finally:
        if started_here:
            stop_ollama_server()
    print("-------Finished The Interrogation Room-------")
    print(f"End: {datetime.now():%H:%M:%S}")
