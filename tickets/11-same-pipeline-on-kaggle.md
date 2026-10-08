# 11: Same pipeline on Kaggle

**Tag:** `<build>`
**Blocked by:** 04
**Status:** ready-for-agent

**What to build:** Run the same code on Kaggle (two T4 GPUs) with vLLM serving the same models. Switching from Mac to Kaggle is one setting. Each result is saved the moment it is produced, and a restarted run skips finished Trajectories (Kaggle sessions stop after 12 hours).

- [ ] On Kaggle, `run.py --check` passes and the 04 scenario runs.
- [ ] A run stopped halfway and restarted finishes without redoing work.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
