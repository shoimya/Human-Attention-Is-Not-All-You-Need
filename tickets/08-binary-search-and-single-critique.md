# 08: Binary search and single critique, with matched calls

**Tag:** `<build>`
**Blocked by:** 07
**Status:** ready-for-agent

**What to build:** The last two methods, both using the matched-call rule from 07, each with its own file in `methods/`, its own `run_<method>(json_file)` in `run.py`, and its own log folder in `runs/` in the same layout as 04. Binary search: one model halves the Trajectory each round with no opponent. Single critique: one model proposes a step, another critiques it once, the judge decides.

- [ ] Both log the same fields as 07, with matched calls.
- [ ] The run prints all five methods side by side.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
