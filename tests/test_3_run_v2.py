"""Tests for runV2.py: marking a run's steps, one call to the live model, counting calls, and writing the log.

Press play on this file to run all its tests. The call test talks to the live model, so start this project's
Ollama server first (setup/start_ollama_server.py); if it is not running, that test is skipped.
"""

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


def make_call(role: str, system_prompt: str, reply: str) -> dict:
    """Build one log entry by hand, shaped exactly like the ones send_to_ollama() adds."""
    return {"role": role, "model": "qwen3.5:9b", "system_prompt": system_prompt, "prompt": "the steps and a question",
            "reply": reply, "tokens_read": 100, "tokens_written": 20, "seconds": 1.0, "prompt_may_be_cut": False}


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
