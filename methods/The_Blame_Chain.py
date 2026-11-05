'''
The Blame Chain: five roles work backward from how a failed run ended to the step that caused it.
Round 1: the Reviewer describes the ending, the Detective names a 5-step window, and both interns name a step.
Round 2: the Detective answers the interns and names one step, then both interns give their final step.
Final: the Judge reads the whole discussion and picks one of the named steps.
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

# ---------- Shared wording ----------
# Here we keep the wording several roles need in one place, so every role is held to the same definition.
DecisiveStepDefinition = (
    "The run is given as numbered steps, starting at Step 0, which is the task. "
    "The decisive step is the step where, had that step been done right, the run would not have failed. "
    "A later step that only follows from an earlier mistake is not the decisive step. "
)

# Here we tell only the Detective how answers are scored; this hint is specific to this method.
ScoringHint = "An answer counts as correct if it is within 2 steps of the true decisive step. "

LengthRule = "Use only what is in the run, and quote it where it matters. Write at most 300 words across all fields. "


# ---------- Round 1: Reviewer ----------
ReviewerPrompt = (
    "You are the Reviewer, a blunt incident reviewer. You have read a thousand failed runs and nothing impresses you. "
    "You state what happened and nothing more. "
    "A team of agents failed the task in this run. The run is given as numbered steps, starting at Step 0, which is the task. "
    "Your job: say how the run ended and what looks wrong with that ending. "
    "Tracebacks, API errors, content filter messages and system warnings come from the machinery, not the agents. Ignore them. "
    "Do not name, hint at or guess which step caused the failure. That is not your job. "
    "You are not given the correct answer. Do not invent it. "
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step about the task and how the run ended. "
    "how_it_ended: one or two sentences on the final answer or final state of the run. "
    "what_looks_wrong: one to three sentences on what is wrong with that ending."
)

ReviewerFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "how_it_ended": {"type": "string"},
        "what_looks_wrong": {"type": "string"},
    },
    "required": ["reasoning", "how_it_ended", "what_looks_wrong"],
}


# ---------- Round 1: Detective ----------
DetectiveRoundOnePrompt = (
    "You are the Detective, hard-boiled and suspicious of everything. The obvious suspect is usually just another victim. "
    "Every mistake has a cause, and you follow it backward until the trail goes cold. "
    + DecisiveStepDefinition +
    "You are given the Reviewer's account. Treat it as a lead, not a fact. "
    "Your job: start from how the run ended, trace the failure back one cause at a time, and stop at the earliest step "
    "where a correct action would have saved the run. "
    + ScoringHint +
    "Name a window of exactly 5 consecutive steps, with your prime suspect in the middle where the run allows it. "
    + LengthRule +
    "Answer only in JSON with four fields, in this order. "
    "reasoning: think step by step, moving backward from the ending and naming each cause you pass. "
    "window_start: the first step number in your window. "
    "window_end: the last step number in your window. "
    "evidence: two to four sentences with the quotes and step numbers that point to this window."
)

DetectiveRoundOneFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "window_start": {"type": "integer"},
        "window_end": {"type": "integer"},
        "evidence": {"type": "string"},
    },
    "required": ["reasoning", "window_start", "window_end", "evidence"],
}


# ---------- Rounds 1 and 2: Interns ----------
InternOnePrompt = (
    "You are Intern 1, restless and impossible to satisfy. You have one question and you never stop asking it: "
    "but what happened before that? "
    + DecisiveStepDefinition +
    "You are given what the others have said so far. "
    "Your job: assume the real mistake may be earlier than the Detective thinks, and go looking for it. "
    "Check the steps before the Detective's suspect for an earlier mistake that caused the failure. "
    "Do not invent one. If the trail really stops at the Detective's suspect, say so and name that step. "
    "The question will say whether this is your first answer or your final one. "
    "For your final answer, read the Detective's verdict and change your step only if the run gives you a reason. "
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step, looking for anything earlier that caused the failure. "
    "step: the step number you think is decisive. "
    "evidence: two to four sentences with the quotes and step numbers that support your step."
)

InternTwoPrompt = (
    "You are Intern 2, a pedantic fact-checker. You believe nothing until you have seen it in the run with your own eyes, "
    "and you enjoy catching people out. "
    + DecisiveStepDefinition +
    "You are given what the others have said so far. "
    "Your job: take the Detective's claims one at a time and look up every quote and step number in the run. "
    "Call out anything misquoted, missing, or that does not prove what the Detective says it proves. "
    "Then name the step the evidence actually supports. If the Detective's evidence holds, name the step in the "
    "Detective's window or verdict that it best supports. "
    "The question will say whether this is your first answer or your final one. "
    "For your final answer, check the Detective's verdict the same way and change your step only if the run gives you a reason. "
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step, checking each claim against the run. "
    "step: the step number you think is decisive. "
    "evidence: two to four sentences with the quotes and step numbers that support your step."
)

# Here both interns share one format, in both rounds.
InternFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "step": {"type": "integer"},
        "evidence": {"type": "string"},
    },
    "required": ["reasoning", "step", "evidence"],
}


# ---------- Round 2: Detective ----------
DetectiveRoundTwoPrompt = (
    "You are the Detective, and your case is now under review. Two interns have read your work and raised objections. "
    "Pride is not evidence. If they are right, say so and change your mind. If they are wrong, prove it. "
    + DecisiveStepDefinition +
    "You are given everything said in round 1. "
    "Your job: go back to the run, answer each intern's objection, then give your verdict. "
    "Your earlier window does not bind you. "
    + ScoringHint +
    "Name exactly one step. If you are torn between nearby steps, name the one in the middle. "
    + LengthRule +
    "Answer only in JSON with four fields, in this order. "
    "reasoning: think step by step, checking each objection against the run. "
    "answer_to_interns: one or two sentences to each intern, saying what you accept or reject and why. "
    "step: your verdict, the step number you think is decisive. "
    "reason: one sentence saying what went wrong at that step."
)

DetectiveRoundTwoFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "answer_to_interns": {"type": "string"},
        "step": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["reasoning", "answer_to_interns", "step", "reason"],
}


# ---------- Final: Judge ----------
JudgePrompt = (
    "You are the Judge: cold, fair and impossible to flatter. You do not care who said something, how many said it, "
    "who spoke last or how sure they sounded. You care only about what the run shows. "
    + DecisiveStepDefinition +
    "You are given the whole discussion and a list of the steps that were named. Treat everything said as claims to check. "
    "Your job: look up the evidence for each named step in the run, decide which holds up, and pick one step. "
    "You must pick. You may not abstain, and you may not name a step that is not on the list. "
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step, checking the evidence for each named step against the run. "
    "step: the step number you pick from the list. "
    "reason: one sentence saying why this is the decisive step."
)

JudgeFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "step": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["reasoning", "step", "reason"],
}


# ---------- Settings ----------
# Here we map each role to its model: Intern 2 and the Judge use the smaller model, the other roles the larger one.
ReviewerModel = settings.DEBATER_MODEL
DetectiveModel = settings.DEBATER_MODEL
InternOneModel = settings.DEBATER_MODEL
InternTwoModel = settings.JUDGE_MODEL
JudgeModel = settings.JUDGE_MODEL

# Here we fix the randomness: every call uses this seed, except the Judge's retries, which add 1, 2 and 3.
Temperature = 0.7
Seed = 42

# Here we cap each reply, so the Judge's prompt (the run plus 7 replies) fits Kaggle's window even for the longest run.
# Thinking counts towards this cap, so with thinking on we keep the larger shared limit.
ReplyLimitInTokens = runV2.ROOM_FOR_REPLY_IN_TOKENS if runV2.THINKING_ON else 2000

# Here we say how many times the Judge is asked again after a failed reply. No other role gets a retry.
MaxJudgeRetries = 3

ReviewerQuestion = "How did this run end, and what looks wrong with that ending?"


# ---------- The method ----------
# Here we reuse single critique's check, so both methods decide the same way whether a step exists.
from single_critique import step_is_in_run


def run_blame_chain(run: data.Trajectory, run_number: int, log_folder: Path) -> int | None:
    """Run The Blame Chain on one run, write its log, and return the Judge's step (None if it gave no usable step)."""
    log = []
    round_one_turns = run_round_one(run, log)
    round_two_turns = run_round_two(run, round_one_turns, log)
    all_turns = round_one_turns + round_two_turns

    # Here the Judge picks from the steps the roles named. There is no vote, so its step is the answer.
    named_steps = steps_named_in(all_turns)
    answer, judge_line = ask_judge(run, all_turns, named_steps, log)

    # Here we add The Blame Chain's own lines to the log's result: what each turn said, then what the Judge did.
    extra_result_lines = [f"{turn['label']}: {summary_of_turn(turn)}" for turn in all_turns]
    extra_result_lines.append(f"Named steps: {steps_as_text(named_steps)}")
    extra_result_lines.append(f"Judge: {judge_line}")
    runV2.write_log(log, log_folder, "The Blame Chain", run_number, run, answer, extra_result_lines)
    return answer


def run_round_one(run: data.Trajectory, log: list) -> list[dict]:
    """Round 1: the Reviewer describes the ending, the Detective names a window, and both interns name a step."""
    reviewer_turn = take_turn("reviewer", "Round 1, Reviewer", ReviewerModel, ReviewerPrompt, run, ReviewerQuestion,
                              ReviewerFormat, log)

    # Here the Detective sees only the Reviewer's answer, and is told the run's range so its window stays inside the run.
    last_step = len(run.steps) - 1
    detective_question = question_after_discussion(
        [reviewer_turn],
        f"This run has steps 0 to {last_step}. Trace the failure backward. Which 5 consecutive steps hold the decisive step?")
    detective_turn = take_turn("detective round 1", "Round 1, Detective", DetectiveModel, DetectiveRoundOnePrompt, run,
                               detective_question, DetectiveRoundOneFormat, log)

    turns_so_far = [reviewer_turn, detective_turn]
    return turns_so_far + ask_both_interns(run, turns_so_far, 1, "first", log)


def run_round_two(run: data.Trajectory, round_one_turns: list[dict], log: list) -> list[dict]:
    """Round 2: the Detective answers the interns and names one step, then both interns give their final step."""
    # Here the Detective sees all of round 1.
    detective_question = question_after_discussion(
        round_one_turns, "Answer each intern's objection, then give your verdict. Which one step is the decisive step?")
    detective_turn = take_turn("detective round 2", "Round 2, Detective", DetectiveModel, DetectiveRoundTwoPrompt, run,
                               detective_question, DetectiveRoundTwoFormat, log)

    turns_so_far = round_one_turns + [detective_turn]
    return [detective_turn] + ask_both_interns(run, turns_so_far, 2, "final", log)


def ask_both_interns(run: data.Trajectory, turns_so_far: list[dict], round_number: int, which_answer: str,
                     log: list) -> list[dict]:
    """Ask both interns the same question and return their two turns."""
    # Here we write the question once, before either intern answers, so neither sees the other's answer in this round.
    question = question_after_discussion(turns_so_far, f"This is your {which_answer} answer. Which step is the decisive step?")

    intern_one_turn = take_turn("intern 1", f"Round {round_number}, Intern 1", InternOneModel, InternOnePrompt, run,
                                question, InternFormat, log)
    intern_two_turn = take_turn("intern 2", f"Round {round_number}, Intern 2", InternTwoModel, InternTwoPrompt, run,
                                question, InternFormat, log)
    return [intern_one_turn, intern_two_turn]


def ask_judge(run: data.Trajectory, all_turns: list[dict], named_steps: list[int], log: list) -> tuple[int | None, str]:
    """Ask the Judge to pick a named step, up to 3 more times if a reply fails.
    Return the step and a line for the log, or None and why there is no step."""
    # Here we do not ask the Judge when nobody named a step, because it would have nothing to pick from.
    if not named_steps:
        return None, "not asked, because nobody named a step"

    number_of_tries = MaxJudgeRetries + 1
    first_question = judge_question(all_turns, named_steps)
    question = first_question
    problem = ""

    for try_number in range(number_of_tries):
        # Here each retry uses a new seed; with the same seed and prompt the model would repeat the same failed reply.
        answer = ask_role("judge", JudgeModel, JudgePrompt, run, question, judge_format_for(named_steps),
                          Seed + try_number, log)
        problem = problem_with_judge_answer(answer, named_steps)
        if not problem:
            return answer["step"], f"step {answer['step']} (try {try_number + 1} of {number_of_tries})"

        # Here the next try says what went wrong this time, added to the original question.
        question = f"{first_question}\nYour last reply was rejected because {problem}."

    return None, f"no answer after {number_of_tries} tries; on the last try {problem}"


# ---------- Small helpers ----------
def take_turn(role: str, label: str, model: str, system_prompt: str, run: data.Trajectory, question: str,
              answer_format: dict, log: list) -> dict:
    """Ask one role once and return its turn: its label, its answer (None if unusable), and any problem with it."""
    answer = ask_role(role, model, system_prompt, run, question, answer_format, Seed, log)
    problem = problem_with_answer(answer, run)

    # Here an unusable answer becomes no answer, so the next roles never read a step that does not exist.
    usable_answer = None if problem else answer
    return {"label": label, "answer": usable_answer, "problem": problem}


def ask_role(role: str, model: str, system_prompt: str, run: data.Trajectory, question: str,
             answer_format: dict, seed: int, log: list) -> dict | None:
    """Ask one role once and return its JSON answer, or None if the reply was not valid JSON (it still counts as a call)."""
    try:
        return runV2.send_to_ollama(role, model, system_prompt, run.steps, question, answer_format,
                                    Temperature, seed, log, reply_limit=ReplyLimitInTokens)
    except json.JSONDecodeError:
        return None


def problem_with_answer(answer: dict | None, run: data.Trajectory) -> str | None:
    """Return why an answer cannot be used (not valid JSON, or a step or window outside the run), or None if it can."""
    if answer is None:
        return "the reply was not valid JSON"
    if "step" in answer and not step_is_in_run(answer["step"], run):
        return f"step {answer['step']} is not in the run"
    if "window_start" in answer and not window_is_in_run(answer["window_start"], answer["window_end"], run):
        return f"window {answer['window_start']} to {answer['window_end']} is not in the run"
    return None


def window_is_in_run(window_start: int, window_end: int, run: data.Trajectory) -> bool:
    """Return True if the window runs forward and both of its ends are steps in the run."""
    return window_start <= window_end and step_is_in_run(window_start, run) and step_is_in_run(window_end, run)


def problem_with_judge_answer(answer: dict | None, named_steps: list[int]) -> str | None:
    """Return why the Judge's answer cannot be used (not valid JSON, or a step nobody named), or None if it can."""
    if answer is None:
        return "your reply was not valid JSON"
    if answer["step"] not in named_steps:
        return f"you picked step {answer['step']}, which nobody named"
    return None


def steps_named_in(turns: list[dict]) -> list[int]:
    """Return the steps the turns named, in order and without repeats. The Detective's window does not name a step."""
    named_steps = set()
    for turn in turns:
        if turn["answer"] is not None and "step" in turn["answer"]:
            named_steps.add(turn["answer"]["step"])
    return sorted(named_steps)


def steps_as_text(steps: list[int]) -> str:
    """Write a list of steps as text, for example "2, 3, 4", or "none" if the list is empty."""
    if not steps:
        return "none"
    return ", ".join(str(step) for step in steps)


def turn_as_text(turn: dict) -> str:
    """Write one turn for the next roles to read: a header, then each answer field, or "no answer"."""
    if turn["answer"] is None:
        return f"--- {turn['label']} ---\nno answer\n"
    answer_lines = [f"{field}: {value}" for field, value in turn["answer"].items()]
    return f"--- {turn['label']} ---\n" + "\n".join(answer_lines) + "\n"


def question_after_discussion(turns: list[dict], question: str) -> str:
    """Write a question that comes after the discussion so far. The roles read this clean text, never the log."""
    discussion = "\n".join(turn_as_text(turn) for turn in turns)
    return f"The discussion so far:\n\n{discussion}\n{question}"


def judge_question(all_turns: list[dict], named_steps: list[int]) -> str:
    """Write the Judge's question: the whole discussion, then the steps it may pick from."""
    return question_after_discussion(
        all_turns, f"The steps that were named: {steps_as_text(named_steps)}.\nWhich of these is the decisive step? Pick one.")


def judge_format_for(named_steps: list[int]) -> dict:
    """Return a copy of JudgeFormat whose step can only be one of this run's named steps."""
    # Here we build a copy, so one run's list of steps never stays behind in the shared JudgeFormat.
    properties = dict(JudgeFormat["properties"])
    properties["step"] = {"type": "integer", "enum": named_steps}
    return {**JudgeFormat, "properties": properties}


def summary_of_turn(turn: dict) -> str:
    """Write a short summary of one turn for the log's result."""
    if turn["answer"] is None:
        return f"no answer ({turn['problem']})"
    if "step" in turn["answer"]:
        return f"step {turn['answer']['step']}"
    if "window_start" in turn["answer"]:
        return f"window {turn['answer']['window_start']} to {turn['answer']['window_end']}"
    return "answered"


if __name__ == "__main__":
    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(PROJECT_FOLDER / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server

    # Here we put today's logs in one folder per day: runs/the_blame_chain/<date>/.
    log_folder = PROJECT_FOLDER / "runs" / "the_blame_chain" / datetime.now().strftime("%Y-%m-%d")

    started_here = start_ollama_server()
    print(f"Start: {datetime.now():%H:%M:%S}")
    print("-------Starting The Blame Chain-------")
    # Here "try ... finally" makes sure the server we started is stopped even if something below fails.
    try:
        # Here we read the pilot run from data/splits/pilot.json (run 36).
        pilot_entry = json.loads((data.SPLITS_FOLDER / "pilot.json").read_text())[0]
        pilot_run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / pilot_entry["file"])

        # Here we run The Blame Chain on the pilot run; it writes its own log into log_folder.
        answer = run_blame_chain(pilot_run, pilot_entry["number"], log_folder)
        print(f"Run {pilot_entry['number']}: answer = step {answer}, labelled Decisive step = {pilot_run.decisive_step}")
        print(f"Log folder: {log_folder}")
    finally:
        if started_here:
            stop_ollama_server()
    print("-------Finished The Blame Chain-------")
    print(f"End: {datetime.now():%H:%M:%S}")
