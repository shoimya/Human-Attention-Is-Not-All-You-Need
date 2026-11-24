"""Tests for methods/binarysearch.py: the halves, what the model sees, the prompt, failed replies and the log.

Press play on this file to run all its tests. The model is replaced by scripted answers, so no server is needed
and nothing is written to runs/.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder and the methods folder to Python's search path,
# so this file can import binarysearch.py and data.py when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "methods"))

import pytest

import data
import settings
import binarysearch


def make_run(number_of_steps: int = 10) -> data.Trajectory:
    """Build a made-up run with the given number of steps, whose Decisive step is 6."""
    steps = [data.Step(index=number, agent="WebSurfer", text=f"Made-up step {number}.") for number in range(number_of_steps)]
    return data.Trajectory(file_name="made_up.json", id="made-up", question="Made-up task?", steps=steps,
                           decisive_step=6, decisive_agent="WebSurfer", decisive_reason="made-up reason")


def fake_model(monkeypatch, halves: list[str | None]) -> list[dict]:
    """Replace the live model with scripted halves, used in order; None stands for a reply that is not valid JSON.
    Return every call's details, in order."""
    calls = []

    def answer_from_the_script(role, model, system_prompt, steps, question, answer_format, temperature, seed, log,
                               reply_limit):
        """Log the call the way send_to_ollama() does, then give the next scripted half."""
        calls.append({"role": role, "model": model, "system_prompt": system_prompt, "steps": steps,
                      "question": question, "answer_format": answer_format, "temperature": temperature,
                      "seed": seed, "reply_limit": reply_limit})
        log.append({"role": role, "model": model, "system_prompt": system_prompt, "reply": "made-up reply",
                    "thinking": "", "tokens_read": 100, "tokens_written": 5, "seconds": 1.0,
                    "temperature": temperature, "seed": seed, "context_window": 8192,
                    "prompt_may_be_cut": False, "reply_was_cut": False})
        half = halves.pop(0)
        # Here a None answer behaves like a broken reply: send_to_ollama() raises this error for it.
        if half is None:
            raise json.JSONDecodeError("not valid JSON", "made-up reply", 0)
        return {"half": half}

    # Here we swap the real model call for the script, only for this test; pytest puts the real one back afterwards.
    monkeypatch.setattr(binarysearch.runV2, "send_to_ollama", answer_from_the_script)
    return calls


def log_text_of(log_folder: Path) -> str:
    """Return the text of the one log a test wrote."""
    return next(log_folder.glob("run_0_*.md")).read_text()


# ---------- The halves ----------
def test_upper_keeps_the_earlier_half_and_lower_keeps_the_later_half(monkeypatch, tmp_path):
    """On steps 0 to 9: lower keeps 5-9, upper keeps 5-7, upper keeps 5-6, lower keeps 6, so the answer is step 6."""
    calls = fake_model(monkeypatch, ["lower half", "upper half", "upper half", "lower half"])

    answer = binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    assert answer == 6
    assert len(calls) == 4


def test_the_middle_step_belongs_to_the_upper_half(monkeypatch, tmp_path):
    """Steps 0 to 9 have their middle at step 4, so the upper half is 0-4 and the lower half is 5-9."""
    calls = fake_model(monkeypatch, ["upper half", "upper half", "upper half", "upper half"])

    binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    first_question = calls[0]["question"]
    assert "upper half (from step 0 to step 4)" in first_question
    assert "lower half (from step 5 to step 9)" in first_question


def test_step_0_stays_in_the_search(monkeypatch, tmp_path):
    """Always choosing the upper half ends on step 0, the task."""
    fake_model(monkeypatch, ["upper half"] * 4)

    answer = binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    assert answer == 0


def test_a_130_step_run_takes_at_most_8_calls(monkeypatch, tmp_path):
    """Halving 130 steps down to one takes 8 rounds when the larger half is kept every time."""
    calls = fake_model(monkeypatch, ["upper half"] * 8)

    binarysearch.run_binary_search(make_run(130), run_number=0, log_folder=tmp_path)

    assert len(calls) == 8


# ---------- What the model sees ----------
def test_the_model_sees_only_the_current_segment(monkeypatch, tmp_path):
    """After choosing the lower half of 0-9, the second call shows steps 5 to 9 and nothing before them."""
    calls = fake_model(monkeypatch, ["lower half", "upper half", "upper half", "lower half"])

    binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    second_question = calls[1]["question"]
    assert "WebSurfer: Made-up step 5." in second_question
    assert "WebSurfer: Made-up step 9." in second_question
    assert "Made-up step 4." not in second_question


def test_the_steps_are_sent_inside_the_prompt_without_step_numbers(monkeypatch, tmp_path):
    """The segment is written as "agent: content" lines inside the question, so the shared step headers never appear."""
    calls = fake_model(monkeypatch, ["upper half"] * 4)

    binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    assert calls[0]["steps"] == []
    assert "--- Step" not in calls[0]["question"]


def test_the_prompt_is_theirs_word_for_word_without_the_answer_line():
    """The prompt follows Who&When's local-model template, with the line that gives the correct answer left out."""
    prompt = binarysearch.binary_search_prompt("Made-up task?", "WebSurfer: Made-up step 0.", 0, 9, 4)

    expected_prompt = (
        "You are an AI assistant tasked with analyzing a segment of a multi-agent conversation. Multiple agents are "
        "collaborating to address a user query, with the goal of resolving the query through their collective dialogue.\n"
        "Your primary task is to identify the location of the most critical mistake within the provided segment. "
        "Determine which half of the segment contains the single step where this crucial error occurs, ultimately "
        "leading to the failure in resolving the user’s query.\n"
        "The problem to address is as follows: Made-up task?\n"
        "Review the following conversation segment from step 0 to step 9:\n\nWebSurfer: Made-up step 0.\n\n"
        "Based on your analysis, predict whether the most critical error is more likely to be located in the upper "
        "half (from step 0 to step 4) or the lower half (from step 5 to step 9) of this segment.\n"
        "Please simply output either 'upper half' or 'lower half'. You should not output anything else."
    )
    assert prompt == expected_prompt
    assert "The Answer for the problem is" not in prompt


def test_the_answer_can_only_be_one_of_the_two_halves():
    """The answer format allows exactly their two phrases and nothing else."""
    assert binarysearch.AnswerFormat["properties"]["half"]["enum"] == ["upper half", "lower half"]
    assert binarysearch.AnswerFormat["required"] == ["half"]


def test_every_call_uses_the_projects_settings(monkeypatch, tmp_path):
    """Every call uses the debater model, temperature 0.7, seed 42, their system prompt and their reply limit."""
    calls = fake_model(monkeypatch, ["upper half"] * 4)

    binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    assert {call["model"] for call in calls} == {settings.DEBATER_MODEL}
    assert {call["temperature"] for call in calls} == {0.7}
    assert {call["seed"] for call in calls} == {42}
    assert {call["reply_limit"] for call in calls} == {1024}
    assert {call["system_prompt"] for call in calls} == {"You are a helpful assistant skilled in analyzing conversations."}


# ---------- Failed replies ----------
def test_a_failed_reply_keeps_the_earlier_half(monkeypatch, tmp_path):
    """A reply that is not valid JSON counts as a call, keeps the upper half, and the log says so."""
    calls = fake_model(monkeypatch, [None, "upper half", "upper half", "upper half"])

    answer = binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    assert answer == 0
    assert len(calls) == 4
    assert "- Round 1: steps 0 to 9, no usable reply (not valid JSON) so upper half, kept 0 to 4" in log_text_of(tmp_path)


# ---------- The log ----------
def test_the_log_shows_every_round_the_answer_and_its_agent(monkeypatch, tmp_path):
    """The result lists each round's choice and the steps kept, the number of rounds, and the answer's agent."""
    fake_model(monkeypatch, ["lower half", "upper half", "upper half", "lower half"])

    binarysearch.run_binary_search(make_run(10), run_number=0, log_folder=tmp_path)

    log_text = log_text_of(tmp_path)
    assert log_text.startswith("# Binary search: run 0 (made_up.json)")
    assert "- Answer: step 6" in log_text
    assert "- Calls: 4" in log_text
    assert "- Round 1: steps 0 to 9, lower half, kept 5 to 9" in log_text
    assert "- Round 4: steps 5 to 6, lower half, kept 6 to 6" in log_text
    assert "- Rounds: 4" in log_text
    assert "- Agent at the answer: WebSurfer" in log_text


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
