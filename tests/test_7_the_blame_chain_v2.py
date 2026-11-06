"""Tests for methods/The_Blame_ChainV2.py: who speaks when, who sees which steps, the halving, failed replies and the log.

Press play on this file to run all its tests. The models are replaced by scripted answers, so no server is needed
and nothing is written to runs/.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder and the methods folder to Python's search path,
# so this file can import The_Blame_ChainV2.py and data.py when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "methods"))

import pytest

import data
import settings
import The_Blame_ChainV2


def make_run(number_of_steps: int = 130) -> data.Trajectory:
    """Build a made-up run with the given number of steps, whose Decisive step is 3."""
    steps = [data.Step(index=number, agent="WebSurfer", text=f"Made-up step {number}.") for number in range(number_of_steps)]
    return data.Trajectory(file_name="made_up.json", id="made-up", question="Made-up task?", steps=steps,
                           decisive_step=3, decisive_agent="WebSurfer", decisive_reason="made-up reason")


def reviewer_says() -> dict:
    """Build the reviewer's answer, with a marker to spot it in later questions."""
    return {"reasoning": "reviewer-marker", "checklist": "1. Find the fact."}


def detective_halves(already_happened: bool) -> dict:
    """Build one of the Detective's halving answers."""
    return {"reasoning": "made-up reasoning", "already_happened": already_happened, "evidence": "See there."}


def names_step(step: int, marker: str) -> dict:
    """Build the close-up Detective's or Intern 1's answer naming the given step, with a marker to spot it later."""
    return {"reasoning": marker, "step": step, "evidence": f"See step {step}."}


def judge_picks(step: int) -> dict:
    """Build the judge's answer picking the given step."""
    return {"reasoning": "made-up reasoning", "step": step, "reason": "It holds up."}


def a_script(halving_answers: list[bool], detective_step: int = 5, intern_step: int = 3, judge_step: int = 3) -> dict:
    """Build one working answer per call, with the given yes or no answers for the halving calls."""
    return {
        "reviewer": [reviewer_says()],
        "detective halving": [detective_halves(answer) for answer in halving_answers],
        "detective close-up": [names_step(detective_step, "detective-marker")],
        "intern 1": [names_step(intern_step, "intern-marker")],
        "judge": [judge_picks(judge_step)],
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
    monkeypatch.setattr(The_Blame_ChainV2.runV2, "send_to_ollama", answer_from_the_script)
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
def test_a_long_run_makes_8_calls_in_the_agreed_order_with_the_agreed_models(monkeypatch, tmp_path):
    """The longest runs use all 8 calls, and only the Judge uses the smaller model."""
    calls = fake_models(monkeypatch, a_script([False, False, False, False], detective_step=125, intern_step=125, judge_step=125))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    assert [call["role"] for call in calls] == ["reviewer"] + ["detective halving"] * 4 + \
        ["detective close-up", "intern 1", "judge"]
    assert [call["model"] for call in calls] == [settings.DEBATER_MODEL] * 7 + [settings.JUDGE_MODEL]


def test_a_run_of_9_steps_or_fewer_skips_the_halving(monkeypatch, tmp_path):
    """A run that already fits in the close-up makes 4 calls."""
    calls = fake_models(monkeypatch, a_script([]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    assert [call["role"] for call in calls] == ["reviewer", "detective close-up", "intern 1", "judge"]


def test_every_call_uses_the_agreed_temperature_seed_and_reply_limit(monkeypatch, tmp_path):
    """Every first try uses temperature 0.7, seed 42 and the method's reply limit."""
    calls = fake_models(monkeypatch, a_script([True, True, True, True]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    assert {call["temperature"] for call in calls} == {0.7}
    assert {call["seed"] for call in calls} == {42}
    assert {call["reply_limit"] for call in calls} == {The_Blame_ChainV2.ReplyLimitInTokens}


def test_the_answer_is_the_judges_step(monkeypatch, tmp_path):
    """The method returns the step the Judge picked, not the Detective's."""
    fake_models(monkeypatch, a_script([True, True, True, True], detective_step=5, intern_step=3, judge_step=3))

    answer = The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    assert answer == 3


# ---------- Who sees which steps ----------
def test_the_reviewer_sees_only_the_task(monkeypatch, tmp_path):
    """The Reviewer is shown Step 0 and nothing the team did."""
    calls = fake_models(monkeypatch, a_script([]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    assert step_numbers_seen_in(calls_of(calls, "reviewer")[0]) == [0]


def test_yes_keeps_the_earlier_half_and_hides_everything_after_the_cut_off(monkeypatch, tmp_path):
    """After four yes answers the cut-offs are 64, 32, 16 and 8, and no call sees past its cut-off."""
    calls = fake_models(monkeypatch, a_script([True, True, True, True]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    halving_calls = calls_of(calls, "detective halving")
    assert [step_numbers_seen_in(call) for call in halving_calls] == [list(range(cut_off + 1)) for cut_off in [64, 32, 16, 8]]


def test_no_keeps_the_later_half(monkeypatch, tmp_path):
    """After four no answers the cut-offs are 64, 97, 113 and 121."""
    calls = fake_models(monkeypatch, a_script([False, False, False, False]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    halving_calls = calls_of(calls, "detective halving")
    assert [step_numbers_seen_in(call)[-1] for call in halving_calls] == [64, 97, 113, 121]


def test_halving_stops_as_soon_as_9_steps_or_fewer_are_left(monkeypatch, tmp_path):
    """A run of 20 steps needs only two halving calls: 20 steps, then 10, then 5."""
    calls = fake_models(monkeypatch, a_script([True, True]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(20), run_number=0, log_folder=tmp_path)

    assert len(calls_of(calls, "detective halving")) == 2


def test_the_first_halving_question_says_nothing_about_earlier_checks(monkeypatch, tmp_path):
    """Before any answer there is nothing to report, so the first question only gives the cut-off."""
    calls = fake_models(monkeypatch, a_script([False, False, False, False]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    first_question = calls_of(calls, "detective halving")[0]["question"]
    assert "reviewer-marker" in first_question
    assert "by step 64" in first_question
    assert "Earlier checks" not in first_question


def test_after_a_no_the_next_question_says_where_to_look(monkeypatch, tmp_path):
    """After a no at step 64, the next call is told the decisive step comes after step 64."""
    calls = fake_models(monkeypatch, a_script([False, False, False, False]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    second_question = calls_of(calls, "detective halving")[1]["question"]
    assert "Earlier checks found the decisive step comes after step 64" in second_question
    assert "steps 65 to 97" in second_question


def test_the_close_up_shows_the_task_and_the_steps_left_with_2_extra_on_each_side(monkeypatch, tmp_path):
    """After four no answers, steps 122 to 129 are left, so the close-up shows Step 0 and steps 120 to 129."""
    calls = fake_models(monkeypatch, a_script([False, False, False, False], detective_step=125, intern_step=125, judge_step=125))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    expected_steps = [0] + list(range(120, 130))
    for role in ["detective close-up", "intern 1", "judge"]:
        assert step_numbers_seen_in(calls_of(calls, role)[0]) == expected_steps


def test_the_close_up_shows_step_0_once_when_the_steps_left_start_at_the_task(monkeypatch, tmp_path):
    """After four yes answers, steps 0 to 8 are left, so the close-up shows steps 0 to 10 with no repeat."""
    calls = fake_models(monkeypatch, a_script([True, True, True, True]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    assert step_numbers_seen_in(calls_of(calls, "detective close-up")[0]) == list(range(11))


def test_the_detective_and_intern_may_name_only_agent_steps_shown(monkeypatch, tmp_path):
    """The answer format limits both roles to the steps shown, leaving out Step 0, without changing the shared format."""
    calls = fake_models(monkeypatch, a_script([True, True, True, True]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    for role in ["detective close-up", "intern 1"]:
        assert calls_of(calls, role)[0]["answer_format"]["properties"]["step"]["enum"] == list(range(1, 11))
    assert "enum" not in The_Blame_ChainV2.StepAndEvidenceFormat["properties"]["step"]


# ---------- Who reads what was said ----------
def test_the_detective_reads_the_checklist_and_the_intern_also_reads_the_detective(monkeypatch, tmp_path):
    """The close-up Detective reads the Reviewer, and Intern 1 reads the Reviewer and the Detective."""
    calls = fake_models(monkeypatch, a_script([]))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    detective_question = calls_of(calls, "detective close-up")[0]["question"]
    intern_question = calls_of(calls, "intern 1")[0]["question"]
    assert "reviewer-marker" in detective_question
    assert "reviewer-marker" in intern_question
    assert "detective-marker" in intern_question


def test_the_judge_reads_both_answers_and_may_pick_only_a_named_step(monkeypatch, tmp_path):
    """The Judge reads the Detective and Intern 1, and its format allows only the steps they named."""
    calls = fake_models(monkeypatch, a_script([], detective_step=5, intern_step=3, judge_step=3))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    judge_call = calls_of(calls, "judge")[0]
    assert "detective-marker" in judge_call["question"]
    assert "intern-marker" in judge_call["question"]
    assert "reviewer-marker" not in judge_call["question"]
    assert judge_call["answer_format"]["properties"]["step"]["enum"] == [3, 5]


def test_the_definition_goes_to_every_role_except_the_reviewer():
    """The Reviewer only writes a checklist, while the roles that judge steps share one definition."""
    definition = The_Blame_ChainV2.DecisiveStepDefinition
    assert definition not in The_Blame_ChainV2.ReviewerPrompt
    assert definition in The_Blame_ChainV2.DetectiveHalvingPrompt
    assert definition in The_Blame_ChainV2.DetectiveCloseUpPrompt
    assert definition in The_Blame_ChainV2.InternOnePrompt
    assert definition in The_Blame_ChainV2.JudgePrompt


# ---------- Failed replies ----------
def test_a_failed_reviewer_shows_as_no_answer_and_the_run_continues(monkeypatch, tmp_path):
    """Later roles read "no answer" in place of the checklist, and the run still gets an answer."""
    script = a_script([])
    script["reviewer"] = [None]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert "no answer" in calls_of(calls, "detective close-up")[0]["question"]


def test_a_failed_halving_call_stops_the_halving_at_the_steps_left(monkeypatch, tmp_path):
    """A failed second call leaves steps 0 to 64, so the close-up uses that wider range with no more halving."""
    script = a_script([True])
    script["detective halving"].append(None)
    calls = fake_models(monkeypatch, script)

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    assert len(calls_of(calls, "detective halving")) == 2
    assert step_numbers_seen_in(calls_of(calls, "detective close-up")[0]) == list(range(67))
    assert "- Halving 2 (by step 32): no answer (the reply was not valid JSON)" in log_text_of(tmp_path)


def test_a_failed_detective_shows_as_no_answer_and_the_judge_gets_the_interns_step(monkeypatch, tmp_path):
    """With no Detective answer, Intern 1 reads "no answer" and the Judge can pick only the intern's step."""
    script = a_script([], intern_step=3, judge_step=3)
    script["detective close-up"] = [None]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert "no answer" in calls_of(calls, "intern 1")[0]["question"]
    assert calls_of(calls, "judge")[0]["answer_format"]["properties"]["step"]["enum"] == [3]


def test_a_step_outside_the_steps_shown_counts_as_no_answer(monkeypatch, tmp_path):
    """A step the role was not shown is never passed on, and it is not offered to the Judge."""
    script = a_script([], detective_step=99, intern_step=3, judge_step=3)
    calls = fake_models(monkeypatch, script)

    The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    assert calls_of(calls, "judge")[0]["answer_format"]["properties"]["step"]["enum"] == [3]
    assert "- Close-up, Detective: no answer (step 99 is not one of the steps allowed)" in log_text_of(tmp_path)


def test_the_judge_is_not_asked_when_nobody_named_a_step(monkeypatch, tmp_path):
    """With no named step there is nothing to pick, so there is no answer and no Judge call."""
    script = a_script([])
    script["detective close-up"] = [None]
    script["intern 1"] = [None]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    assert answer is None
    assert calls_of(calls, "judge") == []
    assert "- Judge: not asked, because nobody named a step" in log_text_of(tmp_path)


def test_the_judge_retries_with_a_new_seed_and_the_reason(monkeypatch, tmp_path):
    """A failed Judge reply is asked again with the next seed, and the question says what went wrong."""
    script = a_script([], judge_step=3)
    script["judge"] = [None, judge_picks(3)]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    judge_calls = calls_of(calls, "judge")
    assert answer == 3
    assert [call["seed"] for call in judge_calls] == [42, 43]
    assert "Your last reply was rejected because your reply was not valid JSON" in judge_calls[1]["question"]
    assert "- Judge: step 3 (try 2 of 4)" in log_text_of(tmp_path)


def test_the_judge_gives_up_after_4_tries(monkeypatch, tmp_path):
    """After the first try and 3 retries fail, the run has no answer and the log says why."""
    script = a_script([])
    script["judge"] = [None, None, None, None]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    assert answer is None
    assert [call["seed"] for call in calls_of(calls, "judge")] == [42, 43, 44, 45]
    assert "- Judge: no answer after 4 tries" in log_text_of(tmp_path)


# ---------- The log ----------
def test_the_log_shows_each_halving_answer_and_the_steps_left(monkeypatch, tmp_path):
    """The result lists the calls made, each yes or no answer and the steps in the close-up."""
    fake_models(monkeypatch, a_script([True, False, True, True], detective_step=35, intern_step=35, judge_step=35))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(130), run_number=0, log_folder=tmp_path)

    log_text = log_text_of(tmp_path)
    assert log_text.startswith("# The Blame Chain V2: run 0 (made_up.json)")
    assert "- Calls: 8" in log_text
    assert "- Reviewer: answered" in log_text
    assert "- Halving 1 (by step 64): yes, steps left 0 to 64" in log_text
    assert "- Halving 2 (by step 32): no, steps left 33 to 64" in log_text
    assert "- Halving 3 (by step 48): yes, steps left 33 to 48" in log_text
    assert "- Halving 4 (by step 40): yes, steps left 33 to 40" in log_text
    assert "- Close-up steps: 31 to 42" in log_text


def test_the_log_shows_the_named_steps_and_the_judges_choice(monkeypatch, tmp_path):
    """The result ends with what each close-up role named and what the Judge picked."""
    fake_models(monkeypatch, a_script([], detective_step=5, intern_step=3, judge_step=3))

    The_Blame_ChainV2.run_blame_chain_v2(make_run(9), run_number=0, log_folder=tmp_path)

    log_text = log_text_of(tmp_path)
    assert "- Answer: step 3" in log_text
    assert "- Close-up steps: 1 to 8" in log_text
    assert "- Close-up, Detective: step 5" in log_text
    assert "- Close-up, Intern 1: step 3" in log_text
    assert "- Named steps: 3, 5" in log_text
    assert "- Judge: step 3 (try 1 of 4)" in log_text


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
