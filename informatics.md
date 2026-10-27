These descriptions are the working plan and may change as the methods are built.

## 1. Prover-estimator debate

- **Who:** a prover and an estimator (same model, different instructions), and a judge (a smaller model).
- **What happens:** each round, the prover splits the steps in half and argues which half has the error. The estimator gives each half a probability. We keep the more likely half, and repeat until one step is left.
- **Answer:** the judge checks that last step.
- **Why it is here:** this is our main method.

### How we differ from the original paper

Brown-Cohen et al., "Avoiding Obfuscation with Prover-Estimator Debate" (arXiv 2506.13609), describes the method in theory only, with no experiments or code. We change three things:

1. **We do not train the models.** In the paper, the prover earns points when the estimator's probabilities do not add up, and these points are used to train both models. Our models are only prompted, so the points change nothing. We still log whether the probabilities add up.
2. **The prover does not choose where to go next.** In the paper, the prover picks which smaller claim to dig into, to catch the estimator's mistakes. We want the run's mistake instead, so we use the **first-error rule**: keep the half the estimator thinks has the error. This is our modification and must be reported as one.
3. **Every run already failed.** The paper starts by asking whether the claim is true. In our data the opening claim ("this run has no error") is always false.

What we keep from the paper: the prover splits the claim and argues, the estimator gives probabilities for the smaller claims, the claim gets smaller every round, and at the end the judge checks one small claim without reading the debate.

### Rules

1. **Input:** one failed run and its task question. The pilot run (run 36) comes first.
2. **The claim:** "steps *a* to *b* contain no error". It starts with the whole run.
3. **Roles and models:** the prover and the estimator use the same debater model (`qwen3.5:9b`) with different instructions. The judge uses the smaller `qwen3.5:2b`. Each role keeps the same instructions for the whole run.
4. **Two parts per round:** each round splits the current steps into two halves at the middle.
5. **The prover's turn:** it says which half it thinks has the error and argues why, citing step numbers inside the current range.
6. **The estimator's turn:** after reading the prover's argument, it gives a probability for each of four cases: no error, error only in the left half, error only in the right half, error in both halves. The four must add up to 1.
7. **First-error rule:** go into the left half if the chance that it has an error is above 0.5 ("left only" plus "both"), otherwise go into the right half. This always prefers the earliest error, which is what the Decisive step is.
8. **Stop** when one step is left. That takes about log₂(number of steps) rounds, for example 7 rounds for run 36's 91 steps.
9. **The judge** sees only the question and that one step, not the debate, and says whether it is the mistake.
10. **The answer** is the last step left. The judge's yes or no is recorded with it.
11. **Fixed answer format:** the prover and the estimator answer in a fixed format (JSON), so the code can read their answers. A broken answer gets one retry, which counts as a call. If it breaks again, the run is marked as failed and recorded.
12. **Citation check:** the code checks every step number the prover cites. A number outside the range, or a step that does not exist, is logged as a made-up citation.
13. **No hindsight:** the label and the annotators' reason are never put in any prompt.
14. **Log each round:** the range, where it was split, the prover's half, the estimator's four probabilities, whether they add up with the last round's, the half kept, and (for analysis only) whether the labelled step is still inside the range.
15. **Fixed randomness:** the temperature and seed are fixed project settings, the same for every method.

### Still to decide

- **A. What each call sees.** The whole run (about 4 minutes per call on the pilot), only steps 0 to the end of the current range (later steps cannot change whether an earlier step was wrong), or only the current range. Suggested: steps 0 to the end of the current range.
- **B. Where to split.** Always the middle, or the prover chooses (closer to the paper). Suggested: the middle, for the first version.
- **C. "Too high / right / too low".** In the paper, the prover first says whether the estimator's last probability was too high, right or too low. Keep it (logged, used for nothing) or drop it. Suggested: keep it, logged only.
- **D. The opening claim.** Skip it, because every run failed (saves 2 calls), or ask it anyway (closer to the paper). Suggested: skip it, and say so in the paper.
- **E. If the judge says "no, this step is fine".** Still answer that step, or go back up a round. Suggested: still answer that step, for the first version.

## 2. Standard debate

- **Who:** two debaters and a judge.
- **What happens:** debater A names the step it blames and explains why. Debater B agrees or argues for a different step. They take turns for a fixed number of rounds.
- **Answer:** the judge reads the debate and names one step.
- **Why it is here:** it shows whether splitting the run in half matters, or whether any debate is enough.

## 3. One-shot

- **Who:** one model.
- **What happens:** it reads the whole run and names one step. It does this as many times as the debate made calls, and stops early if its answer never changes.
- **Answer:** the step it named most often.
- **Why it is here:** it is the simplest method. A debate must beat it to be worth the cost.

### Rules

1. **Input:** one failed run, meaning all its steps marked by `format_steps_as_text()`. The run's task question is already step 0 in all 58 runs, so it is not added again. The pilot run (run 36) comes first.
2. **Model:** a role uses the debater model (`qwen3.5:9b`) unless it is a judge. One-shot has no judge, so it uses the debater model.
3. **The system prompt and the question:** both are variables at the top of the method's script: `SystemPrompt` and a question variable. The question asks for the first step where the run went wrong (the Decisive step).
4. **Fixed answer format:** `{"step": <number>, "reason": "<one sentence>"}`. There is no retry. A reply that isn't valid JSON, or that names a step outside the run, still counts as a call but gets no vote, and the log says why.
5. **Number of calls:** `DefaultNoOfCalls = 10`, set in the script. Once the experiments show the debate's average number of calls, that average replaces it.
6. **Temperature and seed:** both are constants in the method's script for now, kept fixed and changed later when needed.
7. **Early stop:**
   - **Rule:** after half of `DefaultNoOfCalls` (5 of 10), if every one of those calls named the same step, stop and return that step. A call with no valid answer breaks the streak. Otherwise, make the rest of the calls. Every step a call returns is logged.
   - **Why:** to avoid wasting time and compute, while still giving the model and the method enough tries.
   - **Scope:** only one-shot uses it for now. We want to save calls wherever we can, so other methods, single critique for example, may get it later once they show they need fewer calls.
8. **Answer:** the step named most often. If there's a tie, the earliest step wins.
9. **No hindsight:** the label and the annotators' reason never go into any prompt.
10. **Log:** one folder per day and one file per run, with the time in the file name, so running the same test twice keeps both. For example: `runs/one_shot/2026-10-08/run_36_23-10-05.md`. Each log shows every call (step and reason), the final answer, the calls allowed and the calls actually used, and a warning if a prompt filled the context window.

## 4. Single critique

- **Who:** a proposer and a critic (the same debater model, different instructions), and a judge (the smaller model).
- **What happens:** the proposer names a step. The critic checks that choice once: it agrees, or it disagrees and names its own step. Nobody replies to the critic.
- **Answer:** if the critic agrees, the proposer's step. If not, the judge picks the proposer's step or the critic's. Over several rounds, the step chosen most often.
- **Why it is here:** Elasky et al. (2026) found that one critique gives most of the benefit of a full debate.

### How we differ from Elasky et al.

In Elasky et al. (arXiv 2605.27483), the critic only says whether the proposer's answer is right, and the judge rules it correct or incorrect. That gives no step when the judge says "incorrect", and we must always answer with a step. We change two things, and must report both:

1. **The critic names a step when it disagrees,** with evidence from the run.
2. **The judge chooses between the two steps** (PROPOSER or CRITIC) instead of ruling the proposer's step correct or incorrect.

How it still differs from standard debate (section 2): there is only one exchange and no reply to the critic, the judge must choose one of the two named steps (it cannot name a third), and the judge is not asked at all when the critic agrees.

### Rules

1. **Input:** one failed run, meaning all its steps marked by `format_steps_as_text()`. The task question is already step 0. The pilot run (run 36) comes first; the script's main block runs `data/splits/pilot.json`.
2. **Roles and models:** the proposer and the critic use the debater model (`qwen3.5:9b`); the judge uses the judge model (`qwen3.5:2b`). Each role keeps the same system prompt for the whole run.
3. **Prompts, questions and formats:** variables at the top of the script: `ProposerPrompt`, `ProposerQuestion`, `ProposerFormat`, `CriticPrompt`, `CriticFormat`, `JudgePrompt`, `JudgeFormat`. The critic's and the judge's questions are built by `critic_question()` and `judge_question()`.
4. **What each role sees:** every role reads the whole run. The critic also gets the proposer's step and reason, not its reasoning. The judge also gets the proposer's step and reason, and the critic's step and evidence, not the critic's reasoning.
5. **Fixed answer formats** (fields in this order, so each role reasons before it answers):
   - proposer: `reasoning`, `step`, `reason` (one sentence)
   - critic: `reasoning`, `stance` (`AGREE` or `DISAGREE`), `step` (its own step if it disagrees, the claimed step if it agrees), `evidence` (two to four sentences)
   - judge: `reasoning`, `winner` (`PROPOSER` or `CRITIC`), `reason` (one sentence), `confidence` (0 to 1)
6. **One round:** the proposer answers, then the critic.
   - The critic agrees: the round's step is the proposer's step, and the judge is not asked (2 calls).
   - The critic disagrees: the judge picks, and the round's step is the winner's step (3 calls).
7. **No retry:** a reply that isn't valid JSON, or a proposer's or disagreeing critic's step outside the run, ends the round with no step. The call still counts, and the log says why.
8. **Number of rounds:** `NumberOfRounds = 3`, so 6 to 9 calls per run. Once the debate's average number of calls is known, set the rounds to match it. There is no early stop.
9. **Temperature, seed and thinking:** `Temperature = 0.7`, base `Seed = 41` (the same as one-shot). Round *r* uses seed 41 + *r* for all its calls. Thinking is set once for every method by `THINKING_ON` in `runV2.py` (off for now).
10. **Answer:** the step chosen most often over the rounds that gave a step. If there's a tie, the earliest step wins (the same vote as one-shot). If no round gave a step, there is no answer.
11. **No hindsight:** the label and the annotators' reason never go into any prompt.
12. **Log:** `runs/single_critique/<date>/run_<number>_<time>.md`. It shows each role's system prompt once, then every call; each call's heading shows its seed, which tells you the round. The result lists the calls used and one line per round: the chosen step, the proposer's and the critic's steps, and the judge's choice and confidence. The confidence is logged but not used.

## 5. Binary search

- **Who:** one model.
- **What happens:** each round, it splits the steps in half and picks the half with the error. It repeats until one step is left. It answers each round several times, and the majority wins.
- **Answer:** the last step left.
- **Why it is here:** it is the prover-estimator debate without the debate, so it shows whether the arguing adds anything.
