"""Send a run's steps to a live model, count every call, and log every interaction. Every method uses these functions.

Everything in this file is built specifically for Visual Studio Code on a Mac.

How every method uses this file:
    A role (for example prover, estimator or judge) has its rules in a system prompt. It is sent the run's steps,
    marked by format_steps_as_text(), followed by a question. The model answers in JSON. The method then either takes
    that answer as the end result or puts it in the next role's question. Every call is added to the question's log.

What is in this file:
    format_steps_as_text()  the one marker function: turns a run's steps into one block of numbered text
    context_window_for()    how many tokens one call's context window needs: its prompt plus room for the reply
    send_to_ollama()        one call: one role's system prompt, the steps and a question go to the live model,
                            the call is logged, and the model's JSON answer comes back
    count_calls()           how many calls and tokens a question used (one call = one prompt + one reply)
    write_log()             writes one question's log, runs/<method>/<start date>/run_<number>_<time>.md

How to use it:
    Press play on this file. It prints run 1 as the models see it, so you can check the step markers by hand.
    Then it asks the judge which step in run 1 went wrong first, prints the answer and writes the log to runs/demo/.
"""

import json
import math
import time
import urllib.request
from pathlib import Path

import data
import settings

# Here we say how close a predicted step must be to the Decisive step to count as right "within tolerance".
HIT_TOLERANCE_IN_STEPS = 2

# Here we say how close to the context window a prompt may come before we warn that part of it may have been dropped.
CONTEXT_WINDOW_SAFETY_MARGIN = 100

# Here we set how each call's context window is sized (context_window_for()).
# Measured in ticket 03: one token is about 3.6 characters. Some text needs more tokens than that, so we add 25%.
CHARACTERS_PER_TOKEN = 3.6
TOKEN_ESTIMATE_SAFETY_FACTOR = 1.25

# Here we switch the models' thinking on (True) or off (False) for every call.
THINKING_ON = False

# Here we leave far more room when the model thinks, because its thinking counts towards the reply limit;
# with only 4,096 tokens a long think would be cut before the JSON answer.
ROOM_FOR_REPLY_IN_TOKENS = 16384 if THINKING_ON else 4096

# Here we wait longer for a reply when the model thinks, because thinking can write thousands of tokens.
SECONDS_TO_WAIT_FOR_A_REPLY = 7200 if THINKING_ON else 1800

# Here we round every window up to whole blocks of 8,192 tokens, so most runs share a few sizes: Ollama reloads
# the model each time the window size changes.
CONTEXT_WINDOW_BLOCK_IN_TOKENS = 8192


def format_steps_as_text(steps: list[data.Step]) -> str:
    """Turn a run's steps into one block of text: each step gets a header with its number and agent, then its text."""
    # Here we keep each step's own number, so a slice such as steps 10 to 20 is still called Step 10 to Step 20.
    marked_steps = [f"--- Step {step.index} | {step.agent} ---\n{step.text}\n" for step in steps]
    # Here we put a blank line between steps.
    return "\n".join(marked_steps)


def context_window_for(system_prompt: str, prompt: str) -> int:
    """Return a context window just big enough for this call's prompt and its reply, in whole blocks of 8,192 tokens,
    and never bigger than the largest window this machine holds (settings.py)."""
    # Here we estimate the prompt's tokens from its characters, then add the safety margin and the room for the reply.
    estimated_prompt_tokens = (len(system_prompt) + len(prompt)) / CHARACTERS_PER_TOKEN
    needed_tokens = estimated_prompt_tokens * TOKEN_ESTIMATE_SAFETY_FACTOR + ROOM_FOR_REPLY_IN_TOKENS

    # Here we round up to the next whole block, so the window is never smaller than what is needed.
    number_of_blocks = math.ceil(needed_tokens / CONTEXT_WINDOW_BLOCK_IN_TOKENS)
    rounded_window = number_of_blocks * CONTEXT_WINDOW_BLOCK_IN_TOKENS

    # Here we never ask for more than this machine holds; a longer prompt is then cut and its log warns about it.
    return min(rounded_window, settings.OLLAMA_CONTEXT_WINDOW)


def send_to_ollama(role: str, model: str, system_prompt: str, steps: list[data.Step], question: str,
                   answer_format: dict, temperature: float, seed: int, log: list) -> dict:
    """Make one call: send a role's system prompt, the steps and a question to the live model and return its JSON answer.

    One call = one prompt sent to one model and its one reply. Every call is added to the log in full,
    so counting the log counts the calls. Each method sets its own temperature and seed.

    Inputs:
        role            who is asking, logged
        model           which Ollama model answers
        system_prompt   the role's rules
        steps           the run's steps sent
        question        asked after the steps
        answer_format   JSON shape of answer
        temperature     how random replies are
        seed            fixes the randomness
        log             list collecting every call
    """
    # Here we put the marked steps first and the question after them, as one prompt.
    prompt = format_steps_as_text(steps) + "\n" + question

    # Here we size this call's context window to its own prompt and reply.
    context_window = context_window_for(system_prompt, prompt)

    # Here we build the message in Ollama's chat format: the role's rules as the system prompt, then the prompt.
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        # Here we ask for the whole reply at once, and switch thinking off so the reply is only the answer.
        "stream": False,
        "think": THINKING_ON,
        # Here we make the model answer in the JSON shape the method asks for.
        "format": answer_format,
        # Here we let the model read this call's whole context window; without it Ollama reads only
        # about 2,000 tokens and silently drops the rest of the prompt.
        # num_predict stops the reply at the room kept free for it, so the reply never pushes out the prompt.
        # The temperature and seed are the method's own, so its randomness is fixed and can be repeated.
        "options": {
            "num_ctx": context_window,
            "num_predict": ROOM_FOR_REPLY_IN_TOKENS,
            "temperature": temperature,
            "seed": seed,
        },
    }
    # Here we address the message to this project's server (port 11500) as JSON.
    request = urllib.request.Request(
        settings.OLLAMA_ADDRESS + "/api/chat",
        data=json.dumps(request_body).encode(),
        headers={"Content-Type": "application/json"},
    )

    # Here we wait for the reply; a long prompt on a Mac can take minutes, so we allow up to 30 minutes.
    start_time = time.time()
    with urllib.request.urlopen(request, timeout=SECONDS_TO_WAIT_FOR_A_REPLY) as response:
        server_answer = json.load(response)
    seconds = round(time.time() - start_time, 1)

    # Here we read Ollama's token counts: prompt_eval_count = tokens read, eval_count = tokens written.
    tokens_read = server_answer.get("prompt_eval_count", 0)
    reply = server_answer["message"]["content"]

    # Here we keep the model's thinking, which Ollama returns apart from the answer; it is empty when thinking is off.
    thinking = server_answer["message"].get("thinking", "")

    # Here we record the whole call before reading the answer, so the log keeps it even if the reply is not valid JSON.
    log.append({
        "role": role,
        "model": model,
        "system_prompt": system_prompt,
        # "prompt": prompt,
        "reply": reply,
        "thinking": thinking,
        "tokens_read": tokens_read,
        "tokens_written": server_answer.get("eval_count", 0),
        "seconds": seconds,
        "temperature": temperature,
        "seed": seed,
        "context_window": context_window,
        # Here we mark a call whose prompt filled its context window: Ollama may have dropped part of it.
        "prompt_may_be_cut": tokens_read >= context_window - CONTEXT_WINDOW_SAFETY_MARGIN,
        # Here we mark a reply that Ollama stopped because it reached the reply limit ("length"), not because it ended.
        "reply_was_cut": server_answer.get("done_reason") == "length",
    })

    # Here we turn the JSON reply into a Python dictionary, for example {"step": 4}.
    return json.loads(reply)


def count_calls(log: list) -> dict:
    """Return how many calls the question used and how many tokens they read and wrote."""
    # Here every entry in the log is one call, so the number of entries is the number of calls.
    return {
        "calls": len(log),
        "tokens_read": sum(call["tokens_read"] for call in log),
        "tokens_written": sum(call["tokens_written"] for call in log),
    }


def write_log(log: list, run_folder: Path, method_name: str, run_number: int,
              question: data.Trajectory, predicted_step: int | None, extra_result_lines: list[str] = []) -> Path:
    """Write one question's log, run_<number>_<time>.md: system prompts on top, every call in order, result last.

    predicted_step is None when no call gave a valid step. extra_result_lines are the method's own lines for the
    result, for example "Calls allowed: 10".

    Inputs:
        log                 every call made
        run_folder          where the log goes
        method_name         log's title, e.g. One-shot
        run_number          which run, 1 to 58
        question            the run and label
        predicted_step      the method's answer
        extra_result_lines  method's own result lines
    """
    # Here we work out the totals and whether the answer is right, for the result at the bottom.
    # With no answer, it is neither exactly right nor within tolerance.
    totals = count_calls(log)
    has_answer = predicted_step is not None
    exactly_right = has_answer and predicted_step == question.decisive_step
    within_tolerance = has_answer and abs(predicted_step - question.decisive_step) <= HIT_TOLERANCE_IN_STEPS

    lines = [
        f"# {method_name}: run {run_number} ({question.file_name})",
        "",
        f"**Question:** {question.question}",
        "",
        f"**Thinking:** {'on' if THINKING_ON else 'off'}",
        "",
        "## System prompts",
        "",
    ]

    # Here we write each role's model and system prompt once, in the order the roles first speak.
    # Long texts go between ```` lines, so a reply that contains Markdown or code cannot break the log's layout.
    system_prompt_by_role = {}
    for entry in log:
        if entry["role"] not in system_prompt_by_role:
            system_prompt_by_role[entry["role"]] = entry["system_prompt"]
            lines += [f"### {entry['role']} ({entry['model']})", "", "````text", entry["system_prompt"], "````", ""]

    lines += ["## Interactions", ""]

    # Here we write every call in the order it happened.
    for call_number, entry in enumerate(log, start=1):
        lines += [
            f"### Call {call_number}: {entry['role']} ({entry['model']}) | "
            f"{entry['tokens_read']} tokens read, {entry['tokens_written']} written, {entry['seconds']} s | "
            f"temperature {entry['temperature']}, seed {entry['seed']}, context window {entry['context_window']}",
            "",
        ]
        # Here we warn loudly if this call's prompt filled its context window, because the model may not have seen all of it.
        if entry["prompt_may_be_cut"]:
            lines += [f"**WARNING: PROMPT MAY HAVE BEEN CUT** (it filled the {entry['context_window']}-token "
                      "context window, so the model may not have seen all of it)", ""]
        # Here we warn loudly if the reply was stopped at the reply limit, because its end (often the JSON) is missing.
        if entry["reply_was_cut"]:
            lines += [f"**WARNING: REPLY WAS CUT** (it reached the {ROOM_FOR_REPLY_IN_TOKENS}-token reply limit)", ""]
        # Here we show the system prompt again only if this role's system prompt changed during the question.
        if entry["system_prompt"] != system_prompt_by_role[entry["role"]]:
            lines += ["**System prompt changed to:**", "````text", entry["system_prompt"], "````", ""]
        if entry.get("thinking"):
            lines += ["**Thinking:**", "````text", entry["thinking"], "````", ""]
        # lines += ["**Prompt:**", "````text", entry["prompt"], "````", "", "**Reply:**", "````text", entry["reply"], "````", ""]
        lines += ["**Reply:**", "````text", entry["reply"], "````", ""] #I no longer want to see the prompt in the log
    # Here we write the result: the answer, the label, whether it is right, and the totals.
    lines += [
        "## Result",
        "",
        f"- Answer: step {predicted_step}" if has_answer else "- Answer: no answer",
        f"- Labelled Decisive step: {question.decisive_step} (by {question.decisive_agent})",
        f"- Exactly right: {'yes' if exactly_right else 'no'}",
        f"- Within ±{HIT_TOLERANCE_IN_STEPS} steps: {'yes' if within_tolerance else 'no'}",
        f"- Calls: {totals['calls']}",
        f"- Tokens read: {totals['tokens_read']}, tokens written: {totals['tokens_written']}",
    ]
    # Here we add the method's own result lines, for example the calls allowed and each call's vote.
    lines += [f"- {line}" for line in extra_result_lines]
    lines += [""]

    # Here we save the log as run_<number>_<time>.md in this run's folder, creating the folder if it is new.
    # The time in the name means running the same test twice on one day keeps both logs.
    run_folder.mkdir(parents=True, exist_ok=True)
    log_file = run_folder / f"run_{run_number}_{time.strftime('%H-%M-%S')}.md"
    log_file.write_text("\n".join(lines))
    return log_file


if __name__ == "__main__":
    import sys

    # Here we choose the run to show and ask about.
    run_number = 1
    run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / f"{run_number}.json")

    # Here we print the run exactly as the models will see it, so you can check the step markers by hand.
    print(format_steps_as_text(run.steps))

