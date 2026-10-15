# 23: Redo notebook

**Tag:** `<think>`
**Blocked by:** 02
**Status:** ready-for-team (later; owner's decision, 2026-10-08)

**What to decide:** how to simplify `data_analysis.ipynb`, the Kaggle data analysis notebook from ticket 02. It currently has 9 sections and 5 figures. Points to discuss:
- Which sections and figures the midterm report actually needs, and which can go.
- Whether the setup cell (clone from GitHub on Kaggle, or use the Mac folder) can be shorter.
- Whether helper code (the per-run table, the colours, saving figures) should move out of the notebook, for example into `data.py`.
- Whether `figures/` is pushed to GitHub or created only on Kaggle.

- [ ] Decisions written at the bottom of this ticket under `## Decision`.
- [ ] A `<build>` ticket for the changes, or the changes listed here if they are small.
