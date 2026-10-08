# 21: Fine-tuned debaters

**Tag:** `<build>`
**Blocked by:** 13
**Status:** ready-for-agent

**What to build:** Train small open debater models (LoRA) using debates on the development sets, with a stronger judge as the training signal (budget from 13). Compare the trained debaters with the untrained ones at matched calls.

- [ ] Trained and untrained debaters compared on the test set, in the same table form as 14.
- [ ] Follows the code standards in `CLAUDE.md`: test written first, every new file runs on its own with a demo.
