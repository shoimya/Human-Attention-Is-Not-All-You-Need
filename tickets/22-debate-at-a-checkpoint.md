# 22: Debate at a Checkpoint

**Tag:** `<build>`
**Blocked by:** 15
**Status:** ready-for-agent

**What to build:** On replayable TraceElephant runs, stop the agent at each Checkpoint (before an important action) and debate whether the action leads to failure, using only the steps so far. If the debate says yes, send it to the simulated reviewer under a fixed review budget.

- [ ] Failures caught per Review minute, compared with reviewing at random Checkpoints.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
