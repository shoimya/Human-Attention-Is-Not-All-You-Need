"""Tests for methods/The_Blame_Chain.py: who speaks when, who sees what, failed replies, the judge's retries, and the log.

Press play on this file to run all its tests. The models are replaced by scripted answers, so no server is needed
and nothing is written to runs/.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder and the methods folder to Python's search path,
# so this file can import The_Blame_Chain.py and data.py when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "methods"))

import pytest

import data
import The_Blame_Chain
import settings


def make_run() -> data.Trajectory:
    """Build a made-up run with ten steps (0 to 9) whose Decisive step is 3."""
    steps = [data.Step(index=number, agent="WebSurfer", text=f"Made-up step {number}.") for number in range(10)]
    return data.Trajectory(file_name="made_up.json", id="made-up", question="Made-up task?", steps=steps,
                           decisive_step=3, decisive_agent="WebSurfer", decisive_reason="made-up reason")


def reviewer_says() -> dict:
    """Build the reviewer's answer, with a marker to spot it in later questions."""
    return {"reasoning": "reviewer-marker", "how_it_ended": "It ended badly.", "what_looks_wrong": "The answer."}


def detective_names_window(start: int, end: int) -> dict:
    """Build the detective's round 1 answer, with a marker to spot it in later questions."""
    return {"reasoning": "detective-first-marker", "window_start": start, "window_end": end, "evidence": "See there."}


def intern_says(step: int, marker: str) -> dict:
    """Build an intern's answer naming the given step, with a marker to spot it in later questions."""
    return {"reasoning": marker, "step": step, "evidence": f"See step {step}."}


def detective_gives_verdict(step: int) -> dict:
    """Build the detective's round 2 answer naming the given step, with a marker to spot it in later questions."""
    return {"reasoning": "detective-verdict-marker", "answer_to_interns": "Noted.", "step": step, "reason": "Wrong."}


def judge_picks(step: int) -> dict:
    """Build the judge's answer picking the given step."""
    return {"reasoning": "made-up reasoning", "step": step, "reason": "It holds up."}


def a_full_script() -> dict[str, list]:
    """Build one working answer per call: the named steps are 2, 3, 4, 5 and 6, and the judge picks 3."""
    return {
        "reviewer": [reviewer_says()],
        "detective round 1": [detective_names_window(3, 7)],
        "intern 1": [intern_says(2, "intern-1-first-marker"), intern_says(3, "intern-1-final-marker")],
        "intern 2": [intern_says(4, "intern-2-first-marker"), intern_says(5, "intern-2-final-marker")],
        "detective round 2": [detective_gives_verdict(6)],
        "judge": [judge_picks(3)],
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
    monkeypatch.setattr(The_Blame_Chain.runV2, "send_to_ollama", answer_from_the_script)
    return calls


def question_of(calls: list[dict], role: str, turn: int = 0) -> str:
    """Return the question a role was asked on its first turn, or on a later one."""
    return [call["question"] for call in calls if call["role"] == role][turn]


# ---------- Who speaks, with which settings ----------
def test_a_run_makes_8_calls_in_the_agreed_order_with_the_agreed_models(monkeypatch, tmp_path):
    """The roles speak in the order of the table, and only Intern 2 and the Judge use the smaller model."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert [call["role"] for call in calls] == ["reviewer", "detective round 1", "intern 1", "intern 2",
                                                "detective round 2", "intern 1", "intern 2", "judge"]
    assert [call["model"] for call in calls] == [settings.DEBATER_MODEL] * 3 + [settings.JUDGE_MODEL] + \
        [settings.DEBATER_MODEL] * 2 + [settings.JUDGE_MODEL] * 2


def test_the_answer_is_the_judges_step(monkeypatch, tmp_path):
    """The judge picks step 3 although no vote favours it: there is no vote, so the answer is 3."""
    fake_models(monkeypatch, a_full_script())

    answer = The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 3


def test_every_call_uses_temperature_0_7_seed_42_and_the_2000_token_reply_limit(monkeypatch, tmp_path):
    """The first try of every role uses the same fixed settings."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert {call["temperature"] for call in calls} == {0.7}
    assert {call["seed"] for call in calls} == {42}
    assert {call["reply_limit"] for call in calls} == {2000}


def test_every_call_reads_the_full_run(monkeypatch, tmp_path):
    """Every role is sent all ten steps."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert all(len(call["steps"]) == 10 for call in calls)


def test_each_role_gets_its_own_system_prompt_and_the_detective_a_new_one_in_round_2(monkeypatch, tmp_path):
    """Each role uses its own prompt; the Detective's changes in round 2, and the interns' stays the same."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    expected_prompts = [
        The_Blame_Chain.ReviewerPrompt, The_Blame_Chain.DetectiveRoundOnePrompt,
        The_Blame_Chain.InternOnePrompt, The_Blame_Chain.InternTwoPrompt,
        The_Blame_Chain.DetectiveRoundTwoPrompt,
        The_Blame_Chain.InternOnePrompt, The_Blame_Chain.InternTwoPrompt,
        The_Blame_Chain.JudgePrompt,
    ]
    assert [call["system_prompt"] for call in calls] == expected_prompts


def test_only_the_detective_is_told_the_2_step_hint():
    """The scoring hint is in both Detective prompts and in no other role's prompt."""
    assert The_Blame_Chain.ScoringHint in The_Blame_Chain.DetectiveRoundOnePrompt
    assert The_Blame_Chain.ScoringHint in The_Blame_Chain.DetectiveRoundTwoPrompt
    other_prompts = [The_Blame_Chain.ReviewerPrompt, The_Blame_Chain.InternOnePrompt,
                     The_Blame_Chain.InternTwoPrompt, The_Blame_Chain.JudgePrompt]
    assert not any(The_Blame_Chain.ScoringHint in prompt for prompt in other_prompts)


def test_each_role_answers_in_its_own_format(monkeypatch, tmp_path):
    """Each role's format object goes with its call, so the model is forced into that shape."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    formats = [call["answer_format"]["required"] for call in calls]
    assert formats == [
        The_Blame_Chain.ReviewerFormat["required"], The_Blame_Chain.DetectiveRoundOneFormat["required"],
        The_Blame_Chain.InternFormat["required"], The_Blame_Chain.InternFormat["required"],
        The_Blame_Chain.DetectiveRoundTwoFormat["required"],
        The_Blame_Chain.InternFormat["required"], The_Blame_Chain.InternFormat["required"],
        The_Blame_Chain.JudgeFormat["required"],
    ]


# ---------- Who sees what ----------
def test_the_reviewer_sees_no_discussion(monkeypatch, tmp_path):
    """The reviewer speaks first, so its question holds nobody's answer."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert "marker" not in question_of(calls, "reviewer")


def test_the_detective_sees_only_the_reviewer_in_round_1(monkeypatch, tmp_path):
    """The detective's round 1 question holds the reviewer's answer and no other."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    question = question_of(calls, "detective round 1")
    assert "reviewer-marker" in question
    assert question.count("marker") == 1


def test_the_detective_is_told_which_steps_exist_when_it_names_its_window(monkeypatch, tmp_path):
    """A live run showed a window one step past the end of a short run, so the question now gives the run's range."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert "steps 0 to 9" in question_of(calls, "detective round 1")


def test_the_interns_see_the_reviewer_and_detective_but_not_each_other_in_round_1(monkeypatch, tmp_path):
    """Both interns get the same discussion in round 1, so the second cannot copy the first."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    intern_1_question = question_of(calls, "intern 1")
    intern_2_question = question_of(calls, "intern 2")
    assert intern_1_question == intern_2_question
    assert "reviewer-marker" in intern_1_question and "detective-first-marker" in intern_1_question
    assert "intern-1-first-marker" not in intern_2_question


def test_the_detective_sees_all_of_round_1_in_round_2(monkeypatch, tmp_path):
    """The detective's round 2 question holds all four answers from round 1."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    question = question_of(calls, "detective round 2")
    for marker in ["reviewer-marker", "detective-first-marker", "intern-1-first-marker", "intern-2-first-marker"]:
        assert marker in question


def test_the_interns_see_round_1_and_the_verdict_but_not_each_other_in_round_2(monkeypatch, tmp_path):
    """Both interns get the same discussion in round 2: all of round 1 and the verdict, not each other's final step."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    intern_1_question = question_of(calls, "intern 1", turn=1)
    intern_2_question = question_of(calls, "intern 2", turn=1)
    assert intern_1_question == intern_2_question
    for marker in ["reviewer-marker", "detective-first-marker", "intern-1-first-marker", "intern-2-first-marker",
                   "detective-verdict-marker"]:
        assert marker in intern_2_question
    assert "intern-1-final-marker" not in intern_2_question


def test_the_judge_sees_all_7_replies(monkeypatch, tmp_path):
    """The judge reads the whole discussion, not only the final verdicts."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    question = question_of(calls, "judge")
    for marker in ["reviewer-marker", "detective-first-marker", "intern-1-first-marker", "intern-2-first-marker",
                   "detective-verdict-marker", "intern-1-final-marker", "intern-2-final-marker"]:
        assert marker in question


def test_the_interns_are_told_first_answer_then_final_answer(monkeypatch, tmp_path):
    """The interns keep one system prompt, so the question says which answer this is."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert "first answer" in question_of(calls, "intern 1")
    assert "final answer" in question_of(calls, "intern 1", turn=1)


def test_the_models_are_never_told_which_intern_is_strong_or_weak(monkeypatch, tmp_path):
    """The transcript says only Intern 1 and Intern 2, so the labels cannot sway anyone."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    judge_question = question_of(calls, "judge")
    assert "Intern 1" in judge_question and "Intern 2" in judge_question
    for call in calls:
        assert "strong" not in call["question"].lower() and "weak" not in call["question"].lower()
        assert "strong" not in call["system_prompt"].lower() and "weak" not in call["system_prompt"].lower()


# ---------- The judge's choice ----------
def test_the_judge_is_given_the_named_steps_and_can_only_answer_one_of_them(monkeypatch, tmp_path):
    """The list of steps is in the judge's question and in its answer format. The window does not add to the list."""
    calls = fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    judge_call = calls[-1]
    assert "2, 3, 4, 5, 6" in judge_call["question"]
    assert judge_call["answer_format"]["properties"]["step"]["enum"] == [2, 3, 4, 5, 6]


def test_limiting_the_judges_steps_leaves_the_shared_format_untouched(monkeypatch, tmp_path):
    """Each run has its own list of named steps, so the list must not stay behind in JudgeFormat."""
    fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert "enum" not in The_Blame_Chain.JudgeFormat["properties"]["step"]


# ---------- Failed replies ----------
def test_a_broken_reply_becomes_no_answer_and_the_run_continues_without_a_retry(monkeypatch, tmp_path):
    """A broken Intern 1 reply is not asked again: the run still makes 8 calls, and later roles read "no answer"."""
    script = a_full_script()
    script["intern 1"][0] = None
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert len(calls) == 8
    assert "--- Round 1, Intern 1 ---\nno answer" in question_of(calls, "detective round 2")


def test_a_step_outside_the_run_becomes_no_answer_and_cannot_reach_the_judge(monkeypatch, tmp_path):
    """Intern 1 names step 99 in a ten-step run: later roles read "no answer", and 99 is not on the judge's list."""
    script = a_full_script()
    script["intern 1"][0] = intern_says(99, "intern-1-first-marker")
    calls = fake_models(monkeypatch, script)

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert "intern-1-first-marker" not in question_of(calls, "detective round 2")
    assert 99 not in calls[-1]["answer_format"]["properties"]["step"]["enum"]
    log_text = next(tmp_path.glob("run_0_*.md")).read_text()
    assert "Round 1, Intern 1: no answer (step 99 is not in the run)" in log_text


def test_a_window_outside_the_run_or_backwards_becomes_no_answer(monkeypatch, tmp_path):
    """A window that ends past the run, or that ends before it starts, is not passed on to the next roles."""
    for start, end in [(7, 99), (6, 2)]:
        script = a_full_script()
        script["detective round 1"][0] = detective_names_window(start, end)
        calls = fake_models(monkeypatch, script)

        The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

        assert "detective-first-marker" not in question_of(calls, "intern 1")


# ---------- The judge's retries ----------
def test_a_broken_judge_reply_is_asked_again_with_a_new_seed_and_the_reason(monkeypatch, tmp_path):
    """The judge's first reply is broken: the retry uses seed 43, says what went wrong, and its step is the answer."""
    script = a_full_script()
    script["judge"] = [None, judge_picks(4)]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 4
    assert len(calls) == 9
    assert [call["seed"] for call in calls if call["role"] == "judge"] == [42, 43]
    assert "not valid JSON" in question_of(calls, "judge", turn=1)


def test_a_judge_step_nobody_named_is_asked_again_and_told_the_list(monkeypatch, tmp_path):
    """The judge picks step 8, which nobody named: the retry says so, and repeats the steps it may pick."""
    script = a_full_script()
    script["judge"] = [judge_picks(8), judge_picks(5)]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 5
    retry_question = question_of(calls, "judge", turn=1)
    assert "step 8" in retry_question and "2, 3, 4, 5, 6" in retry_question


def test_a_retry_says_only_what_went_wrong_last_time(monkeypatch, tmp_path):
    """The reason is replaced on each retry, so failed tries do not pile up in the question."""
    script = a_full_script()
    script["judge"] = [None, judge_picks(8), judge_picks(5)]
    calls = fake_models(monkeypatch, script)

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    last_question = question_of(calls, "judge", turn=2)
    assert "step 8" in last_question and "not valid JSON" not in last_question


def test_a_judge_that_always_fails_gets_3_retries_and_the_run_has_no_answer(monkeypatch, tmp_path):
    """One first try and 3 retries (seeds 42 to 45, 11 calls in all), then no answer, and the log says why."""
    script = a_full_script()
    script["judge"] = [None, None, None, None]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert answer is None
    assert len(calls) == 11
    assert [call["seed"] for call in calls if call["role"] == "judge"] == [42, 43, 44, 45]
    log_text = next(tmp_path.glob("run_0_*.md")).read_text()
    assert "- Answer: no answer" in log_text
    assert "- Calls: 11" in log_text
    assert "- Judge: no answer after 4 tries" in log_text and "not valid JSON" in log_text


def test_only_the_judge_retries_change_the_seed(monkeypatch, tmp_path):
    """The 7 calls before the judge stay on seed 42 even when the judge needs retries."""
    script = a_full_script()
    script["judge"] = [None, judge_picks(4)]
    calls = fake_models(monkeypatch, script)

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert {call["seed"] for call in calls if call["role"] != "judge"} == {42}


def test_when_nobody_names_a_step_the_judge_is_not_asked(monkeypatch, tmp_path):
    """With nothing on the list the judge cannot pick, so the run has no answer after 7 calls, and the log says why."""
    script = a_full_script()
    script["intern 1"] = [None, None]
    script["intern 2"] = [None, None]
    script["detective round 2"] = [None]
    calls = fake_models(monkeypatch, script)

    answer = The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    assert answer is None
    assert len(calls) == 7
    log_text = next(tmp_path.glob("run_0_*.md")).read_text()
    assert "- Judge: not asked, because nobody named a step" in log_text


# ---------- The log ----------
def test_the_log_lists_every_turn_and_the_judges_choice(monkeypatch, tmp_path):
    """The current log format holds the 8 calls, and the result has one line per role's turn."""
    fake_models(monkeypatch, a_full_script())

    The_Blame_Chain.run_blame_chain(make_run(), run_number=0, log_folder=tmp_path)

    log_text = next(tmp_path.glob("run_0_*.md")).read_text()
    assert log_text.startswith("# The Blame Chain: run 0 (made_up.json)")
    assert "- Answer: step 3" in log_text
    assert "- Calls: 8" in log_text
    assert "- Round 1, Reviewer: answered" in log_text
    assert "- Round 1, Detective: window 3 to 7" in log_text
    assert "- Round 1, Intern 1: step 2" in log_text
    assert "- Round 2, Detective: step 6" in log_text
    assert "- Named steps: 2, 3, 4, 5, 6" in log_text
    assert "- Judge: step 3 (try 1 of 4)" in log_text


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
