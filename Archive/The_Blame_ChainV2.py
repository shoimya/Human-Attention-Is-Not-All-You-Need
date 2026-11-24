'''
The Blame Chain V2: one round that searches a failed run forward, without showing the ending during the search.
The Reviewer reads only the task and writes a checklist. The Detective then halves the run until 9 steps or fewer are left.
The Detective names a step from a close-up of those steps, Intern 1 looks for an earlier cause, and the Judge picks one.
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

# Here we reuse The Blame Chain's small helpers, so both versions write discussions and log lines the same way.
from The_Blame_Chain import (
    problem_with_judge_answer,
    question_after_discussion,
    steps_as_text,
    steps_named_in,
    summary_of_turn,
)


# ---------- Shared wording ----------
# Here we keep the wording several roles need in one place, so every role is held to the same definition.
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

# Here we tell only the Detective how answers are scored; this hint is specific to this method.
ScoringHint = "An answer counts as correct if it is within 2 steps of the true decisive step. "

# Here the halving questions get a shorter limit than the other roles, because writing takes most of a call's time.
HalvingLengthRule = "Use only what you are shown, and quote it where it matters. Write at most 100 words across all fields. "
LengthRule = "Use only what you are shown, and quote it where it matters. Write at most 200 words across all fields. "


# ---------- Call 1: Reviewer ----------
ReviewerPrompt = (
    "You are the Reviewer, a blunt project lead who has watched a thousand teams lose the plot. "
    "You do not care what a team tried. You care what the job needs. "
    "You are given only the task, at Step 0, and nothing the team did. "
    "Your job: write a checklist of what the team must find or do to solve this task, in the order it must happen. "
    "List only what the task itself requires. Do not solve the task. Do not guess the answer. "
    "Write at most 200 words across all fields. "
    "Answer only in JSON with two fields, in this order. "
    "reasoning: think step by step about what the task requires. "
    "checklist: a numbered list of 3 to 7 short items, each one fact to find or one action to complete."
)

ReviewerFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "checklist": {"type": "string"},
    },
    "required": ["reasoning", "checklist"],
}


# ---------- Calls 2 to 5: Detective, halving ----------
DetectiveHalvingPrompt = (
    "You are the Detective, hard-boiled and suspicious of everything. You never read the last page first. "
    "You take a case one page at a time, and you claim only what you can prove. "
    + DecisiveStepDefinition +
    "This run eventually failed, but you can see only its first part, plus the Reviewer's checklist. "
    "The rest of the run is hidden. Do not guess what comes next. The decisive step may not have happened yet. "
    "Your job: decide whether the decisive step is already in the steps you can see. "
    "Say yes only if you can point to a visible step that fits the definition. "
    "Say no if the team could still reach the correct answer from where it stands, even if some steps were clumsy. "
    + ScoringHint
    + HalvingLengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: compare what the team has achieved so far with the checklist. "
    "already_happened: true if the decisive step is in the steps you can see, false if it is not. "
    "evidence: one or two sentences with the quote and step number behind your answer."
)

DetectiveHalvingFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "already_happened": {"type": "boolean"},
        "evidence": {"type": "string"},
    },
    "required": ["reasoning", "already_happened", "evidence"],
}


# ---------- Call 6: Detective, close-up ----------
DetectiveCloseUpPrompt = (
    "You are the Detective, hard-boiled and suspicious of everything. The obvious suspect is usually just another victim. "
    "The search has narrowed this case to a handful of steps, and now you question each one. "
    + DecisiveStepDefinition +
    "You are given the task, the steps still in question, and the Reviewer's checklist. Treat the search result as a lead, not a fact. "
    "Your job: for each step, ask what it was meant to do, what it actually produced, and whether the correct answer was still reachable before it. "
    "Then name the decisive step. It must be a step an agent took, so not Step 0, and it must be one of the steps shown. "
    + ScoringHint +
    "Name exactly one step. If you are torn between nearby steps, name the one in the middle. "
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step through the steps shown, in order. "
    "step: the step number you think is decisive. "
    "evidence: two to four sentences with the quotes and step numbers that support your step."
)


# ---------- Call 7: Intern 1 ----------
InternOnePrompt = (
    "You are Intern 1, restless and impossible to satisfy. You have one question and you never stop asking it: "
    "but what happened before that? "
    + DecisiveStepDefinition +
    "You are given the task, the steps still in question, the Reviewer's checklist and the Detective's answer. "
    "Your job: assume the real mistake may be earlier than the Detective thinks, and go looking for it. "
    "Check the steps shown before the Detective's suspect for an earlier mistake that caused the failure. "
    "Do not invent one. If the trail really stops at the Detective's suspect, say so and name that step. "
    "Name a step an agent took, so not Step 0, and it must be one of the steps shown. "
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step, looking for anything earlier that caused the failure. "
    "step: the step number you think is decisive. "
    "evidence: two to four sentences with the quotes and step numbers that support your step."
)

# Here the Detective's close-up and Intern 1 share one format.
StepAndEvidenceFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "step": {"type": "integer"},
        "evidence": {"type": "string"},
    },
    "required": ["reasoning", "step", "evidence"],
}


# ---------- Call 8: Judge ----------
JudgePrompt = (
    "You are the Judge: cold, fair and impossible to flatter. You do not care who said something, who spoke last "
    "or how sure they sounded. You care only about what the run shows. "
    + DecisiveStepDefinition +
    "You are given the task, the steps still in question, the Detective's answer, Intern 1's answer and a list of the steps they named. "
    "Treat everything they said as claims to check. "
    "Your job: look up the evidence for each named step in the steps shown, decide which holds up, and pick one step. "
    "You must pick. You may not abstain, and you may not name a step that is not on the list. "
    + LengthRule +
    "Answer only in JSON with three fields, in this order. "
    "reasoning: think step by step, checking the evidence for each named step against the steps shown. "
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
# Here we map each role to its model: the Judge uses the smaller model, the other roles the larger one.
ReviewerModel = settings.DEBATER_MODEL
DetectiveModel = settings.DEBATER_MODEL
InternOneModel = settings.DEBATER_MODEL
JudgeModel = settings.JUDGE_MODEL

# Here we fix the randomness: every call uses this seed, except the Judge's retries, which add 1, 2 and 3.
Temperature = 0.7
Seed = 42

# Here we cap each reply. Thinking counts towards this cap, so with thinking on we keep the larger shared limit.
ReplyLimitInTokens = runV2.ROOM_FOR_REPLY_IN_TOKENS if runV2.THINKING_ON else 2000

# Here we say how many times the Judge is asked again after a failed reply. No other role gets a retry.
MaxJudgeRetries = 3

# Here we stop halving at 9 steps or fewer. Four calls are always enough, because the longest run has 130 steps.
MaxStepsLeftAfterHalving = 9
MaxHalvingCalls = 4

# Here we show 2 extra steps on each side in the close-up, in case the halving stopped just short of the mistake.
ExtraStepsInCloseUp = 2

ReviewerQuestion = "What must the team find or do to solve this task?"


# ---------- The method ----------
def run_blame_chain_v2(run: data.Trajectory, run_number: int, log_folder: Path) -> int | None:
    """Run The Blame Chain V2 on one run, write its log, and return the Judge's step (None if it gave no usable step)."""
    log = []

    # Here the Reviewer sees only the task, so its checklist cannot be shaped by how the run ended.
    reviewer_turn = take_turn("reviewer", "Reviewer", ReviewerModel, ReviewerPrompt, run.steps[:1], ReviewerQuestion,
                              ReviewerFormat, log)

    first_step_left, last_step_left, halving_lines = halve_the_run(run, reviewer_turn, log)
    close_up_turns, allowed_steps = run_close_up(run, reviewer_turn, first_step_left, last_step_left, log)

    # Here the Judge picks from the steps the two roles named, and sees the same steps they saw.
    named_steps = steps_named_in(close_up_turns)
    close_up_steps = steps_for_close_up(run, allowed_steps)
    answer, judge_line = ask_judge(close_up_steps, close_up_turns, named_steps, log)

    # Here we add this method's own lines to the log's result: each answer, in order, then what the Judge did.
    extra_result_lines = [f"Reviewer: {summary_of_turn(reviewer_turn)}"]
    extra_result_lines += halving_lines
    extra_result_lines.append(f"Close-up steps: {allowed_steps[0]} to {allowed_steps[-1]}")
    extra_result_lines += [f"{turn['label']}: {summary_of_turn(turn)}" for turn in close_up_turns]
    extra_result_lines.append(f"Named steps: {steps_as_text(named_steps)}")
    extra_result_lines.append(f"Judge: {judge_line}")
    runV2.write_log(log, log_folder, "The Blame Chain V2", run_number, run, answer, extra_result_lines)
    return answer


def halve_the_run(run: data.Trajectory, reviewer_turn: dict, log: list) -> tuple[int, int, list[str]]:
    """Halve the run until 9 steps or fewer are left. Return the first and last steps left, and one log line per call."""
    first_step_left = 0
    last_step_left = len(run.steps) - 1
    halving_lines = []

    for call_number in range(1, MaxHalvingCalls + 1):
        number_of_steps_left = last_step_left - first_step_left + 1
        if number_of_steps_left <= MaxStepsLeftAfterHalving:
            break

        # Here the Detective sees the run only up to the cut-off, so the ending stays hidden during the search.
        cut_off = (first_step_left + last_step_left) // 2
        turn = take_turn("detective halving", f"Halving {call_number} (by step {cut_off})", DetectiveModel,
                         DetectiveHalvingPrompt, run.steps[:cut_off + 1],
                         halving_question(reviewer_turn, first_step_left, cut_off), DetectiveHalvingFormat, log)

        # Here a failed reply stops the halving, and the close-up uses the steps left so far.
        if turn["answer"] is None:
            halving_lines.append(f"{turn['label']}: {summary_of_turn(turn)}")
            break

        # Here yes keeps the earlier half and no keeps the later half.
        if turn["answer"]["already_happened"]:
            last_step_left = cut_off
            answer_word = "yes"
        else:
            first_step_left = cut_off + 1
            answer_word = "no"
        halving_lines.append(f"{turn['label']}: {answer_word}, steps left {first_step_left} to {last_step_left}")

    return first_step_left, last_step_left, halving_lines


def halving_question(reviewer_turn: dict, first_step_left: int, cut_off: int) -> str:
    """Write one halving question: the checklist, what earlier checks found if anything, and the cut-off."""
    question = f"Has the decisive step already happened by step {cut_off}?"

    # Here a later call is told what an earlier no ruled out, so it does not blame a step already cleared.
    if first_step_left > 0:
        question = (f"Earlier checks found the decisive step comes after step {first_step_left - 1}, "
                    f"so look for it in steps {first_step_left} to {cut_off}. {question}")

    return question_after_discussion([reviewer_turn], question)


def run_close_up(run: data.Trajectory, reviewer_turn: dict, first_step_left: int, last_step_left: int,
                 log: list) -> tuple[list[dict], list[int]]:
    """Ask the Detective and then Intern 1 to name a step from the close-up. Return their turns and the steps allowed."""
    # Here we add the extra steps on each side and leave out Step 0, because the task is not an agent's action.
    first_allowed_step = max(1, first_step_left - ExtraStepsInCloseUp)
    last_allowed_step = min(len(run.steps) - 1, last_step_left + ExtraStepsInCloseUp)
    allowed_steps = list(range(first_allowed_step, last_allowed_step + 1))

    close_up_steps = steps_for_close_up(run, allowed_steps)
    answer_format = format_with_steps_limited_to(StepAndEvidenceFormat, allowed_steps)
    search_result = (f"The search narrowed this case to steps {first_step_left} to {last_step_left}. "
                     f"The steps you may name: {steps_as_text(allowed_steps)}. Which one is the decisive step?")

    detective_turn = take_turn("detective close-up", "Close-up, Detective", DetectiveModel, DetectiveCloseUpPrompt,
                               close_up_steps, question_after_discussion([reviewer_turn], search_result),
                               answer_format, log, allowed_steps)
    intern_turn = take_turn("intern 1", "Close-up, Intern 1", InternOneModel, InternOnePrompt,
                            close_up_steps, question_after_discussion([reviewer_turn, detective_turn], search_result),
                            answer_format, log, allowed_steps)
    return [detective_turn, intern_turn], allowed_steps


def steps_for_close_up(run: data.Trajectory, allowed_steps: list[int]) -> list[data.Step]:
    """Return the steps the close-up shows: the task, then the allowed steps, each with its own number."""
    return [run.steps[0]] + [run.steps[step_number] for step_number in allowed_steps]


def ask_judge(close_up_steps: list[data.Step], close_up_turns: list[dict], named_steps: list[int],
              log: list) -> tuple[int | None, str]:
    """Ask the Judge to pick a named step, up to 3 more times if a reply fails.
    Return the step and a line for the log, or None and why there is no step."""
    # Here we do not ask the Judge when nobody named a step, because it would have nothing to pick from.
    if not named_steps:
        return None, "not asked, because nobody named a step"

    number_of_tries = MaxJudgeRetries + 1
    answer_format = format_with_steps_limited_to(JudgeFormat, named_steps)
    first_question = question_after_discussion(
        close_up_turns, f"The steps that were named: {steps_as_text(named_steps)}.\nWhich of these is the decisive step? Pick one.")
    question = first_question
    problem = ""

    for try_number in range(number_of_tries):
        # Here each retry uses a new seed; with the same seed and prompt the model would repeat the same failed reply.
        answer = ask_role("judge", JudgeModel, JudgePrompt, close_up_steps, question, answer_format, Seed + try_number, log)
        problem = problem_with_judge_answer(answer, named_steps)
        if not problem:
            return answer["step"], f"step {answer['step']} (try {try_number + 1} of {number_of_tries})"

        # Here the next try says what went wrong this time, added to the original question.
        question = f"{first_question}\nYour last reply was rejected because {problem}."

    return None, f"no answer after {number_of_tries} tries; on the last try {problem}"


# ---------- Small helpers ----------
def take_turn(role: str, label: str, model: str, system_prompt: str, steps: list[data.Step], question: str,
              answer_format: dict, log: list, allowed_steps: list[int] | None = None) -> dict:
    """Ask one role once and return its turn: its label, its answer (None if unusable), and any problem with it."""
    answer = ask_role(role, model, system_prompt, steps, question, answer_format, Seed, log)
    problem = problem_with_answer(answer, allowed_steps)

    # Here an unusable answer becomes no answer, so the next roles never read a step they were not shown.
    usable_answer = None if problem else answer
    return {"label": label, "answer": usable_answer, "problem": problem}


def ask_role(role: str, model: str, system_prompt: str, steps: list[data.Step], question: str,
             answer_format: dict, seed: int, log: list) -> dict | None:
    """Ask one role once and return its JSON answer, or None if the reply was not valid JSON (it still counts as a call)."""
    try:
        return runV2.send_to_ollama(role, model, system_prompt, steps, question, answer_format,
                                    Temperature, seed, log, reply_limit=ReplyLimitInTokens)
    except json.JSONDecodeError:
        return None


def problem_with_answer(answer: dict | None, allowed_steps: list[int] | None) -> str | None:
    """Return why an answer cannot be used (not valid JSON, or a step that is not allowed), or None if it can."""
    if answer is None:
        return "the reply was not valid JSON"
    if allowed_steps is not None and answer["step"] not in allowed_steps:
        return f"step {answer['step']} is not one of the steps allowed"
    return None


def format_with_steps_limited_to(answer_format: dict, allowed_steps: list[int]) -> dict:
    """Return a copy of an answer format whose step can only be one of the allowed steps."""
    # Here we build a copy, so one run's list of steps never stays behind in the shared format.
    properties = dict(answer_format["properties"])
    properties["step"] = {"type": "integer", "enum": allowed_steps}
    return {**answer_format, "properties": properties}


if __name__ == "__main__":
    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(PROJECT_FOLDER / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server

    # Here we put today's logs in one folder per day: runs/the_blame_chain_v2/<date>/.
    log_folder = PROJECT_FOLDER / "runs" / "the_blame_chain_v2" / datetime.now().strftime("%Y-%m-%d")

    started_here = start_ollama_server()
    print(f"Start: {datetime.now():%H:%M:%S}")
    print("-------Starting The Blame Chain V2-------")
    # Here "try ... finally" makes sure the server we started is stopped even if something below fails.
    try:
        # Here we read the pilot run from data/splits/pilot.json (run 36).
        pilot_entry = json.loads((data.SPLITS_FOLDER / "pilot.json").read_text())[0]
        pilot_run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / pilot_entry["file"])

        # Here we run the method on the pilot run; it writes its own log into log_folder.
        answer = run_blame_chain_v2(pilot_run, pilot_entry["number"], log_folder)
        print(f"Run {pilot_entry['number']}: answer = step {answer}, labelled Decisive step = {pilot_run.decisive_step}")
        print(f"Log folder: {log_folder}")
    finally:
        if started_here:
            stop_ollama_server()
    print("-------Finished The Blame Chain V2-------")
    print(f"End: {datetime.now():%H:%M:%S}")
