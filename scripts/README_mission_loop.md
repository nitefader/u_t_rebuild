# Mission loop — operator guide

## Mental model

- **You (operator)** write the mission once in `operator_mission.txt`.
- **Claude** is PM/architect: plans, decomposes, reviews, answers Codex's questions.
- **Codex** is the implementer: takes one prompt at a time, returns the structured report defined in `codex_report_schema.json`.
- **Orchestrator** (`mission_orchestrator.py`) drives the loop, parses Claude's directive, dispatches to Codex, writes logs, halts cleanly.

## Files

| File | Role |
|---|---|
| `operator_mission.txt` | Your input. Mission + numbered goals + ABCD done conditions + constraints. |
| `mission_orchestrator.py` | The driver. Run this. |
| `prompt.txt` | Current Codex prompt (Claude writes, Codex reads). |
| `codex_output.txt` | Latest Codex JSON report. |
| `claude_output.txt` | Latest Claude PM directive. |
| `mission_log.md` | Append-only audit trail of every cycle. |
| `mission_state.json` | Cycle count, hashes, status, halt reason. |
| `operator_questions.txt` | Where Claude pages you. If non-empty, read it. |
| `HALT.flag` | If present, loop refuses to start. Delete to resume. |

## Run

```powershell
# fresh start (clears state, log, halt flag, prior outputs)
python scripts\mission_orchestrator.py --reset --max-cycles 30

# resume after answering an operator question
Remove-Item scripts\HALT.flag, scripts\operator_questions.txt -ErrorAction SilentlyContinue
python scripts\mission_orchestrator.py --max-cycles 30
```

## Halt outcomes — what each one means

| Status | Cause | Next move |
|---|---|---|
| `mission_complete` | Claude declared done. | Read `claude_output.txt` PAYLOAD; verify, then commit. |
| `stopped_operator_question` | Claude needs you. | Read `operator_questions.txt`. Answer by editing `operator_mission.txt` (add a clarification line) or by leaving notes Claude can read in the log, then resume. |
| `stopped_codex_failed` | Codex non-zero exit. | Read `codex_output.txt` + the Codex stderr in `mission_log.md`. |
| `stopped_no_progress_codex` / `_claude` | Same output two cycles in a row. | Loop detected a stall. Inspect log; usually means the mission is ambiguous. |
| `stopped_max_cycles` | Hit the budget. | Bump `--max-cycles` and resume, or split the mission. |
| `stopped_claude_halt` | Claude hit a stop condition itself. | Reason is in `mission_state.json` and the log. |
| `stopped_unparseable_directive` | Claude returned malformed output. | Re-run; if it persists, tighten the mission text. |

## Autonomy contract (already encoded in the PM prompt)

Claude **may** make routine technical calls and answer Codex questions implied
by mission, doctrine, repo state, or prior log.

Claude **must** page you for: product direction, risk tradeoffs, destructive
changes, unclear architecture ownership, broker / live-trading safety.

If Claude can't form a concrete next Codex prompt, it halts. No infinite loops.

## Tomorrow-morning recovery

Loop is idempotent — `mission_state.json` carries cycle count and hashes.
Re-running without `--reset` resumes from where it stopped. The mission hash
is checked: if you edit `operator_mission.txt`, progress markers reset but the
log is preserved.


## How you answer Claude now

When it stops, open:

notepad scripts\operator_questions.txt

Add your answer under:

ANSWER:

Then run:

.\run-agents.ps1

Do not delete operator_questions.txt anymore. The orchestrator needs it so Claude can read your answer.