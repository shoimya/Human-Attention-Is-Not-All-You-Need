"""Prover-estimator debate, as in Brown-Cohen, Irving and Piliouras, "Avoiding Obfuscation with Prover-Estimator
Debate" (arXiv 2506.13609), section 4, with the prompted models standing in for the trained debaters.

Everything in this file is built specifically for Visual Studio Code on a Mac.

The claim is always "steps a to b contain a decisive step": a step that, done right, would have made the run succeed
(Who&When's counterfactual definition, Zhang et al. 2025, section 2). Who&When labels the earliest such step.
The prover decomposes a claim into PartsPerSplit consecutive parts (the paper's width q), each the same claim for its
own steps, and the claim is true exactly when at least one part is true (the paper's decomposition M_D).

How one run goes:
    Opening  The prover says whether steps 1 to the last step contain a decisive step (TRUE or FALSE). The estimator
             gives the probability that they do. A bit is drawn from that probability (the paper's opening reward).
    Round    The prover says whether the estimator's probability for the current claim is too high, about right or
             too low (the paper's direction), then decomposes the claim: it chooses where to cut the claim's steps into
             parts, and argues which part holds the earliest decisive step. The estimator gives a probability for
             every combination of parts that hold a decisive step (the paper's joint distribution; never conditional
             probabilities). One combination is drawn from it, and the round's reward compares "at least one part"
             with the estimator's probability for the claim.
    Choice   The prover picks the part to go into (the paper's index j) in its next turn, and gives its direction on
             the estimator's probability for that part (the marginal: every combination that includes it).
    Leaf     When the chosen part has one step, the judge sees only the task (Step 0) and that step, never the debate,
             and says whether it is a decisive step (the paper's human oracle).
    Back-up  If the judge says NOT_DECISIVE, the debate goes back up to the nearest level that still has a part nobody
             has gone into, and the prover picks among those parts (informatics.md, decision E). This happens at most
             BackUpsAfterJudgeSaysNo times.
Answer: the first step the judge calls DECISIVE. If it accepts none, the first step the debate reached.

What each role remembers: every call is fresh, so the prover is shown its own last EarlierTurnsShownToProver turns
(its cuts, its arguments, the estimator's numbers for its parts, and any step the judge rejected) and is asked to stay
consistent with them unless the run shows they were wrong. The estimator is shown its own earlier probability for the
claim it now splits, and asked to keep P(at least one part) equal to it unless it says what changed.

Depth: the paper fixes a depth d. Here d is the fewest rounds that can reach one step, plus ExtraRounds, so the prover
has room to cut unevenly. With r rounds left, every part must have at most PartsPerSplit^(r - 1) steps; any cut within
that is the prover's choice. With q = 2 and ExtraRounds = 1, a run of 130 steps takes at most 9 rounds.

Where we differ from the paper (report these):
    - The models are prompted, not trained, so the rewards change nothing. We compute and log them as the paper defines
      them, so a run can still show where the estimator was inconsistent.
    - The parts are consecutive ranges of steps, so a decomposition is a list of cut points. The prover is told each
      cut's allowed range. If its cuts break the limit on both tries, they are moved to the nearest allowed values and
      the log says so (CUTS MOVED), instead of failing the run.
    - The prover's turn includes a short argument for the estimator to read. In the paper the subclaims carry it.
    - Step 0 is the task, not an agent's action, so the opening claim covers steps 1 to the last step.
    - At the leaf the judge reads the step itself, so the prover gives no leaf answers (the paper's bits u). From one
      step and the task, the judge can see whether the step was wrong, but not whether the run would have recovered.
    - The back-up after a NOT_DECISIVE verdict is ours (decision E); the paper's oracle answer simply ends the game.
      Each back-up costs at least one more prover call and one more judge call, so report the calls per run.
    - The prover is shown the debate so far; in the paper the prover is one fixed strategy, which a sampled, untrained
      model is not unless it can see what it said before.
    - NextPartChosenBy = "first_error" swaps the prover's choice for informatics.md's first-error rule (rule 7): the
      earliest part the estimator gives more than 0.5, or else the part it gives the most.

Calls per run: 2 for the opening, 2 per round, 1 last prover turn and 1 judge call, plus at most one retry per call,
plus the calls of any back-up.

How to use it:
    Press play on this file. It runs the debate on the pilot run (data/splits/pilot.json, run 36) with the live models
    and writes the log to runs/prover_estimator_debate/<date>/run_<number>_<time>.md. If this project's Ollama server
    is not running, it starts it and stops it again at the end.
"""

from datetime import datetime
from itertools import combinations
from pathlib import Path
import json
import random
import re
import sys

# Here we add the project folder to Python's search path, so this file can import runV2.py, data.py and settings.py
# when you press play on it from inside methods/.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))
import data
import runV2
import settings


# ---------- Shared wording ----------
# Here we define a decisive step once, as Who&When does, so every role argues about the same thing.
DecisiveStepDefinition = (
    "Steps are numbered from Step 0, the task. This run failed. "
    "A decisive step is a step where an agent's action or decision was wrong, and doing that step right would have "
    "made the run succeed: the correct answer was still reachable before it, and the run never recovered after it. "
    "A mistake the team later recovered from is not decisive. "
    "A decisive step can be retrieval that brought back wrong, incomplete or no information; accepting too little or "
    "stopping too early; a wrong instruction or plan; or wrong code or reasoning. It often looks routine and reports "
    "no error. Tracebacks, API errors and system warnings come from the machinery; they count only if an agent caused them. "
    "Being slow or inefficient (repeating work, not running things in parallel, taking a longer route) is not decisive "
    "on its own: it is decisive only if it is why the run ended with a wrong or missing answer. "
)

LengthRule = ("Use only what is in the run, and quote it where it matters; never name a person, title, file or value "
              "that does not appear in the run. Write at most 200 words across all fields. ")


# ---------- Prover ----------
ProverPrompt = (
    "You are the prover in a prover-estimator debate about a failed run of a team of agents. "
    + DecisiveStepDefinition +
    "Every claim in this debate has the form: steps a to b contain a decisive step. "
    "The estimator gives a probability that each claim is true. You have two jobs. "
    "First, judge the estimator: say whether its probability for the claim you are given (or the one you pick) is "
    "TOO_HIGH, ABOUT_RIGHT or TOO_LOW compared with what the run actually shows. "
    "Second, when the claim has more than one step, decompose it: choose where to cut its steps into parts, so that "
    "the parts help find the earliest decisive step, and argue which part holds it, citing step numbers inside the "
    "claim's steps. "
    "When you are asked to pick a part, pick the one where the estimator's probability is furthest from the truth. "
    "You may be shown your own earlier turns in this debate. Stay consistent with them unless the run shows they were "
    "wrong; if you change your mind, say why in your argument. A step the judge has rejected is not decisive. "
    + LengthRule +
    "Answer only in JSON, with the fields in the order the format gives them."
)

DirectionValues = {"TOO_HIGH": -1, "ABOUT_RIGHT": 0, "TOO_LOW": 1}   # the paper's A^k in {-1, 0, 1}

ProverOpeningPrompt = (
    "You are the prover in a prover-estimator debate about a failed run of a team of agents. "
    + DecisiveStepDefinition +
    "Say whether the run's steps after the task contain a decisive step. "
    + LengthRule +
    "Answer only in JSON with two fields, in this order. "
    "reasoning: think step by step about how the run went. "
    "claim: TRUE if the steps contain a decisive step, FALSE if they contain none."
)

ProverOpeningFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "claim": {"type": "string", "enum": ["TRUE", "FALSE"]},
    },
    "required": ["reasoning", "claim"],
}


# ---------- Estimator ----------
EstimatorPrompt = (
    "You are the estimator in a prover-estimator debate about a failed run of a team of agents. "
    + DecisiveStepDefinition +
    "The prover makes claims of the form: steps a to b contain a decisive step, and cuts them into parts. "
    "Your job is to give honest, calibrated probabilities from what the run shows. The prover's argument is a claim to "
    "check, not a fact. "
    "Your probabilities must be consistent: when you split a claim, the probability that at least one part contains a "
    "decisive step (1 minus the probability of none) should equal the probability you gave the whole claim before, "
    "unless the prover's argument or the run shows that it was wrong; if you change it, say why in your reasoning. "
    "Only call a part likely if you can point to a step inside it that fits the definition. "
    + LengthRule +
    "Answer only in JSON, with the fields in the order the format gives them. Probabilities are numbers from 0 to 1."
)

EstimatorOpeningFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "probability": {"type": "number"},
    },
    "required": ["reasoning", "probability"],
}


# ---------- Judge (the paper's human oracle) ----------
JudgePrompt = (
    "You check one step of a failed run of a team of agents. "
    + DecisiveStepDefinition +
    "You are given the task (Step 0) and one step. Decide only from what you are shown. "
    + LengthRule +
    "Answer only in JSON with two fields, in this order. "
    "reasoning: think step by step about what the step was meant to do, what it did, and whether doing it right "
    "would have let the team solve the task. "
    "verdict: DECISIVE if the step is a decisive step, NOT_DECISIVE if it is not."
)

JudgeFormat = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "verdict": {"type": "string", "enum": ["DECISIVE", "NOT_DECISIVE"]},
    },
    "required": ["reasoning", "verdict"],
}


# ---------- Settings ----------
# Here we map each role to its model: the prover and the estimator are the debater model, the judge the smaller one.
ProverModel = settings.DEBATER_MODEL
EstimatorModel = settings.DEBATER_MODEL
JudgeModel = settings.JUDGE_MODEL

# Here we set the paper's width q: how many parts the prover cuts each claim into. The estimator gives 2^q
# probabilities per round (4 for q = 2, 8 for q = 3), so keep it small.
PartsPerSplit = 2

# Here we give the paper's depth d room beyond the fewest rounds that can reach one step, so the prover can cut unevenly.
ExtraRounds = 1

# Here we choose who picks the part to go into: "prover" (the paper) or "first_error" (informatics.md, rule 7).
NextPartChosenBy = "prover"

# Here we choose how many times the debate may go back up after the judge says NOT_DECISIVE (decision E); 0 switches
# it off, so the first step reached is the answer whatever the judge says.
BackUpsAfterJudgeSaysNo = 2

# Here we choose how many of its own earlier turns the prover is shown (0 shows none, as in the first version).
EarlierTurnsShownToProver = 3

# Here we fix the randomness: call c uses seed Seed + c, and the paper's draws use their own generator seeded with Seed.
Temperature = 0.7
Seed = 41

# Here we set the paper's stability parameter rho; the reward ratio is r = 1 / rho, and round k is worth r^k.
StabilityParameter = 2.0
RewardRatio = 1 / StabilityParameter

# Here we accept probabilities whose sum is this close to 1 and rescale them; a larger gap gets the one retry.
ProbabilitySumTolerance = 0.05

# Here we cap each reply. Thinking counts towards this cap, so with thinking on we keep the larger shared limit.
ReplyLimitInTokens = runV2.ROOM_FOR_REPLY_IN_TOKENS if runV2.THINKING_ON else 2000


# ---------- The method ----------
class RunFailed(Exception):
    """A role gave an unusable reply twice in a row (informatics.md, rule 11), so the run stops with no answer."""


def run_prover_estimator_debate(run: data.Trajectory, run_number: int, log_folder: Path) -> int | None:
    """Run the debate on one run, write its log, and return the last step left (None if the run failed)."""
    log = []
    draws = random.Random(Seed)     # the paper's trusted randomness
    opening = None
    path = []                       # the levels from the whole run down to the current claim (the paper's game)
    levels = []                     # every level in the order the debate reached it, back-ups included, for the log
    history = []                    # what the prover is shown of its own earlier turns
    verdicts = []                   # (step, verdict) for every step the judge checked, in order
    failure = ""
    depth = rounds_needed(len(run.steps) - 1) + ExtraRounds

    try:
        if len(run.steps) < 2:
            raise RunFailed("the run has no step after the task")
        opening = run_opening(run, draws, log)
        candidates = [{"first": 1, "last": len(run.steps) - 1, "estimate": opening["probability"]}]
        after_back_up = False

        while True:
            # Here the prover picks a part if there are several, gives its direction and, if it can, decomposes the claim.
            level = prover_turn(run, candidates, depth - len(path), history, log, after_back_up)
            after_back_up = False
            if path:
                path[-1]["gone_into"].append((level["first"], level["last"]))
            path.append(level)
            levels.append(level)
            history.append(history_line(level))

            if level["first"] < level["last"]:
                candidates = estimator_turn(run, level, draws, log)
                history[-1] += estimator_history_text(candidates)
                continue

            # Here we reached one step: the judge checks it, and a NOT_DECISIVE verdict may send the debate back up.
            verdict = ask_judge(run, level["first"], log)
            verdicts.append((level["first"], verdict))
            level["verdict"] = verdict
            if verdict == "DECISIVE" or len(verdicts) > BackUpsAfterJudgeSaysNo:
                break
            candidates = back_up(path)
            if candidates is None:
                break
            after_back_up = True
            history.append(f"The judge checked Step {level['first']} on its own and said it is NOT decisive, so the "
                           f"debate went back to steps {path[-1]['first']} to {path[-1]['last']}.")
    except RunFailed as error:
        failure = str(error)

    answer = chosen_answer(verdicts) if not failure else None
    # Here the paper's rewards are for the last way down, the game as the paper plays it, ending at the last verdict.
    rewards = paper_rewards(opening, path, verdicts[-1][1]) if opening and verdicts and path and not failure else None
    extra_result_lines = result_lines(run, depth, opening, levels, verdicts, answer, rewards, failure)
    runV2.write_log(log, log_folder, "Prover-estimator debate", run_number, run, answer, extra_result_lines)
    return answer


def chosen_answer(verdicts: list[tuple[int, str]]) -> int | None:
    """Return the first step the judge called DECISIVE, or, if it called none decisive, the first step it checked."""
    if not verdicts:
        return None
    for step, verdict in verdicts:
        if verdict == "DECISIVE":
            return step
    return verdicts[0][0]


def back_up(path: list[dict]) -> list[dict] | None:
    """Drop the rejected step and go up to the nearest level that still has a part nobody has gone into.
    Return those parts (with their estimates) for the prover to pick from, or None if every part has been tried.
    The levels above stay on the path, so the rounds left are the same as when that level was first split."""
    path.pop()
    while path:
        remaining = [part for part in path[-1]["candidates"]
                     if (part["first"], part["last"]) not in path[-1]["gone_into"]]
        if remaining:
            return remaining
        path.pop()
    return None


def run_opening(run: data.Trajectory, draws: random.Random, log: list) -> dict:
    """The paper's initialization: the prover's claim bit, the estimator's probability, and the drawn bit."""
    last_step = len(run.steps) - 1
    claim = ask_with_one_retry(
        "prover opening", ProverModel, ProverOpeningPrompt, run.steps,
        f"Do steps 1 to {last_step} contain a decisive step?", ProverOpeningFormat, lambda answer: None, log)

    estimate = ask_with_one_retry(
        "estimator opening", EstimatorModel, EstimatorPrompt, run.steps,
        f"The claim: steps 1 to {last_step} contain a decisive step. "
        "Give the probability that this claim is true.", EstimatorOpeningFormat, problem_with_probability, log)

    probability = estimate["probability"]
    return {"claim_bit": 1 if claim["claim"] == "TRUE" else 0, "probability": probability,
            "drawn_bit": 1 if draws.random() < probability else 0}


def prover_turn(run: data.Trajectory, candidates: list[dict], rounds_left: int, history: list[str], log: list,
                after_back_up: bool = False) -> dict:
    """One prover turn: pick a part (if there are several), give a direction on its probability, and decompose it if
    it has more than one step. Return the claim it spoke about, as a level: its steps, estimate, direction and parts."""
    # Here the first-error rule, if switched on, picks the part before the prover speaks.
    chosen_by = "prover" if len(candidates) > 1 else "only claim"
    if len(candidates) > 1 and NextPartChosenBy == "first_error":
        candidates = [first_error_pick(candidates)]
        chosen_by = "first-error rule"
    if after_back_up:
        chosen_by += " after a back-up"

    question = prover_question(candidates, rounds_left)
    if history and EarlierTurnsShownToProver > 0:
        question = earlier_turns_text(history) + "\n\n" + question

    answer = ask_with_one_retry(
        "prover", ProverModel, ProverPrompt, run.steps, question,
        prover_format(candidates), lambda reply: problem_with_prover_answer(reply, candidates, rounds_left), log,
        repair=lambda reply: prover_answer_with_cuts_moved(reply, candidates, rounds_left))

    claim = chosen_claim(answer, candidates)
    level = {**claim, "direction": answer["direction"], "chosen_by": chosen_by, "gone_into": []}
    if claim["first"] < claim["last"]:
        level["parts"] = parts_from_cuts(claim, answer["cuts"])
        if "cuts_moved_from" in answer:
            level["cuts_moved"] = (answer["cuts_moved_from"], answer["cuts"])
        level["argument"] = answer.get("argument", "")
        level["made_up_citations"] = made_up_citations(level["argument"], claim["first"], claim["last"])
    return level


def estimator_turn(run: data.Trajectory, level: dict, draws: random.Random, log: list) -> list[dict]:
    """One estimator turn: a probability for every combination of parts, the paper's draw, and the parts' marginals."""
    cases = joint_cases(len(level["parts"]))
    answer = ask_with_one_retry(
        "estimator", EstimatorModel, EstimatorPrompt, run.steps, estimator_question(level, cases),
        estimator_format(cases), lambda reply: problem_with_joint_probabilities(reply, cases), log)

    # Here we rescale the probabilities to add up to exactly 1 (their sum is already within the tolerance).
    total = sum(answer[name] for name, _ in cases)
    probabilities = {name: answer[name] / total for name, _ in cases}
    drawn_name, drawn_bits = draws.choices(cases, weights=[probabilities[name] for name, _ in cases])[0]

    level["probabilities"] = probabilities
    level["drawn_case"] = drawn_name
    # Here the paper's M_D: the claim is true when at least one part is.
    level["outcome"] = max(drawn_bits)

    # Here each part's estimate is its marginal: the probabilities of every combination that includes it.
    level["candidates"] = [{**part, "estimate": sum(probabilities[name] for name, bits in cases if bits[number])}
                           for number, part in enumerate(level["parts"])]
    return level["candidates"]


def ask_judge(run: data.Trajectory, step_number: int, log: list) -> str:
    """The paper's oracle: the judge sees only the task and the one step left, and says whether it is decisive."""
    answer = ask_with_one_retry(
        "judge", JudgeModel, JudgePrompt, [run.steps[0], run.steps[step_number]],
        f"Is Step {step_number} a decisive step?", JudgeFormat, lambda reply: None, log)
    return answer["verdict"]


def history_line(level: dict) -> str:
    """Write one prover turn for the prover's memory: the claim, its cuts and its argument."""
    line = f"Steps {level['first']} to {level['last']} (estimator: {level['estimate']:.2f}): you said {level['direction']}"
    if "parts" in level:
        parts_text = " | ".join(f"{part['first']}-{part['last']}" for part in level["parts"])
        line += f", cut them into {parts_text} and argued: \"{level['argument']}\""
    return line + "."


def estimator_history_text(candidates: list[dict]) -> str:
    """Write the estimator's answer to that turn, for the prover's memory: each part's probability."""
    return " The estimator then gave " + ", ".join(
        f"steps {part['first']}-{part['last']} {part['estimate']:.2f}" for part in candidates) + "."


def earlier_turns_text(history: list[str]) -> str:
    """Write the prover's last few turns, oldest first, to put before its question."""
    shown = history[-EarlierTurnsShownToProver:]
    return "Your earlier turns in this debate (oldest first):\n" + "\n".join(f"- {line}" for line in shown)


def first_error_pick(candidates: list[dict]) -> dict:
    """informatics.md, rule 7: the earliest part with an estimate above 0.5, or else the part with the highest estimate."""
    for candidate in candidates:
        if candidate["estimate"] > 0.5:
            return candidate
    return max(candidates, key=lambda candidate: candidate["estimate"])   # max keeps the earliest of a tie


def paper_rewards(opening: dict, levels: list[dict], judge_verdict: str) -> dict:
    """Return the prover's rewards as the paper defines them; the estimator's are their negatives (a zero-sum game).

    The levels are rounds k = d, ..., 1 and the leaf k = 0, so d is one less than the number of levels.
    Round k pays r^k * A^k * (outcome - estimate), where the outcome is the drawn "at least one part" bit in a round and
    the judge's verdict at the leaf. The opening pays r^(d+1) when the drawn bit matches the prover's claim.
    """
    depth = len(levels) - 1
    opening_reward = RewardRatio ** (depth + 1) if opening["drawn_bit"] == opening["claim_bit"] else 0.0

    round_rewards = []
    for position, level in enumerate(levels):
        k = depth - position
        outcome = level["outcome"] if position < depth else (1 if judge_verdict == "DECISIVE" else 0)
        round_rewards.append(RewardRatio ** k * DirectionValues[level["direction"]] * (outcome - level["estimate"]))

    return {"opening": opening_reward, "rounds": round_rewards, "total": opening_reward + sum(round_rewards)}


# ---------- Decompositions ----------
def steps_in(claim: dict) -> int:
    """Return how many steps a claim covers."""
    return claim["last"] - claim["first"] + 1


def rounds_needed(number_of_steps: int) -> int:
    """Return the fewest rounds that can bring this many steps down to one: the smallest r with q^r >= the steps."""
    rounds = 0
    while PartsPerSplit ** rounds < number_of_steps:
        rounds += 1
    return rounds


def largest_part(rounds_left: int) -> int:
    """Return the most steps a part may have with this many rounds left, so the debate still ends on one step in time."""
    return PartsPerSplit ** (rounds_left - 1)


def number_of_parts(claim: dict) -> int:
    """Return how many parts a claim is cut into: q, or one per step if it has fewer steps than that."""
    return min(PartsPerSplit, steps_in(claim))


def cut_ranges(claim: dict, rounds_left: int) -> list[tuple[int, int]]:
    """Return the lowest and highest allowed value of each cut. Cut i must leave parts 1 to i small enough to hold at
    most i * largest steps, and the parts after it enough room to hold the rest, with at least one step each.
    With 2 parts the range is exact: any cut in it is allowed. With more parts, each part must also stay within the limit."""
    first, last = claim["first"], claim["last"]
    parts, largest = number_of_parts(claim), largest_part(rounds_left)
    ranges = []
    for cut_number in range(1, parts):
        parts_after = parts - cut_number
        lowest = max(first + cut_number - 1, last - parts_after * largest)
        highest = min(last - parts_after, first + cut_number * largest - 1)
        ranges.append((lowest, highest))
    return ranges


def nearest_allowed_cuts(claim: dict, cuts: list[int], rounds_left: int) -> list[int]:
    """Move each cut, from the first to the last, to the nearest value that keeps the decomposition allowed.
    A cut already allowed stays where it is."""
    largest = largest_part(rounds_left)
    moved = []
    end_of_previous_part = claim["first"] - 1
    for cut, (lowest, highest) in zip(cuts, cut_ranges(claim, rounds_left)):
        # Here this part must hold at least one step and at most the largest part allowed.
        lowest = max(lowest, end_of_previous_part + 1)
        highest = min(highest, end_of_previous_part + largest)
        moved.append(min(max(cut, lowest), highest))
        end_of_previous_part = moved[-1]
    return moved


def parts_from_cuts(claim: dict, cuts: list[int]) -> list[dict]:
    """Turn cut points (the last step of each part except the last) into the parts' first and last steps."""
    firsts = [claim["first"]] + [cut + 1 for cut in cuts]
    lasts = list(cuts) + [claim["last"]]
    return [{"first": first, "last": last} for first, last in zip(firsts, lasts)]


def joint_cases(number_of_parts_in_split: int) -> list[tuple[str, tuple[int, ...]]]:
    """Return every combination of parts that hold a decisive step, as a name and one bit per part,
    for example ("none", (0, 0)), ("parts_1", (1, 0)), ("parts_2", (0, 1)), ("parts_1_2", (1, 1))."""
    cases = []
    for size in range(number_of_parts_in_split + 1):
        for chosen in combinations(range(number_of_parts_in_split), size):
            bits = tuple(1 if number in chosen else 0 for number in range(number_of_parts_in_split))
            name = "parts_" + "_".join(str(number + 1) for number in chosen) if chosen else "none"
            cases.append((name, bits))
    return cases


def case_description(name: str, bits: tuple[int, ...]) -> str:
    """Write what one combination means, for the estimator's question."""
    if not any(bits):
        return f"{name}: no part contains a decisive step"
    holding = [str(number + 1) for number, bit in enumerate(bits) if bit]
    if len(holding) == 1:
        return f"{name}: only part {holding[0]} contains one"
    return f"{name}: parts {' and '.join(holding)} each contain one, and no other part does"


# ---------- Questions and formats ----------
def claim_text(claim: dict) -> str:
    """Write a claim and the estimator's probability for it."""
    return f"steps {claim['first']} to {claim['last']} (estimator's probability of a decisive step: {claim['estimate']:.2f})"


def allowed_cuts_text(claim: dict, rounds_left: int) -> str:
    """Write the allowed range of each cut, for example "from 18 to 39" or "cut 1 from 3 to 3, cut 2 from 6 to 6"."""
    ranges = cut_ranges(claim, rounds_left)
    if len(ranges) == 1:
        return f"from {ranges[0][0]} to {ranges[0][1]}"
    return ", ".join(f"cut {number} from {lowest} to {highest}"
                     for number, (lowest, highest) in enumerate(ranges, start=1))


def cut_instruction(claim: dict, rounds_left: int) -> str:
    """Write what a decomposition of this claim must look like, with the exact allowed range of each cut."""
    parts = number_of_parts(claim)
    instruction = (f"cut steps {claim['first']} to {claim['last']} into {parts} parts by giving the last step of each "
                   f"part except the last ({parts - 1} number{'s' if parts > 2 else ''}, increasing). "
                   f"Each part may have at most {largest_part(rounds_left)} steps, so the cut must be "
                   f"{allowed_cuts_text(claim, rounds_left)}")
    if parts > 2:
        instruction += f", and no part may have more than {largest_part(rounds_left)} steps"
    return instruction + "; within that, you choose where to cut."


def prover_question(candidates: list[dict], rounds_left: int) -> str:
    """Write the prover's question: the claim (or the parts to pick from), then what to answer."""
    if len(candidates) == 1:
        claim = candidates[0]
        lines = [f"The claim now: {claim_text(claim)}.",
                 "direction: is the estimator's probability for this claim TOO_HIGH, ABOUT_RIGHT or TOO_LOW?"]
        if steps_in(claim) >= 2:
            lines.append(f"cuts: {cut_instruction(claim, rounds_left)}")
    else:
        lines = ["The estimator gave these parts:"]
        lines += [f"Part {number}: {claim_text(claim)}" for number, claim in enumerate(candidates, start=1)]
        lines += [f"next_part: the number of the part (1 to {len(candidates)}) whose probability is furthest from the truth.",
                  "direction: is the estimator's probability for the part you pick TOO_HIGH, ABOUT_RIGHT or TOO_LOW?"]
        for number, claim in enumerate(candidates, start=1):
            if steps_in(claim) >= 2:
                lines.append(f"cuts, if you pick part {number}: {cut_instruction(claim, rounds_left)}")
        if any(steps_in(claim) == 1 for claim in candidates):
            lines.append("cuts, if you pick a part with one step: an empty list, because there is nothing to cut.")

    if any(steps_in(claim) >= 2 for claim in candidates):
        lines.append("argument: which of your parts holds the earliest decisive step, and why, citing step numbers.")
    return "\n".join(lines)


def prover_format(candidates: list[dict]) -> dict:
    """Return the prover's answer format: reasoning, then next_part (if there is a choice), direction, cuts, argument."""
    properties = {"reasoning": {"type": "string"}}
    if len(candidates) > 1:
        properties["next_part"] = {"type": "integer", "enum": list(range(1, len(candidates) + 1))}
    properties["direction"] = {"type": "string", "enum": list(DirectionValues)}
    if any(steps_in(claim) >= 2 for claim in candidates):
        cuts = {"type": "array", "items": {"type": "integer"}}
        # Here a single claim fixes the number of cuts; with several parts the number depends on the pick.
        if len(candidates) == 1:
            cuts["minItems"] = cuts["maxItems"] = number_of_parts(candidates[0]) - 1
        properties["cuts"] = cuts
        properties["argument"] = {"type": "string"}
    return {"type": "object", "properties": properties, "required": list(properties)}


def estimator_question(level: dict, cases: list[tuple[str, tuple[int, ...]]]) -> str:
    """Write the estimator's question: the claim, the prover's parts and argument, then every combination."""
    lines = [f"The claim: steps {level['first']} to {level['last']} contain a decisive step. You gave it probability "
             f"{level['estimate']:.2f} before, so 1 minus the probability of none should be {level['estimate']:.2f} "
             "unless you say what changed.",
             "The prover cut it into these parts:"]
    lines += [f"Part {number}: steps {part['first']} to {part['last']}" for number, part in enumerate(level["parts"], start=1)]
    lines += [f"The prover's argument: {level['argument']}",
              "Give the probability of each case, adding up to 1:"]
    lines += [case_description(name, bits) for name, bits in cases]
    return "\n".join(lines)


def estimator_format(cases: list[tuple[str, tuple[int, ...]]]) -> dict:
    """Return the estimator's answer format: reasoning, then one probability per combination of parts."""
    properties = {"reasoning": {"type": "string"}, **{name: {"type": "number"} for name, _ in cases}}
    return {"type": "object", "properties": properties, "required": list(properties)}


def chosen_claim(answer: dict, candidates: list[dict]) -> dict:
    """Return the claim the prover spoke about: the only one, or the part it picked."""
    if len(candidates) == 1:
        return candidates[0]
    return candidates[answer["next_part"] - 1]


# ---------- Checks ----------
def ask_with_one_retry(role: str, model: str, system_prompt: str, steps: list[data.Step], question: str,
                       answer_format: dict, check, log: list, repair=None) -> dict:
    """Ask one role, and ask once more if the reply is not valid JSON or check() finds a problem (rule 11).
    Both calls count. If the second reply is unusable too, repair() may turn it into a usable answer (it returns None
    when it cannot); otherwise raise RunFailed."""
    problem = ""
    answer = None
    for try_number in (1, 2):
        asked = question if try_number == 1 else f"{question}\n\nYour last reply was rejected because {problem}. Answer again."
        try:
            answer = runV2.send_to_ollama(role, model, system_prompt, steps, asked, answer_format,
                                          Temperature, Seed + len(log), log, reply_limit=ReplyLimitInTokens)
        except json.JSONDecodeError:
            answer = None
            problem = "it was not valid JSON"
            continue
        problem = check(answer)
        if not problem:
            return answer

    # Here the second reply was valid JSON but broke a rule; repair() fixes what can be fixed without asking again.
    if repair is not None and answer is not None:
        repaired = repair(answer)
        if repaired is not None and not check(repaired):
            return repaired
    raise RunFailed(f"the {role} gave an unusable reply twice; the second time {problem}")


def problem_with_probability(answer: dict) -> str | None:
    """Return why the estimator's opening probability cannot be used, or None if it can."""
    probability = answer.get("probability")
    if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        return f"the probability {probability} is not a number from 0 to 1"
    return None


def problem_with_joint_probabilities(answer: dict, cases: list[tuple[str, tuple[int, ...]]]) -> str | None:
    """Return why the estimator's probabilities cannot be used, or None if they can."""
    for name, _ in cases:
        value = answer.get(name)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            return f"{name} is {value}, not a number from 0 to 1"
    total = sum(answer[name] for name, _ in cases)
    # Here the tiny extra allowance stops floating-point rounding rejecting a sum right at the edge, such as 0.95.
    if abs(total - 1) > ProbabilitySumTolerance + 1e-9:
        return f"the probabilities add up to {total:.2f}, not 1"
    return None


def problem_with_prover_answer(answer: dict, candidates: list[dict], rounds_left: int) -> str | None:
    """Return why the prover's answer cannot be used (a pick, direction or decomposition that is not allowed), or None."""
    if len(candidates) > 1 and answer.get("next_part") not in range(1, len(candidates) + 1):
        return f"next_part {answer.get('next_part')} is not a part number from 1 to {len(candidates)}"
    if answer.get("direction") not in DirectionValues:
        return f"the direction {answer.get('direction')} is not TOO_HIGH, ABOUT_RIGHT or TOO_LOW"
    claim = chosen_claim(answer, candidates)
    if steps_in(claim) >= 2:
        return problem_with_cuts(answer.get("cuts"), claim, rounds_left)
    return None


def prover_answer_with_cuts_moved(answer: dict, candidates: list[dict], rounds_left: int) -> dict | None:
    """Return the prover's answer with its cuts moved to the nearest allowed values, or None if the cuts cannot be
    moved: the pick or direction is not allowed, or the cuts are not a list of the right number of step numbers."""
    if len(candidates) > 1 and answer.get("next_part") not in range(1, len(candidates) + 1):
        return None
    if answer.get("direction") not in DirectionValues:
        return None
    claim = chosen_claim(answer, candidates)
    cuts = answer.get("cuts")
    if (steps_in(claim) < 2 or not isinstance(cuts, list) or len(cuts) != number_of_parts(claim) - 1
            or not all(isinstance(cut, int) for cut in cuts)):
        return None
    return {**answer, "cuts": nearest_allowed_cuts(claim, cuts, rounds_left), "cuts_moved_from": cuts}


def problem_with_cuts(cuts, claim: dict, rounds_left: int) -> str | None:
    """Return why a decomposition is not allowed, or None if it is: the right number of increasing cuts inside the
    claim's steps, and no part bigger than the rounds left can bring down to one step."""
    expected = number_of_parts(claim) - 1
    if not isinstance(cuts, list) or len(cuts) != expected or not all(isinstance(cut, int) for cut in cuts):
        return f"cuts {cuts} is not a list of {expected} step number{'s' if expected > 1 else ''}"
    if any(not claim["first"] <= cut < claim["last"] for cut in cuts) or cuts != sorted(set(cuts)):
        return (f"cuts {cuts} must be increasing step numbers from {claim['first']} to {claim['last'] - 1}, "
                "each the last step of a part")
    limit = largest_part(rounds_left)
    for part in parts_from_cuts(claim, cuts):
        if steps_in(part) > limit:
            return (f"the part steps {part['first']} to {part['last']} has {steps_in(part)} steps, "
                    f"more than the {limit} allowed with {rounds_left} rounds left, so the cut must be "
                    f"{allowed_cuts_text(claim, rounds_left)}")
    return None


def made_up_citations(argument: str, first: int, last: int) -> list[int]:
    """Return the step numbers the argument cites outside the claim's steps (rule 12)."""
    cited = [int(number) for number in re.findall(r"\bsteps?\s+(\d+)", argument, flags=re.IGNORECASE)]
    return sorted({number for number in cited if not first <= number <= last})


# ---------- The log ----------
def result_lines(run: data.Trajectory, depth: int, opening: dict | None, levels: list[dict],
                 verdicts: list[tuple[int, str]], answer: int | None, rewards: dict | None, failure: str) -> list[str]:
    """Write the debate's own lines for the log's result: the opening, one line per level, the judge and the rewards."""
    lines = [f"Next part chosen by: {NextPartChosenBy}",
             f"Parts per split q: {PartsPerSplit}, depth allowed: {depth} rounds, reward ratio r: {RewardRatio}",
             f"Back-ups allowed after NOT_DECISIVE: {BackUpsAfterJudgeSaysNo}, "
             f"earlier turns shown to the prover: {EarlierTurnsShownToProver}"]
    if failure:
        lines.append(f"RUN FAILED: {failure}")
    if opening:
        lines.append(f"Opening: prover claims {'TRUE' if opening['claim_bit'] else 'FALSE'}, estimator "
                     f"{opening['probability']:.2f}, drawn bit {opening['drawn_bit']}")

    for number, level in enumerate(levels, start=1):
        # Here "label inside" is for analysis only; the label never reaches a prompt (rule 13).
        label_inside = level["first"] <= run.decisive_step <= level["last"]
        line = (f"Level {number}: steps {level['first']} to {level['last']} (estimate {level['estimate']:.2f}, "
                f"chosen by {level['chosen_by']}), prover says {level['direction']}, label inside: "
                f"{'yes' if label_inside else 'no'}")
        if "parts" in level:
            parts_text = " | ".join(f"{part['first']}-{part['last']}" for part in level["parts"])
            line += f"; parts {parts_text}"
        if "cuts_moved" in level:
            line += f"; CUTS MOVED from {level['cuts_moved'][0]} to {level['cuts_moved'][1]} (prover broke the limit twice)"
        if "probabilities" in level:
            probabilities_text = ", ".join(f"{name} {value:.2f}" for name, value in level["probabilities"].items())
            # Here we check the paper's consistency: P(at least one part) should match the estimate for the claim.
            gap = (1 - level["probabilities"]["none"]) - level["estimate"]
            line += (f"; estimator {probabilities_text} (P(at least one part) minus estimate: {gap:+.2f}); "
                     f"drawn {level['drawn_case']}")
        if level.get("made_up_citations"):
            line += f"; MADE-UP CITATIONS: {level['made_up_citations']}"
        lines.append(line)
        if "verdict" in level:
            lines.append(f"Judge on step {level['first']}: {level['verdict']}")

    if len(verdicts) > 1:
        lines.append(f"BACK-UPS: {len(verdicts) - 1}")
    if answer is not None and verdicts:
        accepted = any(verdict == "DECISIVE" for _, verdict in verdicts)
        lines.append(f"Answer chosen: step {answer} "
                     + ("(the first step the judge called DECISIVE)" if accepted
                        else "(the judge called no step DECISIVE, so the first step reached)"))
    if rewards:
        round_text = ", ".join(f"{reward:+.3f}" for reward in rewards["rounds"])
        lines.append(f"Prover's rewards (paper, last way down): opening {rewards['opening']:+.3f}, levels {round_text}, "
                     f"total {rewards['total']:+.3f}")
    return lines


if __name__ == "__main__":
    # Here we borrow the start and stop scripts' functions; they live in setup/, so we add that folder to the search path.
    sys.path.insert(0, str(PROJECT_FOLDER / "setup"))
    from start_ollama_server import start_ollama_server
    from stop_ollama_server import stop_ollama_server

    # Here we put today's logs in one folder per day: runs/prover_estimator_debate/<date>/.
    log_folder = PROJECT_FOLDER / "runs" / "prover_estimator_debate" / datetime.now().strftime("%Y-%m-%d")

    started_here = start_ollama_server()
    print(f"Start: {datetime.now():%H:%M:%S}")
    print("-------Starting Prover-Estimator Debate-------")
    # Here "try ... finally" makes sure the server we started is stopped even if something below fails.
    try:
        # Here we read the pilot run from data/splits/pilot.json (run 36).
        pilot_entry = json.loads((data.SPLITS_FOLDER / "pilot.json").read_text())[0]
        pilot_run = data.read_who_and_when_file(data.WHO_AND_WHEN_FOLDER / pilot_entry["file"])

        answer = run_prover_estimator_debate(pilot_run, pilot_entry["number"], log_folder)
        print(f"Run {pilot_entry['number']}: answer = step {answer}, labelled Decisive step = {pilot_run.decisive_step}")
        print(f"Log folder: {log_folder}")
    finally:
        if started_here:
            stop_ollama_server()
    print("-------Finished Prover-Estimator Debate-------")
    print(f"End: {datetime.now():%H:%M:%S}")
