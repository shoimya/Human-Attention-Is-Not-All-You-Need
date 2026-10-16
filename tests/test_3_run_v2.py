"""Tests for runV2.py: marking a run's steps, one call to the live model, counting calls, and writing the log.

Press play on this file to run all its tests. The call test talks to the live model, so start this project's
Ollama server first (setup/start_ollama_server.py); if it is not running, that test is skipped.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder and the setup folder to Python's search path, so this file can import
# runV2.py, data.py and the server check when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "setup"))

import pytest

import data
import runV2
import settings
from start_ollama_server import ollama_server_is_running


def make_steps() -> list[data.Step]:
    """Build three made-up steps, including text with its own line breaks and spaces, to check nothing is changed."""
    return [
        data.Step(index=0, agent="human", text="Find the movie."),
        data.Step(index=1, agent="Orchestrator (thought)", text="Plan:\n1. Search\n2. Check  ratings"),
        data.Step(index=2, agent="WebSurfer", text="I clicked 'IMDb'."),
    ]


def test_steps_become_one_block_of_numbered_text_with_every_character_kept():
    """Each step gets a header with its number and agent, then its text exactly as it was, then a blank line."""
    expected_text = (
        "--- Step 0 | human ---\n"
        "Find the movie.\n"
        "\n"
        "--- Step 1 | Orchestrator (thought) ---\n"
        "Plan:\n1. Search\n2. Check  ratings\n"
        "\n"
        "--- Step 2 | WebSurfer ---\n"
        "I clicked 'IMDb'.\n"
    )

    assert runV2.format_steps_as_text(make_steps()) == expected_text


def test_a_slice_of_steps_keeps_the_original_step_numbers():
    """Sending only steps 1 and 2 must still call them Step 1 and Step 2, so answers match the labels."""
    steps_text = runV2.format_steps_as_text(make_steps()[1:])

    assert steps_text.startswith("--- Step 1 | Orchestrator (thought) ---\n")
    assert "--- Step 0 |" not in steps_text


def test_the_live_model_answers_in_json_and_the_call_is_logged_and_counted():
    """One call to the live judge model returns {"step": <number>}; the log keeps the steps followed by the question."""
    # Here we skip, rather than fail, when the server is off, because this test needs the live model.
    if not ollama_server_is_running():
        pytest.skip("This project's Ollama server is not running; press play on setup/start_ollama_server.py first.")
    log = []

    answer = runV2.send_to_ollama(
        role="judge",
        model=settings.JUDGE_MODEL,
        system_prompt="You read a failed agent run and find the first step where it went wrong.",
        steps=make_steps(),
        question="Which step is the first one that went wrong? Answer with its step number.",
        answer_format={"type": "object", "properties": {"step": {"type": "integer"}}, "required": ["step"]},
        temperature=0.7,
        seed=42,
        log=log,
    )

    # Here we check the shape of the answer, not its value, because the model decides the value.
    assert isinstance(answer["step"], int)
    # Here we check the text sent is exactly the marked steps, a blank line, then the question.
    expected_prompt = runV2.format_steps_as_text(make_steps()) + "\nWhich step is the first one that went wrong? Answer with its step number."
    assert log[0]["prompt"] == expected_prompt
    assert runV2.count_calls(log)["calls"] == 1
    assert log[0]["tokens_read"] > 0


def test_a_tiny_prompt_still_gets_one_whole_block_of_8192_tokens():
    """The smallest context window is one block, so even a one-line prompt has room for its reply."""
    assert runV2.context_window_for("Find the mistake.", "Which step?") == runV2.CONTEXT_WINDOW_BLOCK_IN_TOKENS


def test_the_context_window_fits_the_prompt_and_the_reply_and_is_the_smallest_whole_block():
    """A 36,000-character prompt gets the smallest multiple of 8192 that holds its estimated tokens, the safety
    margin and the room for the reply."""
    system_prompt = "Find the mistake."
    prompt = "x" * 36000

    context_window = runV2.context_window_for(system_prompt, prompt)

    # Here we work out the tokens the window must hold, the same way the function estimates them.
    estimated_prompt_tokens = (len(system_prompt) + len(prompt)) / runV2.CHARACTERS_PER_TOKEN
    needed_tokens = estimated_prompt_tokens * runV2.TOKEN_ESTIMATE_SAFETY_FACTOR + runV2.ROOM_FOR_REPLY_IN_TOKENS
    assert context_window >= needed_tokens
    assert context_window % runV2.CONTEXT_WINDOW_BLOCK_IN_TOKENS == 0
    # Here we check it is the smallest such block: one block less would be too small.
    assert context_window - runV2.CONTEXT_WINDOW_BLOCK_IN_TOKENS < needed_tokens


def test_the_context_window_never_goes_above_the_largest_this_machine_holds():
    """A prompt far too long for this machine gets the largest window from settings.py, never more."""
    assert runV2.context_window_for("Find the mistake.", "x" * 10_000_000) == settings.OLLAMA_CONTEXT_WINDOW


class FakeServerReply:
    """Stands in for the Ollama server's reply, so send_to_ollama() can be tested without a server."""

    def __init__(self, server_answer: dict):
        """Keep the answer as the bytes a real server would send."""
        self.body = json.dumps(server_answer).encode()

    def read(self) -> bytes:
        """Return the whole reply, as json.load() asks for it."""
        return self.body

    def __enter__(self):
        """Let send_to_ollama() use the reply in a `with` block, like a real one."""
        return self

    def __exit__(self, *error_details) -> bool:
        """Close nothing and let any error through."""
        return False


def fake_ollama_server(monkeypatch, done_reason: str) -> list[dict]:
    """Replace the server with a fake that answers {"step": 1} and keeps every request it receives."""
    received_requests = []

    def answer_like_ollama(request, timeout):
        """Keep the request's JSON body and answer like Ollama does."""
        received_requests.append(json.loads(request.data))
        return FakeServerReply({"message": {"content": '{"step": 1}'}, "prompt_eval_count": 50, "eval_count": 5,
                                "done_reason": done_reason})

    # Here we swap the real urlopen for the fake one, only for this test; pytest puts the real one back afterwards.
    monkeypatch.setattr(runV2.urllib.request, "urlopen", answer_like_ollama)
    return received_requests


def test_each_call_asks_for_a_window_that_fits_its_prompt_and_logs_its_seed_temperature_and_window(monkeypatch):
    """The request carries this call's own context window, reply limit, temperature and seed; the log keeps them."""
    received_requests = fake_ollama_server(monkeypatch, done_reason="stop")
    log = []

    runV2.send_to_ollama("one-shot", "qwen3.5:9b", "Find the mistake.", make_steps(), "Which step?",
                         {"type": "object"}, temperature=0.7, seed=43, log=log)

    # Here we work out the window this prompt should get: the marked steps, a blank line, then the question.
    expected_window = runV2.context_window_for("Find the mistake.", runV2.format_steps_as_text(make_steps()) + "\nWhich step?")
    sent_options = received_requests[0]["options"]
    assert sent_options["num_ctx"] == expected_window
    assert sent_options["num_predict"] == runV2.ROOM_FOR_REPLY_IN_TOKENS
    assert sent_options["temperature"] == 0.7 and sent_options["seed"] == 43
    assert log[0]["context_window"] == expected_window
    assert log[0]["temperature"] == 0.7 and log[0]["seed"] == 43
    assert log[0]["reply_was_cut"] is False


def test_a_reply_that_hit_the_reply_limit_is_marked_as_cut(monkeypatch):
    """When Ollama stops a reply because it reached the reply limit, the log marks the reply as cut."""
    fake_ollama_server(monkeypatch, done_reason="length")
    log = []

    runV2.send_to_ollama("one-shot", "qwen3.5:9b", "Find the mistake.", make_steps(), "Which step?",
                         {"type": "object"}, temperature=0.7, seed=43, log=log)

    assert log[0]["reply_was_cut"] is True


def make_call(role: str, system_prompt: str, reply: str) -> dict:
    """Build one log entry by hand, shaped exactly like the ones send_to_ollama() adds."""
    return {"role": role, "model": "qwen3.5:9b", "system_prompt": system_prompt, "prompt": "the steps and a question",
            "reply": reply, "tokens_read": 100, "tokens_written": 20, "seconds": 1.0, "temperature": 0.7, "seed": 42,
            "context_window": 8192, "prompt_may_be_cut": False, "reply_was_cut": False}


def make_question() -> data.Trajectory:
    """Build a made-up question whose Decisive step is 2, matching make_steps()."""
    return data.Trajectory(file_name="36.json", id="made-up", question="Which movie?", steps=make_steps(),
                           decisive_step=2, decisive_agent="WebSurfer", decisive_reason="made-up reason")


def test_each_calls_heading_shows_its_temperature_seed_and_context_window(tmp_path):
    """A call's heading in the log says how it was asked, so anyone can repeat it exactly."""
    log_text = runV2.write_log([make_call("one-shot", "Find the mistake.", '{"step": 2}')], tmp_path, "One-shot", 36,
                               make_question(), predicted_step=2).read_text()

    assert "temperature 0.7, seed 42, context window 8192" in log_text


def test_the_cut_warnings_name_the_calls_own_context_window(tmp_path):
    """A call whose prompt filled its own window, and whose reply hit the limit, gets both warnings in the log."""
    cut_call = make_call("one-shot", "Find the mistake.", '{"step": 2')
    cut_call["context_window"] = 16384
    cut_call["prompt_may_be_cut"] = True
    cut_call["reply_was_cut"] = True

    log_text = runV2.write_log([cut_call], tmp_path, "One-shot", 36, make_question(), predicted_step=None).read_text()

    assert "PROMPT MAY HAVE BEEN CUT** (it filled the 16384-token context window" in log_text
    assert "REPLY WAS CUT" in log_text


def test_write_log_shows_each_system_prompt_once_every_call_and_the_result(tmp_path):
    """A log with two prover calls and one judge call has each system prompt once, all three calls, and the result.
    tmp_path is a temporary folder from pytest, so nothing is written to runs/."""
    log = [
        make_call("prover", "You are the prover.", '{"step": 2}'),
        make_call("judge", "You are the judge.", '{"agree": true}'),
        make_call("prover", "You are the prover.", '{"step": 2}'),
    ]
    # Here we make a made-up question whose Decisive step is 2, matching the steps above.
    question = data.Trajectory(file_name="36.json", id="made-up", question="Which movie?", steps=make_steps(),
                               decisive_step=2, decisive_agent="WebSurfer", decisive_reason="made-up reason")

    log_text = runV2.write_log(log, tmp_path, "One-shot", 36, question, predicted_step=2).read_text()

    assert log_text.count("You are the prover.") == 1
    assert "Call 1" in log_text and "Call 2" in log_text and "Call 3" in log_text
    assert "Exactly right: yes" in log_text
    assert "Calls: 3" in log_text
    assert "Tokens read: 300, tokens written: 60" in log_text


def test_write_log_puts_the_time_in_the_file_name_and_adds_the_methods_own_result_lines(tmp_path):
    """The file is run_<number>_<time>.md, so a second run on the same day does not replace the first,
    and the method's own lines (for example the calls allowed) are in the result."""
    question = data.Trajectory(file_name="36.json", id="made-up", question="Which movie?", steps=make_steps(),
                               decisive_step=2, decisive_agent="WebSurfer", decisive_reason="made-up reason")

    log_file = runV2.write_log([make_call("one-shot", "Find the mistake.", '{"step": 2}')], tmp_path, "One-shot", 36,
                               question, predicted_step=2, extra_result_lines=["Calls allowed: 10"])

    # Here we check the name looks like run_36_23-10-05.md: the run number, then the time as hours-minutes-seconds.
    assert log_file.name.startswith("run_36_") and len(log_file.stem) == len("run_36_23-10-05")
    assert "- Calls allowed: 10" in log_file.read_text()


def test_write_log_says_no_answer_when_no_call_gave_a_valid_step(tmp_path):
    """If every call failed to give a valid step, the log says so instead of crashing."""
    question = data.Trajectory(file_name="36.json", id="made-up", question="Which movie?", steps=make_steps(),
                               decisive_step=2, decisive_agent="WebSurfer", decisive_reason="made-up reason")

    log_text = runV2.write_log([make_call("one-shot", "Find the mistake.", "not json")], tmp_path, "One-shot", 36,
                               question, predicted_step=None).read_text()

    assert "- Answer: no answer" in log_text
    assert "Exactly right: no" in log_text


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
