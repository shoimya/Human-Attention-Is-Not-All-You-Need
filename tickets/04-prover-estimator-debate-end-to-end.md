# 04: Prover-estimator debate end to end

**Tag:** `<build>`
**Blocked by:** 02, 03
**Status:** ready-for-agent

**What to build:** The first method and the whole pipeline around it. `run.py` with no arguments runs the Prover-estimator debate on 5 Who&When Trajectories, scores each predicted step against the Decisive step, and logs the run to `runs/<scenario>/<start time>/`.

**Method (simplest version):** each round splits the current range at the midpoint. The prover argues which half has the error; the estimator gives the probability that each half has the error; the First-error rule picks the next half. At one step, the judge checks it. Prompts are short and live in the method file.

- [ ] The log holds, per Trajectory: predicted step, hit (exact and within ±2), calls, tokens, and every round (range, both probabilities, chosen half).
- [ ] The run prints the hit rate and the average calls.
- [ ] Each of you times how long it takes to check the predicted step on these 5 cases; the times go in this ticket.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
