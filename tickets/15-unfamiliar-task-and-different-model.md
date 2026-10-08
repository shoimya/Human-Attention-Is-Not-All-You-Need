# 15: Unfamiliar-task test and different-model test

**Tag:** `<build>`
**Blocked by:** 13
**Status:** ready-for-agent

**What to build:** Two extra runs with frozen prompts. (1) Loaders and runs for TraceElephant SWE-Agent and AgentProcessBench τ², to test an unfamiliar task. (2) Debates with Gemma as one debater, compared with Qwen against Qwen.

- [ ] Both new loaders return Trajectories in the same shape.
- [ ] Summary tables for both tests, in the same form as 14.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
