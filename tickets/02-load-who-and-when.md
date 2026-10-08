# 02: Load Who&When and read it

**Tag:** `<build>`
**Blocked by:** 01
**Status:** ready-for-agent

**What to build:** Load the 58 Who&When Hand-Crafted failures as Trajectories (task question, steps, Decisive step, responsible agent) and print a short summary from `run.py --check`. Before writing the loader, read 5 failed runs yourselves.

- [ ] The loader returns 58 Trajectories; `run.py --check` prints their count and length (median and max steps).
- [ ] Answered in this ticket: does the Decisive step count from 0 or from 1?
- [ ] For the 5 runs read by hand: notes on what a step looks like, whether the label looks right, and the minutes it took to find the mistake.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
