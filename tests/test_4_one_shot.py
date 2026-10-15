"""Tests for methods/one_shot.py: the vote, the early stop, and one-shot on a made-up run with the live model.

Press play on this file to run all its tests. The one-shot test talks to the live model, so start this project's
Ollama server first (setup/start_ollama_server.py); if it is not running, that test is skipped.
"""

import sys
from pathlib import Path

# Here we add the project folder, the methods folder and the setup folder to Python's search path,
# so this file can import one_shot.py, data.py and the server check when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
sys.path.insert(0, str(PROJECT_FOLDER / "methods"))
sys.path.insert(0, str(PROJECT_FOLDER / "setup"))

import pytest

import data
import one_shot
from start_ollama_server import ollama_server_is_running


def test_the_vote_picks_the_step_named_most_often():
    """Three votes for step 7 beat one vote for step 3."""
    assert one_shot.most_named_step([7, 3, 7, 7]) == 7


def test_a_tie_goes_to_the_earliest_step():
    """Two votes each for steps 7 and 3: step 3 wins, because it comes first in the run."""
    assert one_shot.most_named_step([7, 3, 7, 3]) == 3


def test_early_stop_only_when_every_call_named_the_same_step():
    """Five votes for step 4 agree; a different step, or a call with no vote (None), breaks the streak."""
    assert one_shot.all_votes_agree([4, 4, 4, 4, 4]) is True
    assert one_shot.all_votes_agree([4, 4, 5, 4, 4]) is False
    assert one_shot.all_votes_agree([4, 4, None, 4, 4]) is False


def test_one_shot_on_a_made_up_run_answers_a_real_step_and_writes_its_log(tmp_path):
    """On the live model, one-shot answers a step that is in the run, uses 5 to 10 calls, and writes its log.
    tmp_path is a temporary folder from pytest, so nothing is written to runs/."""
    # Here we skip, rather than fail, when the server is off, because this test needs the live model.
    if not ollama_server_is_running():
        pytest.skip("This project's Ollama server is not running; press play on setup/start_ollama_server.py first.")
    # Here we make a short run whose mistake is clear: the agent reports the wrong movie as the answer.
    run = data.Trajectory(
        file_name="made_up.json", id="made-up", question="Which Daniel Craig movie is rated highest on IMDb?",
        steps=[
            data.Step(index=0, agent="human", text="Which Daniel Craig movie is rated highest on IMDb?"),
            data.Step(index=1, agent="WebSurfer", text="IMDb ratings: Knives Out 7.9, Skyfall 7.8, Casino Royale 8.0."),
            data.Step(index=2, agent="Orchestrator", text="FINAL ANSWER: Knives Out, the highest rated."),
        ],
        decisive_step=2, decisive_agent="Orchestrator", decisive_reason="made-up reason",
    )

    answer = one_shot.run_one_shot(run, run_number=0, log_folder=tmp_path)

    assert answer in [0, 1, 2]
    log_text = next(tmp_path.glob("run_0_*.md")).read_text()
    calls_used = log_text.count("### Call ")
    assert 5 <= calls_used <= one_shot.DefaultNoOfCalls


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
