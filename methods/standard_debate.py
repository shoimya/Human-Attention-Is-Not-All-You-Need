
import json
import time
import urllib.request
from pathlib import Path

import runV2
import settings


DebaterModel = "qwen3.5:9b"
JudgeModel = "qwen3.5:2b"
NumberOfRounds = 4          # N: each round is one turn of A and one turn of B. Update from the prover-estimator average.
MaxCalls = 10               # hard cap on model calls per run (the one-shot budget); one call is always kept for the judge
EarlyStopOnAgreement = True
Temperature = 0.7
Seed = 50                   # call number c uses seed Seed + c
MaxRetriesPerTurn = 2       # a turn is asked again when its JSON is broken or its step is not in the run

MaxReplyTokens = 1500       # a reply longer than this is cut (and reported as REPLY WAS CUT in the log)
MinContext = 8192
MaxContext = 49152          # same ceiling as the single critique logs
ContextStep = 4096
CharactersPerToken = 3.0    # rough estimate, only used to size the context window

# ----------------------------------------------------------------------------------------------------------------
# Prompts
# ----------------------------------------------------------------------------------------------------------------
DEFINITION = (
    "The run is given as numbered steps, starting at Step 0, which is the task. The decisive step is the step where, "
    "had that step been done right, the run would not have failed. A later step that only follows from an earlier "
    "mistake is not the decisive step."
)

DEBATER_A_SYSTEM = (
    "You are Debater A in a debate about a failed run of a team of agents. " + DEFINITION + " "
    "Your job is to find the decisive step and argue for it as convincingly and honestly as you can, using what the "
    "steps actually say. In every turn you must name exactly one step. When Debater B argues against you, answer its "
    "points. Keep your step if you still think it is right. If B has convinced you, change to B's step and say so; "
    "do not defend a step you no longer believe in. Answer only in JSON with three fields, in this order. "
    "reasoning: go through the evidence in a few sentences. step: the step number you now believe is decisive. "
    "argument: at most four sentences addressed to the judge and to your opponent."
)

DEBATER_B_SYSTEM = (
    "You are Debater B in a debate about a failed run of a team of agents. " + DEFINITION + " "
    "Debater A has named a step. In your first turn you must name a DIFFERENT step that you think is the real "
    "decisive step, and argue for it, including why A's step is not decisive (for example, it only follows from an "
    "earlier mistake, or the run could still have succeeded after it). In later turns answer A's points. Keep your "
    "step if you still think it is right. If A has convinced you, change to A's step and say so; do not defend a "
    "step you no longer believe in. In every turn you must name exactly one step. Answer only in JSON with three "
    "fields, in this order. reasoning: go through the evidence in a few sentences. step: the step number you now "
    "believe is decisive. argument: at most four sentences addressed to the judge and to your opponent."
)

JUDGE_SYSTEM = (
    "You are the judge of a debate about a failed run of a team of agents. " + DEFINITION + " "
    "Two debaters, A and B, argued for different steps. Read the steps and the debate, decide which debater is right, "
    "or pick another step if neither is. Do not just pick the debater who sounds more confident; check their claims "
    "against the steps. Answer only in JSON with five fields, in this order. reasoning: a few sentences. "
    "winner: DEBATER_A, DEBATER_B or NEITHER. step: the decisive step's number. reason: one sentence saying what "
    "went wrong at that step. confidence: a number from 0 to 1."
)

DEBATER_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "step": {"type": "integer"},
        "argument": {"type": "string"},
    },
    "required": ["reasoning", "step", "argument"],
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "winner": {"type": "string", "enum": ["DEBATER_A", "DEBATER_B", "NEITHER"]},
        "step": {"type": "integer"},
        "reason": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["reasoning", "winner", "step", "reason", "confidence"],
}


# ----------------------------------------------------------------------------------------------------------------
# Reading the run
# ----------------------------------------------------------------------------------------------------------------
def _field(step, names):
    """Return the first present field of a step, whether the step is a dict or an object."""
    for name in names:
        value = step.get(name) if isinstance(step, dict) else getattr(step, name, None)
        if value:
            return value
    return ""


def render_trajectory(run) -> str:
    """Return the run as numbered steps, starting at Step 0. Adapt this one function if your steps look different."""
    lines = []
    for number, step in enumerate(run.steps):
        if isinstance(step, str):
            lines.append(f"Step {number}: {step}")
            continue
        who = _field(step, ["role", "name", "agent", "speaker"])
        content = _field(step, ["content", "text", "message"])
        lines.append(f"Step {number} ({who}): {content}" if who else f"Step {number}: {content}")
    return "\n\n".join(lines)


# ----------------------------------------------------------------------------------------------------------------
# Talking to Ollama
# ----------------------------------------------------------------------------------------------------------------
def context_window_for(system_text: str, user_text: str) -> int:
    """Pick the smallest context window (a multiple of ContextStep) that fits the prompt and a full reply."""
    estimated_tokens = (len(system_text) + len(user_text)) / CharactersPerToken + MaxReplyTokens + 512
    steps_needed = -(-int(estimated_tokens) // ContextStep)
    return max(MinContext, min(MaxContext, steps_needed * ContextStep))


def call_model(model: str, system_text: str, user_text: str, schema: dict, seed: int) -> dict:
    """One Ollama call with a JSON schema. Returns the parsed reply (or None) and what the log needs."""
    num_context = context_window_for(system_text, user_text)
    request_body = {
        "model": model,
        "stream": False,
        "think": bool(runV2.THINKING_ON),
        "format": schema,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "options": {
            "temperature": Temperature,
            "seed": seed,
            "num_ctx": num_context,
            "num_predict": MaxReplyTokens,
        },
    }
    request = urllib.request.Request(
        settings.OLLAMA_ADDRESS + "/api/chat",
        data=json.dumps(request_body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start_time = time.time()
    with urllib.request.urlopen(request, timeout=3600) as response:
        reply = json.load(response)
    seconds = time.time() - start_time

    reply_text = reply.get("message", {}).get("content", "")
    try:
        parsed = json.loads(reply_text)
        if not isinstance(parsed, dict):
            parsed = None
    except json.JSONDecodeError:
        parsed = None

    tokens_read = reply.get("prompt_eval_count", 0)
    estimated_prompt_tokens = (len(system_text) + len(user_text)) / CharactersPerToken
    return {
        "model": model,
        "seed": seed,
        "num_context": num_context,
        "parsed": parsed,
        "raw_text": reply_text,
        "tokens_read": tokens_read,
        "tokens_written": reply.get("eval_count", 0),
        "seconds": seconds,
        "prompt_may_be_cut": tokens_read >= num_context - 8 or estimated_prompt_tokens > num_context,
        "reply_was_cut": reply.get("done_reason") == "length",
    }


# ----------------------------------------------------------------------------------------------------------------
# Prompts for each turn
# ----------------------------------------------------------------------------------------------------------------
def transcript_text(turns: list) -> str:
    """Return the debate so far, one block per turn."""
    if not turns:
        return "(no arguments yet)"
    blocks = []
    for turn in turns:
        blocks.append(f"Round {turn['round']}, {turn['speaker']} (step {turn['step']}): {turn['argument']}")
    return "\n\n".join(blocks)


def debater_user_prompt(trajectory: str, turns: list, speaker: str, round_number: int, own_step, opponent_step) -> str:
    """Build the user message for one debater turn: the steps, the debate so far and this turn's instruction."""
    if not turns:
        task = "This is the first turn. Name the decisive step and argue for it."
    elif speaker == "Debater B" and round_number == 1:
        task = (f"Debater A named step {opponent_step}. You must name a DIFFERENT step than {opponent_step}. "
                f"Argue that your step is the decisive one and that step {opponent_step} is not.")
    else:
        task = (f"Your opponent currently holds step {opponent_step} and you hold step {own_step}. Answer your "
                f"opponent's last argument. Keep your step or change it, and say which and why.")
    return (
        f"The run, as numbered steps:\n\n{trajectory}\n\n"
        f"The debate so far:\n\n{transcript_text(turns)}\n\n"
        f"You are {speaker}. {task} Remember the step number must be between 0 and the last step of the run."
    )


def judge_user_prompt(trajectory: str, turns: list, last_step_a, last_step_b) -> str:
    return (
        f"The run, as numbered steps:\n\n{trajectory}\n\n"
        f"The debate:\n\n{transcript_text(turns)}\n\n"
        f"At the end, Debater A holds step {last_step_a} and Debater B holds step {last_step_b}. "
        f"Decide which step is the decisive step."
    )


# ----------------------------------------------------------------------------------------------------------------
# The method
# ----------------------------------------------------------------------------------------------------------------
def step_is_valid(step, number_of_steps: int) -> bool:
    return isinstance(step, int) and not isinstance(step, bool) and 0 <= step < number_of_steps


def ask_until_valid(model, system_text, user_text, schema, number_of_steps, calls, call_log,
                    must_differ_from=None, reserve_calls_for_judge=True):
    """Ask one question, and ask again (up to MaxRetriesPerTurn times) while the reply is unusable.

    A reply is unusable when it is not JSON, or its step is not in the run, or (for B's first turn) it repeats A's step.
    Returns the last parsed reply, or None if no call was allowed or none gave JSON. Every call is appended to call_log.
    """
    last_parsed = None
    prompt = user_text
    for attempt in range(MaxRetriesPerTurn + 1):
        calls_left = MaxCalls - len(call_log) - (1 if reserve_calls_for_judge else 0)
        if calls_left <= 0:
            break
        result = call_model(model, system_text, prompt, schema, Seed + len(call_log))
        result["note"] = ""
        call_log.append(result)

        parsed = result["parsed"]
        if parsed is None:
            result["note"] = "reply was not valid JSON"
            prompt = user_text + "\n\nYour last reply was not valid JSON. Answer only in the JSON format."
            continue
        last_parsed = parsed
        if not step_is_valid(parsed.get("step"), number_of_steps):
            result["note"] = f"step {parsed.get('step')} is not in the run (steps 0 to {number_of_steps - 1})"
            prompt = (user_text + f"\n\nYour last reply named step {parsed.get('step')}, which is not in the run. "
                      f"Name a step from 0 to {number_of_steps - 1}.")
            continue
        if must_differ_from is not None and parsed["step"] == must_differ_from:
            result["note"] = f"step {parsed['step']} repeats the opponent's step"
            prompt = (user_text + f"\n\nYour last reply named step {must_differ_from}, which is your opponent's step. "
                      f"You must name a different step.")
            continue
        return parsed
    return last_parsed


def run_standard_debate(run, run_number: int, log_folder: Path):
    """Run the debate on one run, write its log, and return the final step (or None if no valid step came out)."""
    number_of_steps = len(run.steps)
    trajectory = render_trajectory(run)

    turns = []                  # every debater turn: {round, speaker, step, argument}
    call_log = []               # every model call, for the log
    position = {"Debater A": None, "Debater B": None}
    answer = None
    converged = False
    judge_result = None
    rounds_used = 0

    # ---- the debate ----
    for round_number in range(1, NumberOfRounds + 1):
        rounds_used = round_number
        for speaker, system_text in (("Debater A", DEBATER_A_SYSTEM), ("Debater B", DEBATER_B_SYSTEM)):
            opponent = "Debater B" if speaker == "Debater A" else "Debater A"
            first_b_turn = speaker == "Debater B" and round_number == 1
            user_text = debater_user_prompt(trajectory, turns, speaker, round_number,
                                            position[speaker], position[opponent])
            parsed = ask_until_valid(
                DebaterModel, system_text, user_text, DEBATER_SCHEMA, number_of_steps, None, call_log,
                must_differ_from=position[opponent] if first_b_turn else None,
            )
            if parsed is None or not step_is_valid(parsed.get("step"), number_of_steps):
                continue    # this speaker keeps their old position (or has none) and the debate goes on

            position[speaker] = parsed["step"]
            turns.append({"round": round_number, "speaker": speaker, "step": parsed["step"],
                          "argument": parsed.get("argument", "")})

            # Here we stop early when a debater moves to the step the other one holds (after the first two turns).
            if (EarlyStopOnAgreement and position[opponent] is not None and position[speaker] == position[opponent]):
                converged = True
                answer = position[speaker]
                break
        if converged or len(call_log) >= MaxCalls - 1:
            break

    # ---- the judge ----
    if not converged:
        if position["Debater A"] is None and position["Debater B"] is None:
            answer = None   # no debater gave a valid step, so there is nothing to judge
        else:
            user_text = judge_user_prompt(trajectory, turns, position["Debater A"], position["Debater B"])
            judge_calls_before = len(call_log)
            judge_result = ask_until_valid(
                JudgeModel, JUDGE_SYSTEM, user_text, JUDGE_SCHEMA, number_of_steps, None, call_log,
                reserve_calls_for_judge=False,
            )
            # The judge's calls (it may retry) are the ones after judge_calls_before; mark them for the log.
            for judge_call in call_log[judge_calls_before:]:
                judge_call["is_judge"] = True
            if judge_result is not None and step_is_valid(judge_result.get("step"), number_of_steps):
                answer = judge_result["step"]
            else:
                answer = None

    _write_log(run, run_number, log_folder, answer, converged, rounds_used, turns, call_log, judge_result)
    return answer


# ----------------------------------------------------------------------------------------------------------------
# The log
# ----------------------------------------------------------------------------------------------------------------
def _write_log(run, run_number, log_folder, answer, converged, rounds_used, turns, call_log, judge_result):
    """Write run_<number>_<time>.md, in the same spirit as the one-shot and single critique logs."""
    log_folder = Path(log_folder)
    log_folder.mkdir(parents=True, exist_ok=True)
    log_file = log_folder / f"run_{run_number}_{time.strftime('%H-%M-%S')}.md"

    has_answer = answer is not None
    exactly_right = has_answer and answer == run.decisive_step
    within_tolerance = has_answer and abs(answer - run.decisive_step) <= runV2.HIT_TOLERANCE_IN_STEPS
    yes_no = lambda value: "yes" if value else "no"

    lines = [
        f"# Standard debate, run {run_number}",
        "",
        f"- Answer: {'step ' + str(answer) if has_answer else 'no step (no valid step came out of the debate)'}",
        f"- Labelled decisive step: {run.decisive_step}",
        f"- Exactly right: {yes_no(exactly_right)}",
        f"- Within +/- {runV2.HIT_TOLERANCE_IN_STEPS} steps: {yes_no(within_tolerance)}",
        f"- Calls: {len(call_log)} (allowed: {MaxCalls})",
        f"- Tokens read: {sum(call['tokens_read'] for call in call_log)}, "
        f"tokens written: {sum(call['tokens_written'] for call in call_log)}",
        f"- Rounds: {rounds_used} of {NumberOfRounds}",
        f"- Stopped early because the debaters agreed: {yes_no(converged)}",
        f"- Debaters: {DebaterModel}, judge: {JudgeModel}, temperature {Temperature}, base seed {Seed}",
        "",
        "## Debate",
        "",
    ]
    for turn in turns:
        lines.append(f"- Round {turn['round']}, {turn['speaker']}: step {turn['step']}")
    if judge_result is not None:
        lines.append(f"- Judge: step {judge_result.get('step')}, chose {judge_result.get('winner')}, "
                     f"confidence {judge_result.get('confidence')}")
    elif not converged:
        lines.append("- Judge: no valid answer")

    lines += ["", "## Calls", ""]
    for number, call in enumerate(call_log, start=1):
        who = "judge" if call.get("is_judge") else "debater"
        lines.append(f"### Call {number}: {who} ({call['model']}) | {call['tokens_read']:,} tokens read, "
                     f"{call['tokens_written']:,} written, {call['seconds']:.1f}s | temperature {Temperature}, "
                     f"seed {call['seed']}, context window {call['num_context']:,}")
        if call["prompt_may_be_cut"]:
            lines.append("**PROMPT MAY HAVE BEEN CUT** (the prompt is as long as the context window)")
        if call["reply_was_cut"]:
            lines.append("**REPLY WAS CUT** (the reply hit the length limit)")
        if call["note"]:
            lines.append(f"Retry needed: {call['note']}")
        lines += ["", "```json", json.dumps(call["parsed"], indent=2) if call["parsed"] is not None
                  else call["raw_text"], "```", ""]

    log_file.write_text("\n".join(lines))