"""Tests for data.py: download Who&When, remove bad runs, print a run, split into pilot and test,
and make a human review set.

Press play on this file to run all its tests.
"""

import json
import sys
from pathlib import Path

# Here we add the project folder to Python's search path, so this file can import data.py
# when you press play on it.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))

import pytest

import data


def test_setting_up_the_data_folder_creates_both_folders_inside_the_project():
    """The downloaded runs and the split files each get a folder inside the project's data/ folder."""
    data.set_up_data_folder()

    for folder in [data.WHO_AND_WHEN_FOLDER, data.SPLITS_FOLDER]:
        assert folder.is_dir(), f"Missing folder: {folder}"
        assert PROJECT_FOLDER in folder.parents, f"{folder} is outside the project"


def test_download_returns_all_58_runs_and_reads_a_known_run_correctly():
    """Who&When Hand-Crafted has 58 runs; 1.json (read by hand) has 29 steps and its Decisive step is 12, by WebSurfer."""
    all_runs = data.download_who_and_when()

    assert len(all_runs) == 58

    first_run = all_runs[0]
    assert first_run.file_name == "1.json"
    assert len(first_run.steps) == 29
    assert first_run.decisive_step == 12
    assert first_run.decisive_agent == "WebSurfer"


def test_a_download_that_stops_halfway_leaves_no_broken_file(tmp_path, monkeypatch):
    """If a download breaks off, no half-written file may be left under the real name, or the next run would skip it."""
    monkeypatch.setattr(data, "WHO_AND_WHEN_FOLDER", tmp_path)

    def download_that_breaks_halfway(address, file_path):
        """Pretend to download: write part of the file, then fail like a dropped internet connection."""
        Path(file_path).write_text('{"history": [')
        raise OSError("internet connection dropped")

    # Here we swap the real download for one that breaks, because the real network cannot be broken on purpose.
    monkeypatch.setattr(data.urllib.request, "urlretrieve", download_that_breaks_halfway)

    with pytest.raises(OSError):
        data.download_who_and_when()

    assert not (tmp_path / "1.json").exists()


def make_run(number_of_steps: int, decisive_step: int) -> data.Trajectory:
    """Build a small made-up run with the given number of steps and Decisive step, for tests that need no real data."""
    steps = [data.Step(index=step_number, agent="WebSurfer", text="...") for step_number in range(number_of_steps)]
    return data.Trajectory(
        file_name="made-up.json",
        id="made-up",
        question="made-up question",
        steps=steps,
        decisive_step=decisive_step,
        decisive_agent="WebSurfer",
        decisive_reason="made-up reason",
    )


def test_a_run_whose_decisive_step_does_not_exist_is_removed_with_a_reason(capsys):
    """A run labelled with step 5 but holding only steps 0 to 2 is removed, and the printout says why."""
    good_run = make_run(number_of_steps=3, decisive_step=1)
    bad_run = make_run(number_of_steps=3, decisive_step=5)

    usable_runs = data.remove_bad_runs([good_run, bad_run])

    assert usable_runs == [good_run]
    printed_text = capsys.readouterr().out
    assert "step 5" in printed_text
    assert "steps 0 to 2" in printed_text


def test_all_58_real_runs_are_usable():
    """In the JSON version of Who&When every Decisive step exists, so all 58 runs are kept.
    (The Parquet version has 3 broken labels; the JSON files have them corrected.)"""
    all_runs = data.download_who_and_when()

    usable_runs = data.remove_bad_runs(all_runs)

    assert len(usable_runs) == 58


def test_printing_a_run_by_number_shows_its_steps_and_then_its_label(capsys):
    """Run number 1 is 1.json: the printout shows its question and ends with its label (Decisive step 12, WebSurfer)."""
    usable_runs = data.remove_bad_runs(data.download_who_and_when())
    capsys.readouterr()

    data.print_trajectory(usable_runs, 1)

    printed_text = capsys.readouterr().out
    assert usable_runs[0].question in printed_text
    # Here we check the label comes after the last step, so a reader sees the steps first.
    assert printed_text.index("--- Step 28 |") < printed_text.index("LABEL: Decisive step 12, by WebSurfer")


def test_printing_a_run_number_that_does_not_exist_gives_a_clear_message(capsys):
    """Asking for run 0 or a number past the last run prints which numbers are allowed, instead of crashing."""
    usable_runs = [make_run(number_of_steps=3, decisive_step=1)]

    data.print_trajectory(usable_runs, 0)
    data.print_trajectory(usable_runs, 2)

    printed_text = capsys.readouterr().out
    assert printed_text.count("Choose a number from 1 to 1") == 2


def test_split_writes_one_pilot_run_and_all_runs_as_test_replacing_the_old_split(tmp_path):
    """The pilot holds 1 run, the test holds all runs (pilot included), and an old split is replaced.
    tmp_path is a temporary folder from pytest, so the real data/splits/ is never touched."""
    five_runs = [make_run(number_of_steps=3, decisive_step=1) for _ in range(5)]
    for run_number, run in enumerate(five_runs, start=1):
        run.id = f"run-{run_number}"

    # Here we put an old, different split in the folder, to check it gets replaced.
    (tmp_path / "pilot.json").write_text('[{"number": 1}, {"number": 2}, {"number": 3}]')

    data.split_pilot_and_test(five_runs, splits_folder=tmp_path)

    pilot_split = json.loads((tmp_path / "pilot.json").read_text())
    test_split = json.loads((tmp_path / "test.json").read_text())
    assert len(pilot_split) == 1
    assert len(test_split) == 5
    assert pilot_split[0] in test_split
    assert pilot_split[0]["id"] == f"run-{pilot_split[0]['number']}"


def make_six_different_runs() -> list[data.Trajectory]:
    """Build six made-up runs with different IDs, enough to pick five different ones for human review."""
    six_runs = [make_run(number_of_steps=3, decisive_step=1) for _ in range(6)]
    for run_number, run in enumerate(six_runs, start=1):
        run.id = f"run-{run_number}"
        run.file_name = f"{run_number}.json"
    return six_runs


def test_human_review_split_writes_five_different_runs_without_their_labels(tmp_path):
    """Five files for five different runs; each shows the steps and an empty answer section, but never the label."""
    data.human_review_split(make_six_different_runs(), review_folder=tmp_path)

    review_files = sorted(tmp_path.glob("*.md"))
    assert len(review_files) == 5

    for review_file in review_files:
        review_text = review_file.read_text()
        assert "--- Step 0 |" in review_text
        assert "## Your answer" in review_text
        # Here we check the label never appears: no LABEL line and no reason text.
        assert "LABEL" not in review_text
        assert "made-up reason" not in review_text


def test_human_review_split_refuses_when_the_folder_is_not_empty(tmp_path, capsys):
    """If the review folder already holds a file, nothing is written, so typed answers are never lost."""
    existing_review = tmp_path / "run_3.md"
    existing_review.write_text("answers typed by a reviewer")

    data.human_review_split(make_six_different_runs(), review_folder=tmp_path)

    assert [path.name for path in tmp_path.iterdir()] == ["run_3.md"]
    assert existing_review.read_text() == "answers typed by a reviewer"
    assert "not empty" in capsys.readouterr().out


if __name__ == "__main__":
    # Here we run every test in this file when you press play on it.
    pytest.main([__file__, "-v"])
