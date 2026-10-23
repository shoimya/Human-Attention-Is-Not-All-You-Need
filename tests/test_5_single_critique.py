"""Tests for methods/single_critique.py: one round (proposer, critic, judge), the vote over rounds, and the log.

Press play on this file to run all its tests. The models are replaced by scripted answers, so no server is needed
and nothing is written to runs/.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder and the methods folder to Python's search path,
# so this file can import single_critique.py and data.py when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "methods"))

import pytest

import data
import single_critique


def make_run() -> data.Trajectory:
    """Build a made-up run with four steps (0 to 3) whose Decisive step is 2."""
    return data.Trajectory(
        file_name="made_up.json", id="made-up", question="Which Daniel Craig movie is rated highest on IMDb?",
        steps=[
            data.Step(index=0, agent="human", text="Which Daniel Craig movie is rated highest on IMDb?"),
            data.Step(index=1, agent="WebSurfer", text="IMDb ratings: Knives Out 7.9, Skyfall 7.8, Casino Royale 8.0."),
            data.Step(index=2, agent="Orchestrator", text="Knives Out has the highest rating."),
            data.Step(index=3, agent="Orchestrator", text="FINAL ANSWER: Knives Out."),
        ],
        decisive_step=2, decisive_agent="Orchestrator", decisive_reason="made-up reason",
    )


def proposer_says(step: int) -> dict:
    """Build a proposer's answer naming the given step."""
    return {"reasoning": "made-up reasoning", "step": step, "reason": f"Step {step} went wrong."}


def critic_says(stance: str, step: int) -> dict:
    """Build a critic's answer with the given stance and step."""
    return {"reasoning": "made-up reasoning", "stance": stance, "step": step, "evidence": f"See step {step}."}


def judge_says(winner: str) -> dict:
    """Build a judge's answer choosing the given side."""
    return {"reasoning": "made-up reasoning", "winner": winner, "reason": "made-up reason", "confidence": 0.8}


def fake_models(monkeypatch, answers_by_role: dict[str, list]) -> list[str]:
    """Replace the live models with scripted answers, one list per role, used in order.
    An answer of None stands for a reply that is not valid JSON. Return the roles in the order they were asked."""
    asked_roles = []

    def answer_from_the_script(role, model, system_prompt, steps, question, answer_format, temperature, seed, log):
        """Log the call the way send_to_ollama() does, then give the role's next scripted answer."""
        asked_roles.append(role)
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
    monkeypatch.setattr(single_critique.runV2, "send_to_ollama", answer_from_the_script)
    return asked_roles


def test_when_the_critic_agrees_the_round_takes_the_proposers_step_without_asking_the_judge(monkeypatch):
    """Proposer says 2, critic agrees: the round's step is 2, after 2 calls (no judge)."""
    asked_roles = fake_models(monkeypatch, {"proposer": [proposer_says(2)], "critic": [critic_says("AGREE", 2)]})

    step, round_line = single_critique.run_one_round(make_run(), [], seed=43)

    assert step == 2
    assert asked_roles == ["proposer", "critic"]
    assert "critic agreed" in round_line


def test_when_the_critic_disagrees_and_the_judge_sides_with_it_the_round_takes_the_critics_step(monkeypatch):
    """Proposer says 3, critic says 2, judge picks CRITIC: the round's step is 2, after 3 calls."""
    asked_roles = fake_models(monkeypatch, {"proposer": [proposer_says(3)], "critic": [critic_says("DISAGREE", 2)],
                                            "judge": [judge_says("CRITIC")]})

    step, round_line = single_critique.run_one_round(make_run(), [], seed=43)

    assert step == 2
    assert asked_roles == ["proposer", "critic", "judge"]
    assert "judge chose CRITIC" in round_line and "confidence 0.8" in round_line


def test_when_the_critic_disagrees_and_the_judge_sides_with_the_proposer_the_round_takes_the_proposers_step(monkeypatch):
    """Proposer says 3, critic says 2, judge picks PROPOSER: the round's step is 3."""
    fake_models(monkeypatch, {"proposer": [proposer_says(3)], "critic": [critic_says("DISAGREE", 2)],
                              "judge": [judge_says("PROPOSER")]})

    step, round_line = single_critique.run_one_round(make_run(), [], seed=43)

    assert step == 3


def test_a_broken_proposer_reply_ends_the_round_with_no_step_after_one_call(monkeypatch):
    """A proposer reply that is not valid JSON still counts as a call, and the round stops with no step."""
    asked_roles = fake_models(monkeypatch, {"proposer": [None]})

    step, round_line = single_critique.run_one_round(make_run(), [], seed=43)

    assert step is None
    assert asked_roles == ["proposer"]
    assert "no step" in round_line


def test_a_step_that_is_not_in_the_run_ends_the_round_with_no_step(monkeypatch):
    """A proposer step outside the run (the run has steps 0 to 3), or such a critic step, gives the round no step."""
    fake_models(monkeypatch, {"proposer": [proposer_says(99), proposer_says(2)],
                              "critic": [critic_says("DISAGREE", 99)]})

    proposer_step, proposer_line = single_critique.run_one_round(make_run(), [], seed=43)
    critic_step, critic_line = single_critique.run_one_round(make_run(), [], seed=44)

    assert proposer_step is None and "proposer" in proposer_line
    assert critic_step is None and "step 99 is not in the run" in critic_line


def test_single_critique_votes_over_the_rounds_and_writes_every_round_in_its_log(monkeypatch, tmp_path):
    """Rounds give steps 2, 1 and 1: the answer is 1, and the log lists every round and all 7 calls.
    tmp_path is a temporary folder from pytest, so nothing is written to runs/."""
    monkeypatch.setattr(single_critique, "NumberOfRounds", 3)
    fake_models(monkeypatch, {
        "proposer": [proposer_says(2), proposer_says(3), proposer_says(1)],
        "critic": [critic_says("AGREE", 2), critic_says("DISAGREE", 1), critic_says("AGREE", 1)],
        "judge": [judge_says("CRITIC")],
    })

    answer = single_critique.run_single_critique(make_run(), run_number=0, log_folder=tmp_path)

    assert answer == 1
    log_text = next(tmp_path.glob("run_0_*.md")).read_text()
    assert "- Calls: 7" in log_text
    assert "- Round 1: step 2 (critic agreed)" in log_text
    assert "- Round 2: step 1 (proposer 3, critic 1, judge chose CRITIC, confidence 0.8)" in log_text
    assert "- Round 3: step 1 (critic agreed)" in log_text


def test_each_round_uses_its_own_seed(monkeypatch, tmp_path):
    """Round 1 uses the base seed plus 1, round 2 plus 2, and every role in a round uses that round's seed."""
    monkeypatch.setattr(single_critique, "NumberOfRounds", 2)
    fake_models(monkeypatch, {"proposer": [proposer_says(2), proposer_says(2)],
                              "critic": [critic_says("AGREE", 2), critic_says("AGREE", 2)]})

    single_critique.run_single_critique(make_run(), run_number=0, log_folder=tmp_path)

    log_text = next(tmp_path.glob("run_0_*.md")).read_text()
    assert log_text.count(f"seed {single_critique.Seed + 1},") == 2
    assert log_text.count(f"seed {single_critique.Seed + 2},") == 2


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
