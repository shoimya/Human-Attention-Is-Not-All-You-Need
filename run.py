"""Run the methods (the debates and, later, the baselines) on the Trajectories and log every interaction.

Everything in this file is built specifically for Visual Studio Code on a Mac.

How to use it:
    Press play on this file. If this project's Ollama server is not running, it starts it and stops it again at the
    end; if the server is already running, it uses it and leaves it running. Today it asks the prover and the judge
    one short question each, to show ask_model() working. Ticket 04 makes it run the prover-estimator debate on the
    pilot run.

What is in this file:
    ask_model()             ticket 03: the only way to ask a model something; records every call in full
    send_to_ollama()        ticket 03: the one part that talks to the Ollama server (the tests replace it)
    add_note()              ticket 03: a method's own note in the log, for example "Round 2: go left"
    count_calls()           ticket 03: how many calls and tokens a question used (one call = one prompt + one reply)
    write_log()             ticket 03: writes one question's log, runs/<method>/<start time>/run_<number>.md
    write_results_file()    ticket 04: writes results.jsonl, one line per question (skeleton for now)
    run_<method>()          ticket 04 onwards: one per method, for example run_prover_estimator_debate("36.json")
"""

import json
import time
import urllib.request
from pathlib import Path

import data
import settings

# Here we say how close a predicted step must be to the Decisive step to count as right "within tolerance".
HIT_TOLERANCE_IN_STEPS = 2

# Here we say how close to the context window a prompt may come before we warn that part of it may have been dropped.
CONTEXT_WINDOW_SAFETY_MARGIN = 100


def ask_model(role: str, model: str, system_prompt: str, prompt: str, log: list) -> str:
    """Ask one model one question and return its reply. This is the only way the project asks a model anything.

    One call = one prompt sent to one model and its one reply, whatever the role or the length.
    Every call is added to the question's log, in full, so the log shows exactly what each role was told and said.
    """
    # Here we note the time before asking, so the log can say how long the model took to answer.
    start_time = time.time()
    answer = send_to_ollama(model, system_prompt, prompt)

    # Here we record the whole call: who asked, which model, the full texts, the tokens and the time it took.
    log.append({
        "type": "call",
        "role": role,
        "model": model,
        "system_prompt": system_prompt,
        "prompt": prompt,
        "reply": answer["reply"],
        "tokens_read": answer["tokens_read"],
        "tokens_written": answer["tokens_written"],
        "seconds": round(time.time() - start_time, 1),
        # Here we mark a call whose prompt filled the context window: Ollama may have dropped part of it.
        "prompt_may_be_cut": answer["tokens_read"] >= settings.OLLAMA_CONTEXT_WINDOW - CONTEXT_WINDOW_SAFETY_MARGIN,
    })
    return answer["reply"]


def send_to_ollama(model: str, system_prompt: str, prompt: str) -> dict:
    """Send one system prompt and one prompt to this project's Ollama server and return the reply and token counts."""
    # Here we build the message in Ollama's chat format: the system prompt first, then the prompt.
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        # Here we ask for the whole reply at once, and switch thinking off so the reply is only the answer.
        "stream": False,
        "think": False,
        # Here we let the model read up to the context window from settings.py; without it Ollama reads only
        # about 2,000 tokens and silently drops the rest of the prompt.
        "options": {"num_ctx": settings.OLLAMA_CONTEXT_WINDOW},
    }
    # Here we address the message to this project's server (port 11500) as JSON.
    request = urllib.request.Request(
        settings.OLLAMA_ADDRESS + "/api/chat",
        data=json.dumps(request_body).encode(),
        headers={"Content-Type": "application/json"},
    )

    # Here we wait for the reply; a long prompt on a Mac can take minutes, so we allow up to 30 minutes.
    with urllib.request.urlopen(request, timeout=1800) as response:
        server_answer = json.load(response)

    return {
        "reply": server_answer["message"]["content"],
        # Here we read Ollama's token counts: prompt_eval_count = tokens read, eval_count = tokens written.
        "tokens_read": server_answer.get("prompt_eval_count", 0),
        "tokens_written": server_answer.get("eval_count", 0),
    }


def add_note(log: list, note: str) -> None:
    """Add a method's own note to the question's log, for example "Round 2: steps 0 to 45; go left"."""
    # Here we mark the entry as a note, so count_calls() does not count it and write_log() shows it as a note.
    log.append({"type": "note", "text": note})


def count_calls(log: list) -> dict:
    """Return how many calls the question used and how many tokens they read and wrote. Notes are not calls."""
    # Here we keep only the calls; notes are written by the method, not sent to a model.
    calls = [entry for entry in log if entry["type"] == "call"]
    return {
        "calls": len(calls),
        "tokens_read": sum(call["tokens_read"] for call in calls),
        "tokens_written": sum(call["tokens_written"] for call in calls),
    }


def write_log(log: list, run_folder: Path, method_name: str, run_number: int,
              question: data.Trajectory, predicted_step: int) -> Path:
    """Write one question's log, run_<number>.md: system prompts on top, every call and note in order, result last."""
    # Here we work out the totals and whether the answer is right, for the result at the bottom.
    totals = count_calls(log)
    exactly_right = predicted_step == question.decisive_step
    within_tolerance = abs(predicted_step - question.decisive_step) <= HIT_TOLERANCE_IN_STEPS

    lines = [
        f"# {method_name}: run {run_number} ({question.file_name})",
        "",
        f"**Question:** {question.question}",
        "",
        "## System prompts",
        "",
    ]

    # Here we write each role's model and system prompt once, in the order the roles first speak.
    # Long texts go between ```` lines, so a reply that contains Markdown or code cannot break the log's layout.
    system_prompt_by_role = {}
    for entry in log:
        if entry["type"] == "call" and entry["role"] not in system_prompt_by_role:
            system_prompt_by_role[entry["role"]] = entry["system_prompt"]
            lines += [f"### {entry['role']} ({entry['model']})", "", "````text", entry["system_prompt"], "````", ""]

    lines += ["## Interactions", ""]

    # Here we write every call and every note in the order they happened.
    call_number = 0
    for entry in log:
        if entry["type"] == "note":
            lines += [f"> **Note:** {entry['text']}", ""]
            continue

        call_number += 1
        lines += [
            f"### Call {call_number}: {entry['role']} ({entry['model']}) | "
            f"{entry['tokens_read']} tokens read, {entry['tokens_written']} written, {entry['seconds']} s",
            "",
        ]
        # Here we warn loudly if this call's prompt filled the context window, because the model may not have seen all of it.
        if entry["prompt_may_be_cut"]:
            lines += [f"**WARNING: PROMPT MAY HAVE BEEN CUT** (it filled the {settings.OLLAMA_CONTEXT_WINDOW}-token "
                      "context window, so the model may not have seen all of it)", ""]
        # Here we show the system prompt again only if this role's system prompt changed during the question.
        if entry["system_prompt"] != system_prompt_by_role[entry["role"]]:
            lines += ["**System prompt changed to:**", "````text", entry["system_prompt"], "````", ""]
        lines += ["**Prompt:**", "````text", entry["prompt"], "````", "", "**Reply:**", "````text", entry["reply"], "````", ""]

    # Here we write the result: the answer, the label, whether it is right, and the totals.
    lines += [
        "## Result",
        "",
        f"- Answer: step {predicted_step}",
        f"- Labelled Decisive step: {question.decisive_step} (by {question.decisive_agent})",
        f"- Exactly right: {'yes' if exactly_right else 'no'}",
        f"- Within ±{HIT_TOLERANCE_IN_STEPS} steps: {'yes' if within_tolerance else 'no'}",
        f"- Calls: {totals['calls']}",
        f"- Tokens read: {totals['tokens_read']}, tokens written: {totals['tokens_written']}",
        "",
    ]

    # Here we save the log as run_<number>.md in this run's folder, creating the folder if it is new.
    run_folder.mkdir(parents=True, exist_ok=True)
    log_file = run_folder / f"run_{run_number}.md"
    log_file.write_text("\n".join(lines))
    return log_file


def write_results_file(results: list[dict], run_folder: Path) -> None:
    """Write results.jsonl into the run's folder: one line per question (Trajectory), for code to read back.

    SKELETON: not implemented yet.

    What it is supposed to do:
        - run_folder is this run's log folder, for example runs/prover_estimator_debate/<start time>/,
          the same folder that holds the 58 readable logs (run_1.md ... run_58.md).
        - results holds one entry per question, with:
            run number, file name (for example "36.json"), method name,
            predicted step, labelled Decisive step, whether the prediction was right
            (exactly, and within ±2 steps), number of model calls, tokens read, tokens written.
        - Each entry becomes one line of JSON in run_folder / "results.jsonl".
        - Scoring, the TA's equal-calls check (every baseline gets the same number of calls as the
          debate used on the same run) and the figures read this file, so they never have to
          read numbers out of the .md logs written for people.
    """
    pass


if __name__ == "__main__":
    import sys

    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server

    # Here we start the server only if it is not running, and remember whether we did,
    # so at the end we stop only a server this file started and never one someone else is using.
    started_here = start_ollama_server()

    # Here "try ... finally" makes sure the server we started is stopped even if something below fails.
    try:
        # Here we ask the prover and the judge one short question each, to show ask_model() working with real models.
        demo_log = []
        ask_model("prover", settings.DEBATER_MODEL, "You are a careful assistant. Answer in one sentence.",
                  "What is the step where an agent run went wrong usually called?", demo_log)
        ask_model("judge", settings.JUDGE_MODEL, "You are a strict judge. Answer yes or no, then one reason.",
                  "Is 2 + 2 equal to 4?", demo_log)

        # Here we print each call from the log, which also shows that ask_model() recorded them.
        for call in demo_log:
            print(f"{call['role']} ({call['model']}), {call['seconds']} s: {call['reply']}")
        print("Counted:", count_calls(demo_log))
        print("Ticket 04 adds the prover-estimator debate: run_prover_estimator_debate().")
    finally:
        if started_here:
            stop_ollama_server()
