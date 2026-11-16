"""Tests for methods/prover_estimator_debate.py: the protocol's order, the prover's decompositions and the depth limit,
who picks the next part, the retries, the judge's view, the paper's rewards and the log.

Press play on this file to run all its tests. The models are replaced by scripted answers, so no server is needed
and nothing is written to runs/.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder and the methods folder to Python's search path,
# so this file can import prover_estimator_debate.py and data.py when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "methods"))

import pytest

import data
import settings
import prover_estimator_debate as debate


def make_run(number_of_steps: int = 10, decisive_step: int = 3) -> data.Trajectory:
    """Build a made-up run with the given number of steps (Step 0 is the task)."""
    steps = [data.Step(index=number, agent="WebSurfer", text=f"Made-up step {number}.") for number in range(number_of_steps)]
    return data.Trajectory(file_name="made_up.json", id="made-up", question="Made-up task?", steps=steps,
                           decisive_step=decisive_step, decisive_agent="WebSurfer", decisive_reason="made-up reason")


def prover_says(direction: str, cuts: list[int] | None = None, next_part: int | None = None,
                argument: str = "See step 3.") -> dict:
    """Build one prover answer; fields left as None are left out, as the format would leave them out."""
    answer = {"reasoning": "made-up reasoning", "direction": direction}
    if next_part is not None:
        answer["next_part"] = next_part
    if cuts is not None:
        answer["cuts"] = cuts
        answer["argument"] = argument
    return answer


def estimator_says(**probabilities: float) -> dict:
    """Build one estimator answer; combinations not given get 0."""
    return {"reasoning": "made-up reasoning", **probabilities}


def two_parts(none: float, parts_1: float, parts_2: float, parts_1_2: float) -> dict:
    """Build an estimator answer for a decomposition into two parts."""
    return estimator_says(none=none, parts_1=parts_1, parts_2=parts_2, parts_1_2=parts_1_2)


def opening_answers() -> dict:
    return {"prover opening": [{"reasoning": "r", "claim": "TRUE"}],
            "estimator opening": [{"reasoning": "r", "probability": 0.9}]}


def a_prover_script() -> dict:
    """A 10-step run (claim: steps 1 to 9) where the prover's picks lead to step 3 in three rounds."""
    return {
        **opening_answers(),
        "prover": [
            prover_says("ABOUT_RIGHT", cuts=[4]),                   # steps 1-9 -> 1-4 | 5-9
            prover_says("TOO_LOW", cuts=[2], next_part=1),          # picks 1-4 -> 1-2 | 3-4
            prover_says("TOO_LOW", cuts=[3], next_part=2),          # picks 3-4 -> 3 | 4
            prover_says("ABOUT_RIGHT", cuts=[], next_part=1),       # picks step 3, the leaf
        ],
        "estimator": [
            two_parts(0.1, 0.7, 0.1, 0.1),
            two_parts(0.1, 0.1, 0.7, 0.1),
            two_parts(0.0, 1.0, 0.0, 0.0),
        ],
        "judge": [{"reasoning": "r", "verdict": "DECISIVE"}],
    }


def fake_models(monkeypatch, answers_by_role: dict[str, list]) -> list[dict]:
    """Replace the live models with scripted answers, one list per role, used in order.
    An answer of None stands for a reply that is not valid JSON. Return every call's details, in order."""
    calls = []

    def answer_from_the_script(role, model, system_prompt, steps, question, answer_format, temperature, seed, log,
                               reply_limit):
        """Log the call the way send_to_ollama() does, then give the role's next scripted answer."""
        calls.append({"role": role, "model": model, "system_prompt": system_prompt, "steps": steps,
                      "question": question, "answer_format": answer_format, "temperature": temperature, "seed": seed})
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
    monkeypatch.setattr(debate.runV2, "send_to_ollama", answer_from_the_script)
    return calls


def log_text_of(log_folder: Path) -> str:
    """Return the text of the one log a test wrote."""
    return next(log_folder.glob("run_0_*.md")).read_text()


# ---------- The protocol ----------
def test_the_prover_picks_the_parts_and_the_last_step_left_is_the_answer(monkeypatch, tmp_path):
    """Opening, three rounds, the last prover turn and the judge: 10 calls, in the paper's order."""
    calls = fake_models(monkeypatch, a_prover_script())

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert [call["role"] for call in calls] == ["prover opening", "estimator opening"] + \
        ["prover", "estimator"] * 3 + ["prover", "judge"]
    assert [call["model"] for call in calls] == [settings.DEBATER_MODEL] * 9 + [settings.JUDGE_MODEL]


def test_every_call_gets_its_own_seed_and_the_fixed_temperature(monkeypatch, tmp_path):
    """Call c uses seed Seed + c, so calls differ but repeat exactly when run again."""
    calls = fake_models(monkeypatch, a_prover_script())

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert [call["seed"] for call in calls] == [debate.Seed + number for number in range(10)]
    assert {call["temperature"] for call in calls} == {debate.Temperature}


def test_every_role_argues_about_the_counterfactual_decisive_step(monkeypatch, tmp_path):
    """The claim is Who&When's: a step that, done right, would have made the run succeed; recovered mistakes do not count."""
    calls = fake_models(monkeypatch, a_prover_script())

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    for call in calls:
        assert "doing that step right would have made the run succeed" in call["system_prompt"]
        assert "recovered from is not decisive" in call["system_prompt"]
    assert "contain a decisive step" in calls[0]["question"]


def test_the_prover_is_asked_to_pick_only_when_there_are_several_parts(monkeypatch, tmp_path):
    """The first prover turn has one claim and no next_part; later turns pick a part number."""
    calls = fake_models(monkeypatch, a_prover_script())

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    prover_formats = [call["answer_format"]["properties"] for call in calls if call["role"] == "prover"]
    assert "next_part" not in prover_formats[0]
    assert all(properties["next_part"]["enum"] == [1, 2] for properties in prover_formats[1:])
    # Here the last turn picks between two single steps, so there is nothing to cut.
    assert "cuts" not in prover_formats[-1]


def test_a_run_with_one_step_after_the_task_goes_straight_to_the_leaf(monkeypatch, tmp_path):
    """With nothing to cut, the opening is followed by one prover turn and the judge."""
    calls = fake_models(monkeypatch, {
        **opening_answers(),
        "prover": [prover_says("ABOUT_RIGHT")],
        "judge": [{"reasoning": "r", "verdict": "DECISIVE"}],
    })

    answer = debate.run_prover_estimator_debate(make_run(2, decisive_step=1), run_number=0, log_folder=tmp_path)

    assert answer == 1
    assert [call["role"] for call in calls] == ["prover opening", "estimator opening", "prover", "judge"]


# ---------- The prover's decompositions ----------
def test_the_prover_chooses_where_to_cut_even_unevenly(monkeypatch, tmp_path):
    """With rounds to spare, a cut that leaves one step on one side is the prover's choice and is accepted."""
    script = a_prover_script()
    script["prover"] = [
        prover_says("ABOUT_RIGHT", cuts=[2]),                       # steps 1-9 -> 1-2 | 3-9
        prover_says("TOO_LOW", cuts=[3], next_part=2),              # picks 3-9 -> 3 | 4-9
        prover_says("ABOUT_RIGHT", cuts=[], next_part=1),           # picks step 3, the leaf
    ]
    script["estimator"] = [two_parts(0.1, 0.1, 0.7, 0.1), two_parts(0.1, 0.7, 0.1, 0.1)]
    calls = fake_models(monkeypatch, script)

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert len(calls) == 8
    assert "parts 1-2 | 3-9" in log_text_of(tmp_path)


@pytest.mark.parametrize("cuts, problem", [
    ([8], None),                                        # 1-8 | 9-16: both parts fit in 8 steps
    ([3], "has 13 steps, more than the 8 allowed"),     # 4-16 is too big to reach one step in the rounds left
    ([], "is not a list of 1 step number"),
    ([16], "must be increasing step numbers from 1 to 15"),
])
def test_no_part_may_be_bigger_than_the_rounds_left_can_bring_down_to_one_step(cuts, problem):
    """16 steps with 4 rounds left (2^4 = 16): each of the 2 parts may have at most 2^3 = 8 steps."""
    found = debate.problem_with_cuts(cuts, {"first": 1, "last": 16}, rounds_left=4)
    if problem is None:
        assert found is None
    else:
        assert problem in found


def test_the_prover_is_told_the_exact_range_of_its_cut():
    """The pilot (run 36) failed here: steps 8 to 50 with 6 rounds left allow parts of at most 32 steps,
    so the cut must be from 18 to 39, and the question now says so."""
    claim = {"first": 8, "last": 50, "estimate": 0.0}
    assert debate.cut_ranges(claim, rounds_left=6) == [(18, 39)]
    assert "the cut must be from 18 to 39" in debate.prover_question([claim], rounds_left=6)
    assert "so the cut must be from 18 to 39" in debate.problem_with_cuts([42], claim, rounds_left=6)


@pytest.mark.parametrize("parts_per_split, claim, rounds_left, cuts, expected", [
    (2, {"first": 8, "last": 50}, 6, [42], [39]),       # the pilot's cut, moved to the nearest allowed value
    (2, {"first": 8, "last": 50}, 6, [25], [25]),       # an allowed cut stays where it is
    (2, {"first": 1, "last": 9}, 4, [9], [8]),          # a cut past the claim's last step allowed
    (3, {"first": 1, "last": 9}, 2, [5, 7], [3, 6]),    # q = 3, parts of at most 3 steps: only 3 | 6 works
])
def test_cuts_that_break_the_limit_move_to_the_nearest_allowed_values(monkeypatch, parts_per_split, claim,
                                                                     rounds_left, cuts, expected):
    monkeypatch.setattr(debate, "PartsPerSplit", parts_per_split)
    moved = debate.nearest_allowed_cuts(claim, cuts, rounds_left)
    assert moved == expected
    assert debate.problem_with_cuts(moved, claim, rounds_left) is None


def test_a_prover_that_breaks_the_limit_twice_has_its_cut_moved_and_the_run_goes_on(monkeypatch, tmp_path):
    """Steps 1 to 16 with 4 rounds left allow only the cut 8. Two cuts at 3 are moved to 8, and the log says so."""
    monkeypatch.setattr(debate, "ExtraRounds", 0)
    calls = fake_models(monkeypatch, {
        **opening_answers(),
        "prover": [
            prover_says("ABOUT_RIGHT", cuts=[3]),                   # not allowed
            prover_says("ABOUT_RIGHT", cuts=[3]),                   # not allowed again: moved to 8 -> 1-8 | 9-16
            prover_says("TOO_LOW", cuts=[4], next_part=1),          # picks 1-8 -> 1-4 | 5-8
            prover_says("TOO_LOW", cuts=[2], next_part=1),          # picks 1-4 -> 1-2 | 3-4
            prover_says("TOO_LOW", cuts=[3], next_part=2),          # picks 3-4 -> 3 | 4
            prover_says("ABOUT_RIGHT", cuts=[], next_part=1),       # picks step 3
        ],
        "estimator": [two_parts(0, 1, 0, 0), two_parts(0, 1, 0, 0), two_parts(0, 0, 1, 0), two_parts(0, 1, 0, 0)],
        "judge": [{"reasoning": "r", "verdict": "DECISIVE"}],
    })

    answer = debate.run_prover_estimator_debate(make_run(17), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert len(calls) == 13
    assert "so the cut must be from 8 to 8" in calls[3]["question"]
    assert "parts 1-8 | 9-16; CUTS MOVED from [3] to [8]" in log_text_of(tmp_path)


def test_a_reply_that_is_not_json_twice_still_fails_the_run(monkeypatch, tmp_path):
    """Only cuts are moved: two broken replies still end the run (rule 11)."""
    script = a_prover_script()
    script["prover"] = [None, None]
    fake_models(monkeypatch, script)

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer is None
    assert "RUN FAILED: the prover gave an unusable reply twice; the second time it was not valid JSON" in log_text_of(tmp_path)


def test_the_depth_is_the_fewest_rounds_plus_the_extra_rounds(monkeypatch):
    monkeypatch.setattr(debate, "ExtraRounds", 1)
    assert debate.rounds_needed(1) == 0
    assert debate.rounds_needed(9) == 4      # 2^3 = 8 < 9 <= 16 = 2^4
    assert debate.rounds_needed(129) == 8    # run of 130 steps, Step 0 is the task


def test_three_parts_per_split_give_eight_combinations(monkeypatch, tmp_path):
    """With q = 3 the prover gives 2 cuts and the estimator a probability for each of the 2^3 combinations."""
    monkeypatch.setattr(debate, "PartsPerSplit", 3)
    calls = fake_models(monkeypatch, {
        **opening_answers(),
        "prover": [
            prover_says("ABOUT_RIGHT", cuts=[3, 6]),                # steps 1-9 -> 1-3 | 4-6 | 7-9
            prover_says("TOO_LOW", cuts=[4, 5], next_part=2),       # picks 4-6 -> 4 | 5 | 6
            prover_says("ABOUT_RIGHT", cuts=[], next_part=1),       # picks step 4
        ],
        "estimator": [estimator_says(none=0, parts_1=0, parts_2=1, parts_3=0, parts_1_2=0, parts_1_3=0, parts_2_3=0,
                                     parts_1_2_3=0),
                      estimator_says(none=0, parts_1=1, parts_2=0, parts_3=0, parts_1_2=0, parts_1_3=0, parts_2_3=0,
                                     parts_1_2_3=0)],
        "judge": [{"reasoning": "r", "verdict": "DECISIVE"}],
    })

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 4
    first_estimator_call = next(call for call in calls if call["role"] == "estimator")
    assert len(first_estimator_call["answer_format"]["properties"]) == 1 + 8
    first_prover_call = next(call for call in calls if call["role"] == "prover")
    assert first_prover_call["answer_format"]["properties"]["cuts"]["minItems"] == 2


def test_the_combinations_are_named_from_none_to_all_parts():
    assert debate.joint_cases(2) == [("none", (0, 0)), ("parts_1", (1, 0)), ("parts_2", (0, 1)), ("parts_1_2", (1, 1))]


# ---------- Who picks the next part ----------
def test_the_first_error_rule_overrides_the_prover(monkeypatch, tmp_path):
    """With the switch on, the earliest part the estimator gives more than 0.5 is kept, and the prover never picks."""
    monkeypatch.setattr(debate, "NextPartChosenBy", "first_error")
    calls = fake_models(monkeypatch, {
        **opening_answers(),
        "prover": [
            prover_says("ABOUT_RIGHT", cuts=[4]),       # steps 1-9 -> 1-4 | 5-9
            prover_says("TOO_LOW", cuts=[6]),           # the rule kept 5-9 -> 5-6 | 7-9
            prover_says("TOO_LOW", cuts=[5]),           # the rule kept 5-6 -> 5 | 6
            prover_says("ABOUT_RIGHT"),                 # the rule kept step 5
        ],
        "estimator": [
            two_parts(0.1, 0.1, 0.7, 0.1),              # part 1 at 0.2: go to part 2
            two_parts(0.0, 0.9, 0.1, 0.0),              # part 1 at 0.9
            two_parts(0.0, 1.0, 0.0, 0.0),              # part 1 at 1.0
        ],
        "judge": [{"reasoning": "r", "verdict": "NOT_DECISIVE"}],
    })

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 5
    assert all("next_part" not in call["answer_format"]["properties"] for call in calls if call["role"] == "prover")
    assert "chosen by first-error rule" in log_text_of(tmp_path)


def test_the_first_error_rule_falls_back_to_the_most_likely_part():
    parts = [{"first": 1, "last": 2, "estimate": 0.3}, {"first": 3, "last": 4, "estimate": 0.4},
             {"first": 5, "last": 6, "estimate": 0.2}]
    assert debate.first_error_pick(parts)["first"] == 3
    parts[2]["estimate"] = 0.6
    assert debate.first_error_pick(parts)["first"] == 5


# ---------- What each role sees ----------
def test_the_judge_sees_only_the_task_and_the_last_step(monkeypatch, tmp_path):
    """The paper's oracle never reads the debate: only Step 0 and the one step left."""
    calls = fake_models(monkeypatch, a_prover_script())

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    judge_call = calls[-1]
    assert [step.index for step in judge_call["steps"]] == [0, 3]
    assert "argument" not in judge_call["question"].lower()


def test_the_estimator_reads_the_prover_s_parts_and_argument(monkeypatch, tmp_path):
    """The estimator's question names every part, quotes the prover's argument and explains every combination."""
    script = a_prover_script()
    script["prover"][0] = prover_says("ABOUT_RIGHT", cuts=[4], argument="argument-marker")
    calls = fake_models(monkeypatch, script)

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    question = next(call["question"] for call in calls if call["role"] == "estimator")
    assert "Part 1: steps 1 to 4" in question and "Part 2: steps 5 to 9" in question
    assert "argument-marker" in question
    assert "parts_1_2: parts 1 and 2 each contain one" in question


def test_no_prompt_holds_the_label(monkeypatch, tmp_path):
    """No hindsight (rule 13): the annotators' reason never reaches a model."""
    calls = fake_models(monkeypatch, a_prover_script())

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert all("made-up reason" not in call["question"] for call in calls)


# ---------- Retries ----------
def test_a_decomposition_that_is_not_allowed_gets_one_retry(monkeypatch, tmp_path):
    """A cut outside the claim is rejected once; the retry counts as a call and says what was wrong."""
    script = a_prover_script()
    script["prover"].insert(0, prover_says("ABOUT_RIGHT", cuts=[9]))
    calls = fake_models(monkeypatch, script)

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert len(calls) == 11
    assert "cuts [9] must be increasing step numbers from 1 to 8" in calls[3]["question"]


def test_probabilities_close_to_1_are_rescaled_and_far_from_1_get_a_retry(monkeypatch, tmp_path):
    """A sum of 1.04 is accepted and rescaled; a sum of 1.5 is rejected once."""
    script = a_prover_script()
    script["estimator"] = [two_parts(0.5, 0.5, 0.25, 0.25), two_parts(0.1, 0.74, 0.1, 0.1)] + script["estimator"][1:]
    calls = fake_models(monkeypatch, script)

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 3
    assert "add up to 1.50" in [call for call in calls if call["role"] == "estimator"][1]["question"]
    assert "parts_1 0.71" in log_text_of(tmp_path)


def test_a_sum_right_at_the_edge_of_the_tolerance_is_accepted(monkeypatch, tmp_path):
    """The pilot's estimator gave 0, 0.95, 0, 0; floating-point rounding made 1 - 0.95 slightly above 0.05."""
    script = a_prover_script()
    script["estimator"][0] = two_parts(0.0, 0.95, 0.0, 0.0)
    calls = fake_models(monkeypatch, script)

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert len(calls) == 10     # no retry


def test_two_broken_replies_in_a_row_fail_the_run(monkeypatch, tmp_path):
    """Rule 11: after one retry, a second broken reply stops the run with no answer, and the log says why."""
    script = a_prover_script()
    script["estimator"] = [None, None]
    calls = fake_models(monkeypatch, script)

    answer = debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert answer is None
    assert [call["role"] for call in calls][-2:] == ["estimator", "estimator"]
    log_text = log_text_of(tmp_path)
    assert "RUN FAILED: the estimator gave an unusable reply twice" in log_text
    assert "Answer: no answer" in log_text


# ---------- Citations ----------
def test_citations_outside_the_claim_are_flagged():
    """Rule 12: step numbers the argument cites outside the claim's steps are made up."""
    assert debate.made_up_citations("Step 2 and step 12 matter; see Steps 4.", 1, 9) == [12]


def test_made_up_citations_appear_in_the_log(monkeypatch, tmp_path):
    script = a_prover_script()
    script["prover"][0] = prover_says("ABOUT_RIGHT", cuts=[4], argument="It started at step 40.")
    fake_models(monkeypatch, script)

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    assert "MADE-UP CITATIONS: [40]" in log_text_of(tmp_path)


# ---------- The paper's rewards and the log ----------
def test_the_rewards_follow_the_paper(monkeypatch):
    """d = 1: the opening pays r^2 when the drawn bit matches the claim; round k pays r^k * A^k * (outcome - estimate)."""
    monkeypatch.setattr(debate, "RewardRatio", 0.5)
    opening = {"claim_bit": 1, "probability": 1.0, "drawn_bit": 1}
    levels = [
        {"first": 1, "last": 2, "estimate": 1.0, "direction": "TOO_LOW", "outcome": 1},     # k = 1: 0.5 * 1 * 0
        {"first": 1, "last": 1, "estimate": 1.0, "direction": "TOO_HIGH"},                  # k = 0: 1 * -1 * (0 - 1)
    ]

    rewards = debate.paper_rewards(opening, levels, "NOT_DECISIVE")

    assert rewards["opening"] == pytest.approx(0.25)
    assert rewards["rounds"] == pytest.approx([0.0, 1.0])
    assert rewards["total"] == pytest.approx(1.25)


def test_the_log_shows_every_level_the_judge_and_the_rewards(monkeypatch, tmp_path):
    """Rule 14: each level's steps, estimate, direction, parts, probabilities and whether the label is inside."""
    fake_models(monkeypatch, a_prover_script())

    debate.run_prover_estimator_debate(make_run(), run_number=0, log_folder=tmp_path)

    log_text = log_text_of(tmp_path)
    assert "Parts per split q: 2, depth allowed: 5 rounds" in log_text
    assert "Opening: prover claims TRUE, estimator 0.90" in log_text
    assert "Level 1: steps 1 to 9 (estimate 0.90, chosen by only claim), prover says ABOUT_RIGHT, label inside: yes" in log_text
    assert "parts 1-4 | 5-9; estimator none 0.10, parts_1 0.70, parts_2 0.10, parts_1_2 0.10" in log_text
    assert "Level 4: steps 3 to 3" in log_text
    assert "Judge on step 3: DECISIVE" in log_text
    assert "Prover's rewards (paper):" in log_text


if __name__ == "__main__":
    # Here pressing play runs every test in this file, with one line per test.
    sys.exit(pytest.main([__file__, "-v"]))
