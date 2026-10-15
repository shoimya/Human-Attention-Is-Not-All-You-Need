# 03: Ask a model, count every call, and log it

**Tag:** `<build>`
**Blocked by:** 01
**Status:** done

**What to build:** the shared parts every method uses to talk to the models, all in `run.py` (agreed with the owner, 2026-10-08). Every file runs with the play button.

1. **`ask_model(role, model, system_prompt, prompt, log)`**: the **only** way any part of the project asks a model something.
   - **Each method file maps its own roles to models** (owner's decision, 2026-10-08), for example in the prover-estimator file: prover and estimator use `settings.DEBATER_MODEL` (`qwen3.5:9b`), the judge uses `settings.JUDGE_MODEL` (`qwen3.5:2b`). `settings.py` only names the models. The method passes the role and its model to `ask_model()`. Same model, different system prompt = different role.
   - Sends the system prompt and the prompt to this project's Ollama server (port 11500), with thinking mode off, and returns the reply. Python's built-in tools can do this, so no new library is needed.
   - Adds one entry to the question's `log` list: role, model, the **full** prompt, the **full** reply, tokens read, tokens written, seconds taken.
2. **What counts as a call (the same rule for every method):** one prompt sent to one model and its one reply = **1 call**, whatever the role, the prompt length or the reply length. A retry (for example after a broken reply) is another call. Tokens are counted separately. The TA's rule compares calls: every baseline gets as many calls as the debate used on the same run.
3. **`write_log(...)`**: one function that writes one question's log, `run_<number>.md`, into `runs/<method>/<start time>/` once the question is finished (so a crash loses at most the question in progress):
   - **Top:** run number, file name, the question, and **every role's model and full system prompt** (each system prompt written once, because it stays the same for the whole question).
   - **Middle:** every interaction and every method note, in order: round, role, full prompt sent, full reply, tokens and time.
   - **Bottom:** the method's answer, the labelled Decisive step, whether it is right (exactly and within ±2 steps), total calls and tokens.
4. **Method notes:** a method adds its own lines to the same `log` list between calls (for example "Round 2: steps 0–45; estimator says left 0.7, right 0.3; go left"). This is how each method logs what matters for it, while every log keeps the same layout.

**Not in this ticket:** the debate itself, `run_<debate>()` and filling in `write_results_file()` (ticket 04). `run.py --check` was dropped: `run.py` is for the pilot and later runs.

- [x] `ask_model()` counts one call per prompt and records the full prompt, reply, tokens and time. Tested with a fake model, so the tests need no server.
- [x] `write_log()` writes a log with the system prompts at the top, every interaction and note in order, and the result at the bottom. Tested in a temporary folder; tests write nothing to `runs/`.
- [x] Pressing play on `run.py` asks the prover and the judge one question each and prints the replies, the models used and the call count. It starts the server if needed and stops it again only if it started it.
- [x] Replies contain no thinking text.
- [x] The model reads the whole prompt (context window), and a prompt that fills the window is marked in the log.
- [x] Follows the code standards in `CLAUDE.md`: test written first, every file runs with the play button.

## Outcome

Done 2026-10-08, test-first.

**`run.py`**
- `ask_model(role, model, system_prompt, prompt, log)`: the only way to ask a model; returns the reply and records the whole call (role, model, system prompt, full prompt, full reply, tokens read and written, seconds, and `prompt_may_be_cut`).
- `send_to_ollama(model, system_prompt, prompt)`: the one part that talks to the server (`/api/chat`, `stream` off, `think` off, `num_ctx` = `settings.OLLAMA_CONTEXT_WINDOW`). The tests replace only this function.
- `add_note(log, note)`: a method's own note; not a call.
- `count_calls(log)`: calls, tokens read, tokens written for one question.
- `write_log(log, run_folder, method_name, run_number, question, predicted_step)`: writes `run_<number>.md` (system prompts once at the top; calls and notes in order, long texts fenced with ```` so replies cannot break the layout; a **PROMPT MAY HAVE BEEN CUT** warning on any call that filled the context window; result with exact and ±2 hits and totals). `HIT_TOLERANCE_IN_STEPS = 2`.
- `write_results_file(...)`: still a skeleton (ticket 04).
- Main block: starts the server only if it is not running, asks the prover and the judge one question each, prints replies, models, times and counts, and in a `try ... finally` stops the server only if it started it.

**`settings.py`**: `OLLAMA_CONTEXT_WINDOW = 65536` (owner agreed 2026-10-08).

**`tests/test_3_run.py`**: 4 tests, all passing, no server needed: the whole call is recorded; two questions plus a note = 2 calls with the right token totals; the log layout and result (prediction 11 vs label 9 = not exact, within ±2); a prompt that fills the context window is marked and the log warns once.

**Checked with real models:** the server stopped → `run.py` started it, both models answered, it stopped it; the server already running → `run.py` used it and left it running. Ollama's raw answer has no thinking text. Nothing was written to `runs/`.

**Found and fixed: prompts were being cut.** Ollama reads only about 2,000 tokens of a prompt by default and silently drops the rest (a 5,700-token prompt was read as 2,050 tokens). With `num_ctx` set, the whole prompt is read. Measured on the M4 (16 GB): 32,768 tokens fits 45 of 58 runs but not the pilot; **65,536 fits 57 of 58 including the pilot** (run 36, about 35,000 tokens; read in full as 37,904 tokens); one call on the full pilot run took **237 s** and used 7.9 GB of GPU memory, leaving the Mac close to its memory limit; the largest run (about 87,000 tokens) needs about 98,000 tokens, so it is for Kaggle (ticket 11). Real token counts are about 12% higher than characters ÷ 4 (about 3.6 characters per token).

**For ticket 04:** if every debate call reads the whole pilot run, one debate (about 15 calls) takes about an hour on the Mac. Worth deciding in ticket 04 whether each round sends only the steps in the current half.

**Gotcha:** VS Code shows "Import stop_ollama_server could not be resolved" in `run.py`; it is only the editor, which does not see the search-path line that runs first. Python finds it.
