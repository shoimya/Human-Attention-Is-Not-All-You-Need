"""Tests for run.py: asking a model, counting every call, and writing one question's log.

Press play on this file to run all its tests. No Ollama server is needed: only the part that sends a
message over the network is replaced with a fake, so everything else is the real code.
"""

import sys
from pathlib import Path

# Here we add the project folder to Python's search path, so this file can import run.py
# when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))

import pytest

import data
import run
import settings


def fake_send_to_ollama(model: str, system_prompt: str, prompt: str) -> dict:
    """Pretend to be the Ollama server: answer with a fixed reply and fixed token counts, without a network."""
    return {"reply": f"fake reply to: {prompt}", "tokens_read": 100, "tokens_written": 20}


def test_ask_model_returns_the_reply_and_records_the_whole_call(monkeypatch):
    """One question gives one reply, and the log keeps the role, model, system prompt, full prompt, full reply and tokens."""
    # Here we swap only the network part for the fake, because the tests must run without a server.
    monkeypatch.setattr(run, "send_to_ollama", fake_send_to_ollama)
    log = []

    reply = run.ask_model("prover", "qwen3.5:9b", "You are the prover.", "Which half has the error?", log)

    assert reply == "fake reply to: Which half has the error?"
    assert len(log) == 1
    recorded_call = log[0]
    assert recorded_call["role"] == "prover"
    assert recorded_call["model"] == "qwen3.5:9b"
    assert recorded_call["system_prompt"] == "You are the prover."
    assert recorded_call["prompt"] == "Which half has the error?"
    assert recorded_call["reply"] == "fake reply to: Which half has the error?"
    assert recorded_call["tokens_read"] == 100
    assert recorded_call["tokens_written"] == 20


def test_every_question_counts_as_one_call_and_notes_do_not_count(monkeypatch):
    """Two questions plus one method note are 2 calls, 200 tokens read and 40 tokens written."""
    monkeypatch.setattr(run, "send_to_ollama", fake_send_to_ollama)
    log = []

    # Here we make two calls with a note between them; only the calls may be counted.
    run.ask_model("prover", "qwen3.5:9b", "You are the prover.", "First question", log)
    run.add_note(log, "Round 1: steps 0 to 90")
    run.ask_model("judge", "qwen3.5:2b", "You are the judge.", "Second question", log)

    assert run.count_calls(log) == {"calls": 2, "tokens_read": 200, "tokens_written": 40}


def make_question() -> data.Trajectory:
    """Build a small made-up question (run 36) whose Decisive step is 9, for tests that need no real data."""
    # Here we make 20 identical steps, because write_log only needs the question, file name and label.
    steps = [data.Step(index=step_number, agent="WebSurfer", text="...") for step_number in range(20)]
    return data.Trajectory(
        file_name="36.json",
        id="made-up",
        question="Which movie is the highest rated?",
        steps=steps,
        decisive_step=9,
        decisive_agent="Orchestrator",
        decisive_reason="made-up reason",
    )


def test_write_log_puts_system_prompts_on_top_then_every_call_and_note_in_order_then_the_result(monkeypatch, tmp_path):
    """The log shows each role's system prompt once at the top, then calls and notes in order, then the result.
    A predicted step of 11 against a Decisive step of 9 is not exactly right, but is right within ±2 steps.
    tmp_path is a temporary folder from pytest, so nothing is written to runs/."""
    monkeypatch.setattr(run, "send_to_ollama", fake_send_to_ollama)
    log = []
    run.ask_model("prover", "qwen3.5:9b", "You are the prover.", "First question", log)
    run.add_note(log, "Round 1: go left")
    run.ask_model("judge", "qwen3.5:2b", "You are the judge.", "Second question", log)

    log_file = run.write_log(log, tmp_path, "Prover-estimator debate", 36, make_question(), predicted_step=11)

    log_text = log_file.read_text()
    assert log_file == tmp_path / "run_36.md"
    # Here we check each system prompt is written exactly once, before the first call.
    assert log_text.count("You are the prover.") == 1
    assert log_text.count("You are the judge.") == 1
    assert log_text.index("You are the judge.") < log_text.index("Call 1")
    # Here we check the calls and the note keep the order they happened in.
    assert log_text.index("Call 1") < log_text.index("Round 1: go left") < log_text.index("Call 2")
    assert "First question" in log_text and "fake reply to: Second question" in log_text
    # Here we check the result at the bottom.
    assert "Answer: step 11" in log_text
    assert "Labelled Decisive step: 9 (by Orchestrator)" in log_text
    assert "Exactly right: no" in log_text
    assert "Within ±2 steps: yes" in log_text
    assert "Calls: 2" in log_text


def test_a_prompt_that_fills_the_context_window_is_marked_as_maybe_cut(monkeypatch, tmp_path):
    """If a prompt fills the model's context window, Ollama may have dropped part of it, so the call is marked
    and the log warns about it. A normal-sized prompt is not marked."""
    def fake_send_that_fills_the_window(model: str, system_prompt: str, prompt: str) -> dict:
        """Pretend the prompt used the whole context window."""
        return {"reply": "reply", "tokens_read": settings.OLLAMA_CONTEXT_WINDOW, "tokens_written": 0}

    # Here we make one normal call, then one whose prompt fills the whole context window.
    log = []
    monkeypatch.setattr(run, "send_to_ollama", fake_send_to_ollama)
    run.ask_model("prover", "qwen3.5:9b", "You are the prover.", "A short prompt", log)
    monkeypatch.setattr(run, "send_to_ollama", fake_send_that_fills_the_window)
    run.ask_model("prover", "qwen3.5:9b", "You are the prover.", "A very long prompt", log)

    assert log[0]["prompt_may_be_cut"] is False
    assert log[1]["prompt_may_be_cut"] is True

    # Here we check the warning shows once in the log, for the one call that filled the window.
    log_text = run.write_log(log, tmp_path, "Prover-estimator debate", 36, make_question(), predicted_step=9).read_text()
    assert log_text.count("PROMPT MAY HAVE BEEN CUT") == 1


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
