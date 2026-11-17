"""Tests for methods/The_Interrogation_Room.py: who speaks when, who sees which steps, the halving, failed replies and the log.

Press play on this file to run all its tests. The models are replaced by scripted answers, so no server is needed
and nothing is written to runs/.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder and the methods folder to Python's search path,
# so this file can import The_Interrogation_Room.py and data.py when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "methods"))

import pytest

import data
import settings
import The_Interrogation_Room


def make_run(number_of_steps: int = 130) -> data.Trajectory:
    """Build a made-up run with the given number of steps, whose Decisive step is 3."""
    steps = [data.Step(index=number, agent="WebSurfer", text=f"Made-up step {number}.") for number in range(number_of_steps)]
    return data.Trajectory(file_name="made_up.json", id="made-up", question="Made-up task?", steps=steps,
                           decisive_step=3, decisive_agent="WebSurfer", decisive_reason="made-up reason")


def summary_says() -> dict:
    """Build the Witness's summary, with a marker to spot it in later questions."""
    return {"reasoning": "made-up reasoning", "summary": "summary-marker"}


def witness_names(step: int, marker: str) -> dict:
    """Build the Witness's testimony or final answer naming the given step, with a marker to spot it later."""
    return {"reasoning": marker, "step": step, "reason": f"See step {step}."}


def interrogator_says() -> dict:
    """Build the Interrogator's feedback, with a marker to spot it in later questions."""
    return {"reasoning": "made-up reasoning", "feedback": "interrogator-marker"}


def witness_answers(steps: list[int | None], marker: str) -> list[dict | None]:
    """Build one Witness answer per step; a step of None stands for a reply that is not valid JSON."""
    return [None if step is None else witness_names(step, marker) for step in steps]


def a_script(testimony_steps: list[int | None], final_steps: list[int | None]) -> dict:
    """Build one answer per call: one testimony and one final step per round, and feedback for every round."""
    return {
        "witness summary": [summary_says()],
        "witness testimony": witness_answers(testimony_steps, "testimony-marker"),
        "interrogator": [interrogator_says() for step in testimony_steps],
        "witness final": witness_answers(final_steps, "final-marker"),
    }


def fake_models(monkeypatch, answers_by_role: dict[str, list]) -> list[dict]:
    """Replace the live models with scripted answers, one list per role, used in order.
    An answer of None stands for a reply that is not valid JSON. Return every call's details, in order."""
    calls = []

    def answer_from_the_script(role, model, system_prompt, steps, question, answer_format, temperature, seed, log,
                               reply_limit):
        """Log the call the way send_to_ollama() does, then give the role's next scripted answer."""
        calls.append({"role": role, "model": model, "system_prompt": system_prompt, "steps": steps,
                      "question": question, "answer_format": answer_format, "temperature": temperature,
                      "seed": seed, "reply_limit": reply_limit})
        log.append({"role": role, "model": model, "system_prompt": system_prompt, "reply": "made-up reply",
                    "thinking": "", "tokens_read": 100, "tokens_written": 20, "seconds": 1.0,
                    "temperature": temperature, "seed": seed, "context_window": 8192,
                    "prompt_may_be_cut": False, "reply_was_cut": False})
        answer = answers_by_role[role].pop(0)
        # Here a None answer behaves like a broken reply: send_to_ollama() raises this error for it.
        if answer is None:
            raise json.JSONDecodeError("not valid JSON", "made-up reply", 0)
        return answer

    # Here we swap the real model call for the script, only for this test; pytest puts the real one back afterwards.
    monkeypatch.setattr(The_Interrogation_Room.runV2, "send_to_ollama", answer_from_the_script)
    return calls


def calls_of(calls: list[dict], role: str) -> list[dict]:
    """Return the calls one role made, in order."""
    return [call for call in calls if call["role"] == role]


def step_numbers_seen_in(call: dict) -> list[int]:
    """Return the numbers of the steps one call was shown."""
    return [step.index for step in call["steps"]]


def log_text_of(log_folder: Path) -> str:
    """Return the text of the one log a test wrote."""
    return next(log_folder.glob("run_0_*.md")).read_text()


# ---------- Who speaks, with which settings ----------
def test_a_long_run_makes_16_calls_in_the_agreed_order_with_the_agreed_models(monkeypatch, tmp_path):
    """A 130-step run takes the summary and then 5 rounds of 3 calls; only the Interrogator uses the weaker model."""
    calls = fake_models(monkeypatch, a_script([40] * 5, [40] * 5))

    The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    assert [call["role"] for call in calls] == ["witness summary"] + ["witness testimony", "interrogator", "witness final"] * 5
    assert [call["model"] for call in calls] == [settings.DEBATER_MODEL] + \
        [settings.DEBATER_MODEL, settings.JUDGE_MODEL, settings.DEBATER_MODEL] * 5


def test_a_run_of_9_steps_takes_one_round(monkeypatch, tmp_path):
    """Halving 8 agent steps would leave 4, which is within the tolerance, so one round is enough."""
    calls = fake_models(monkeypatch, a_script([3], [3]))

    The_Interrogation_Room.run_interrogation_room(make_run(9), run_number=0, log_folder=tmp_path)

    assert [call["role"] for call in calls] == ["witness summary", "witness testimony", "interrogator", "witness final"]


def test_every_call_uses_the_agreed_temperature_seed_and_reply_limit(monkeypatch, tmp_path):
    """Every call uses temperature 0.7, seed 42 and the method's reply limit."""
    calls = fake_models(monkeypatch, a_script([3], [3]))

    The_Interrogation_Room.run_interrogation_room(make_run(9), run_number=0, log_folder=tmp_path)

    assert {call["temperature"] for call in calls} == {0.7}
    assert {call["seed"] for call in calls} == {42}
    assert {call["reply_limit"] for call in calls} == {The_Interrogation_Room.ReplyLimitInTokens}


def test_the_answer_is_the_witnesss_last_final_step(monkeypatch, tmp_path):
    """The answer is the final step of the last round, not a testimony step."""
    fake_models(monkeypatch, a_script([50, 50, 50, 50, 50], [40, 40, 40, 40, 38]))

    answer = The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    assert answer == 38


# ---------- Who sees which steps ----------
def test_the_summary_sees_only_the_task(monkeypatch, tmp_path):
    """The Witness's first call is shown Step 0 and nothing the team did."""
    calls = fake_models(monkeypatch, a_script([3], [3]))

    The_Interrogation_Room.run_interrogation_room(make_run(9), run_number=0, log_folder=tmp_path)

    assert step_numbers_seen_in(calls_of(calls, "witness summary")[0]) == [0]


def test_round_1_shows_the_task_and_every_agent_step(monkeypatch, tmp_path):
    """All three calls of round 1 see Step 0 and steps 1 to 129."""
    calls = fake_models(monkeypatch, a_script([40] * 5, [40] * 5))

    The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    for role in ["witness testimony", "interrogator", "witness final"]:
        assert step_numbers_seen_in(calls_of(calls, role)[0]) == list(range(130))


def test_each_round_keeps_the_half_centred_on_the_final_step(monkeypatch, tmp_path):
    """With every final step at 40, the steps in play shrink to 8-72, 24-56, 32-48 and 36-44."""
    calls = fake_models(monkeypatch, a_script([40] * 5, [40] * 5))

    The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    steps_seen_by_round = [step_numbers_seen_in(call)[1:] for call in calls_of(calls, "witness testimony")]
    assert steps_seen_by_round == [list(range(1, 130)), list(range(8, 73)), list(range(24, 57)),
                                   list(range(32, 49)), list(range(36, 45))]


def test_the_final_step_decides_the_half_not_the_testimony(monkeypatch, tmp_path):
    """The testimony names 100 but the final answer names 40, so round 2 sees steps 8 to 72."""
    calls = fake_models(monkeypatch, a_script([100, 40, 40, 40, 40], [40] * 5))

    The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    assert step_numbers_seen_in(calls_of(calls, "witness testimony")[1])[1:] == list(range(8, 73))


def test_the_half_stays_inside_the_steps_in_play(monkeypatch, tmp_path):
    """A final step near either end keeps a full half, pushed in from that end."""
    assert The_Interrogation_Room.half_centred_on(2, list(range(1, 130))) == list(range(1, 66))
    assert The_Interrogation_Room.half_centred_on(128, list(range(1, 130))) == list(range(65, 130))


def test_the_witness_may_name_only_steps_in_play(monkeypatch, tmp_path):
    """Both Witness formats list only the steps in play, without changing the shared format."""
    calls = fake_models(monkeypatch, a_script([40] * 5, [40] * 5))

    The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    for role in ["witness testimony", "witness final"]:
        assert calls_of(calls, role)[1]["answer_format"]["properties"]["step"]["enum"] == list(range(8, 73))
    assert "enum" not in The_Interrogation_Room.WitnessStepFormat["properties"]["step"]


# ---------- Who reads what was said ----------
def test_the_interrogator_reads_the_testimony_and_the_final_answer_reads_both(monkeypatch, tmp_path):
    """The Interrogator reads the summary and the testimony; the final answer also reads the feedback."""
    calls = fake_models(monkeypatch, a_script([3], [3]))

    The_Interrogation_Room.run_interrogation_room(make_run(9), run_number=0, log_folder=tmp_path)

    testimony_question = calls_of(calls, "witness testimony")[0]["question"]
    interrogator_question = calls_of(calls, "interrogator")[0]["question"]
    final_question = calls_of(calls, "witness final")[0]["question"]
    assert "summary-marker" in testimony_question
    assert "summary-marker" in interrogator_question and "testimony-marker" in interrogator_question
    assert "testimony-marker" in final_question and "interrogator-marker" in final_question


def test_the_definition_goes_to_every_round_prompt_but_not_the_summary():
    """The summary only lists what the task needs, while the three round prompts share one definition."""
    definition = The_Interrogation_Room.DecisiveStepDefinition
    assert definition not in The_Interrogation_Room.WitnessSummaryPrompt
    assert definition in The_Interrogation_Room.WitnessTestimonyPrompt
    assert definition in The_Interrogation_Room.InterrogatorPrompt
    assert definition in The_Interrogation_Room.WitnessFinalPrompt


# ---------- Failed replies ----------
def test_a_failed_interrogator_shows_as_no_answer_and_the_round_goes_on(monkeypatch, tmp_path):
    """The final answer reads "no answer" in place of the feedback, and its step still counts."""
    script = a_script([3], [4])
    script["interrogator"] = [None]
    calls = fake_models(monkeypatch, script)

    answer = The_Interrogation_Room.run_interrogation_room(make_run(9), run_number=0, log_folder=tmp_path)

    assert answer == 4
    assert "no answer" in calls_of(calls, "witness final")[0]["question"]


def test_a_failed_final_answer_falls_back_to_the_testimony(monkeypatch, tmp_path):
    """If the final answer is not valid JSON, the testimony's step decides the half."""
    script = a_script([40] * 5, [None, 40, 40, 40, 40])
    calls = fake_models(monkeypatch, script)

    The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    assert step_numbers_seen_in(calls_of(calls, "witness testimony")[1])[1:] == list(range(8, 73))


def test_a_step_outside_the_steps_in_play_counts_as_no_answer(monkeypatch, tmp_path):
    """A final step the Witness was not shown is not used, so the testimony's step is the answer."""
    fake_models(monkeypatch, a_script([3], [99]))

    answer = The_Interrogation_Room.run_interrogation_room(make_run(9), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert "- Round 1, Witness final: no answer (step 99 is not one of the steps allowed)" in log_text_of(tmp_path)


def test_a_round_with_no_usable_step_stops_the_search_at_the_last_step(monkeypatch, tmp_path):
    """If both Witness calls fail in round 2, the search stops and round 1's step is the answer."""
    script = a_script([40, None], [40, None])
    calls = fake_models(monkeypatch, script)

    answer = The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    assert answer == 40
    assert len(calls_of(calls, "witness testimony")) == 2
    assert "- Round 2: no usable step, so the search stops here" in log_text_of(tmp_path)


def test_no_usable_step_in_round_1_gives_no_answer(monkeypatch, tmp_path):
    """If both Witness calls fail in the first round, there is no step to fall back on."""
    script = a_script([None], [None])
    fake_models(monkeypatch, script)

    answer = The_Interrogation_Room.run_interrogation_room(make_run(9), run_number=0, log_folder=tmp_path)

    assert answer is None
    assert "- Answer: no answer" in log_text_of(tmp_path)


# ---------- The log ----------
def test_the_log_shows_every_round_and_the_steps_kept(monkeypatch, tmp_path):
    """The result lists the summary, each call's answer, the steps kept each round and the number of rounds."""
    fake_models(monkeypatch, a_script([50, 40, 40, 40, 40], [40] * 5))

    The_Interrogation_Room.run_interrogation_room(make_run(130), run_number=0, log_folder=tmp_path)

    log_text = log_text_of(tmp_path)
    assert log_text.startswith("# The Interrogation Room: run 0 (made_up.json)")
    assert "- Answer: step 40" in log_text
    assert "- Calls: 16" in log_text
    assert "- Summary: answered" in log_text
    assert "- Round 1, Witness testimony: step 50" in log_text
    assert "- Round 1, Interrogator: answered" in log_text
    assert "- Round 1, Witness final: step 40" in log_text
    assert "- Round 1: steps 1 to 129, kept 8 to 72" in log_text
    assert "- Round 5: steps 36 to 44, search finished" in log_text
    assert "- Rounds: 5" in log_text


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
