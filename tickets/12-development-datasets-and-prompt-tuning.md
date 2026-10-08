# 12: Development datasets and prompt tuning

**Tag:** `<build>`
**Blocked by:** 08, 11
**Status:** ready-for-agent

**What to build:** Loaders for AgentProcessBench and Who&When Pro (read a few runs of each first). Tune every method's prompts on these development sets only, with similar effort per method. Use AgentProcessBench's per-step labels to check each debate round, not only the final answer.

- [ ] Both loaders return Trajectories in the same shape.
- [ ] Per method: prompt versions tried and their dev hit rates, recorded in this ticket.
- [ ] Per-round accuracy of the estimator on AgentProcessBench is reported.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
