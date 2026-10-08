# 03: Count every model call

**Tag:** `<build>`
**Blocked by:** 01
**Status:** ready-for-agent

**What to build:** One `call()` that every method uses to ask a model something by role (debater or judge). It counts calls and tokens, so the equal-calls rule can be enforced later. Thinking mode is off.

- [ ] A test with a fake model shows the counts are correct.
- [ ] The demo asks both real models one question each and prints the answers and counts.
- [ ] `run.py --check` also confirms both models answer.
- [ ] Replies contain no thinking text.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
