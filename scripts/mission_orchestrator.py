"""
Mission-driven Claude/Codex orchestrator.

Operator writes a mission in operator_mission.txt (numbered goals + ABCD done
conditions). Claude (PM/architect/reviewer) plans and drives Codex one prompt
at a time. Operator is paged only on stop conditions.

Cycle:
  1. If HALT.flag exists, stop.
  2. Read mission + log + last codex output.
  3. Run Claude in PM mode -> structured DIRECTIVE.
  4. Dispatch:
        NEXT_CODEX_PROMPT  -> write prompt.txt, run codex, append log, continue
        OPERATOR_QUESTION  -> write operator_questions.txt, halt
        MISSION_COMPLETE   -> halt (success)
        HALT               -> halt (reason recorded)
  5. Stop also on: codex non-zero exit, no-progress hash repeats, max cycles.

Operator resumes by clearing operator_questions.txt + deleting HALT.flag, or
by editing operator_mission.txt and re-running.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(r"C:\Users\potij\Projects\Ultimate_Trading_OS_Rebuild")
SCRIPTS_DIR = REPO_ROOT / "scripts"

MISSION_FILE = SCRIPTS_DIR / "operator_mission.txt"
PROMPT_FILE = SCRIPTS_DIR / "prompt.txt"
CODEX_OUTPUT_FILE = SCRIPTS_DIR / "codex_output.txt"
CLAUDE_OUTPUT_FILE = SCRIPTS_DIR / "claude_output.txt"
OPERATOR_QUESTIONS_FILE = SCRIPTS_DIR / "operator_questions.txt"
STATE_FILE = SCRIPTS_DIR / "mission_state.json"
LOG_FILE = SCRIPTS_DIR / "mission_log.md"
HALT_FILE = SCRIPTS_DIR / "HALT.flag"
CODEX_SCHEMA_FILE = SCRIPTS_DIR / "codex_report_schema.json"

CODEX_TIMEOUT_SECONDS = 1800
CLAUDE_TIMEOUT_SECONDS = 900

LOG_TAIL_CYCLES = 6  # how many prior cycles to feed Claude each turn


def _resolve_cli(name: str) -> str:
    """Resolve a CLI name to its full path (handles Windows .cmd/.bat shims)."""
    for candidate in (name, f"{name}.cmd", f"{name}.exe", f"{name}.bat"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError(
        f"Could not find '{name}' on PATH. Tried: {name}, {name}.cmd, "
        f"{name}.exe, {name}.bat. Install it or fix PATH."
    )


CLAUDE_BIN = _resolve_cli("claude")
CODEX_BIN = _resolve_cli("codex")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "mission_hash": None,
            "cycle": 0,
            "status": "new",
            "last_codex_hash": None,
            "last_claude_hash": None,
            "halt_reason": None,
            "updated_at": now(),
        }
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["updated_at"] = now()
    STATE_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")


def append_log(section_title: str, body: str) -> None:
    ts = now()
    block = f"\n## {ts} {section_title}\n\n{body.strip()}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fp:
        fp.write(block)


def read_log_tail(n_cycles: int) -> str:
    if not LOG_FILE.exists():
        return "(empty log)"
    text = LOG_FILE.read_text(encoding="utf-8")
    # Each cycle writes 2 sections (CLAUDE + CODEX). Take last 2*n_cycles sections.
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    sections = [s for s in sections if s.strip()]
    keep = sections[-(2 * n_cycles):]
    return "".join(keep).strip() or "(empty log)"


def run_process(
    command: list[str],
    timeout_seconds: int,
    stdin_text: str | None = None,
) -> tuple[int, str]:
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        stdout, stderr = process.communicate(input=stdin_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return 124, f"TIMEOUT\n{stderr}"

    return process.returncode, stdout if stdout else stderr


def run_codex(prompt: str) -> tuple[int, str]:
    # Pass prompt via stdin to avoid Windows 8191-char argv limit on .CMD shims.
    command = [
        CODEX_BIN,
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        str(REPO_ROOT),
        "--color",
        "never",
        "--output-schema",
        str(CODEX_SCHEMA_FILE),
        "-",  # read prompt from stdin
    ]
    return run_process(command, CODEX_TIMEOUT_SECONDS, stdin_text=prompt)


def run_claude(prompt: str) -> tuple[int, str]:
    # `claude -p` with no positional prompt reads from stdin — bypasses the
    # Windows .CMD-shim 8191-char argv limit.
    return run_process(
        [CLAUDE_BIN, "-p", "--dangerously-skip-permissions"], CLAUDE_TIMEOUT_SECONDS, stdin_text=prompt
    )


def format_codex_output(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2)
    except Exception:
        return raw.strip()


def build_pm_prompt(mission_text: str, log_tail: str, last_codex: str | None) -> str:
    last_codex_block = (
        f"LAST_CODEX_OUTPUT (latest cycle, JSON):\n{last_codex}\n"
        if last_codex
        else "LAST_CODEX_OUTPUT: (none yet — this is the first cycle)\n"
    )

    return f"""
You are Claude in PM/architect mode driving an autonomous engineering loop for
the Ultimate Trader project. Your peer is Codex (the implementer). You issue
one Codex prompt per cycle, observe Codex's structured output, then decide the
next move.

OPERATOR MISSION (frozen — do not reinterpret):
---
{mission_text.strip()}
---

RECENT CYCLE LOG (last {LOG_TAIL_CYCLES} cycles, oldest first):
---
{log_tail}
---

{last_codex_block}

YOUR JOB:
- Decompose the mission into the minimum sequence of Codex tasks.
- If Codex's last output has a non-empty QUESTIONS field, decide whether you
  can answer it from the mission, repo doctrine, prior log, or general
  architecture knowledge. If yes, fold the answer into the next Codex prompt.
  If no — and only if no — escalate to the operator.
- If Codex's last output has BLOCKERS or reports FAIL, do NOT issue a repair
  prompt unless the fix is obvious and safe; otherwise HALT or escalate.
- Never expand scope beyond the mission.
- Never approve destructive ops, broker/live-trading changes, or unclear
  architecture ownership without operator sign-off.

OUTPUT FORMAT (strict — orchestrator parses this):
STATUS: <one line of mission progress>
STEP: <numbered step you are currently driving, e.g. "2 of 4">
DIRECTIVE: NEXT_CODEX_PROMPT | OPERATOR_QUESTION | MISSION_COMPLETE | HALT
REASON: <one short sentence>
PAYLOAD:
<For NEXT_CODEX_PROMPT: the literal Codex prompt, ready to send.>
<For OPERATOR_QUESTION: the question(s) for Nanyel, plus what you need to
 unblock.>
<For MISSION_COMPLETE: a short summary of what shipped and where the artifacts
 live.>
<For HALT: the reason and what the operator should inspect.>
""".strip()


# ---- Directive parsing -------------------------------------------------------

DIRECTIVES = ("NEXT_CODEX_PROMPT", "OPERATOR_QUESTION", "MISSION_COMPLETE", "HALT")


def parse_claude_directive(text: str) -> dict:
    out = {"status": "", "step": "", "directive": "", "reason": "", "payload": ""}

    def grab(label: str) -> str:
        m = re.search(rf"^{label}:\s*(.*)$", text, flags=re.MULTILINE)
        return m.group(1).strip() if m else ""

    out["status"] = grab("STATUS")
    out["step"] = grab("STEP")
    out["directive"] = grab("DIRECTIVE").upper()
    out["reason"] = grab("REASON")

    payload_match = re.search(r"^PAYLOAD:\s*\n(.*)\Z", text, flags=re.MULTILINE | re.DOTALL)
    if payload_match:
        out["payload"] = payload_match.group(1).strip()

    if out["directive"] not in DIRECTIVES:
        out["directive"] = ""

    return out


# ---- Main loop ---------------------------------------------------------------


def halt(state: dict, reason: str, code: str) -> None:
    state["status"] = code
    state["halt_reason"] = reason
    save_state(state)
    HALT_FILE.write_text(f"{now()} {code}\n{reason}\n", encoding="utf-8")
    print(f"\nHALT: {code}")
    print(reason)


def run_one_cycle(cycle: int, state: dict, mission_text: str) -> bool:
    print(f"\n=== CYCLE {cycle} ===")

    if HALT_FILE.exists():
        print("HALT.flag present — stopping.")
        return False

    log_tail = read_log_tail(LOG_TAIL_CYCLES)
    last_codex = (
        CODEX_OUTPUT_FILE.read_text(encoding="utf-8").strip()
        if CODEX_OUTPUT_FILE.exists() and state.get("last_codex_hash")
        else None
    )

    pm_prompt = build_pm_prompt(mission_text, log_tail, last_codex)

    print("--- Claude PM ---")
    code, claude_raw = run_claude(pm_prompt)
    claude_out = claude_raw.strip()
    CLAUDE_OUTPUT_FILE.write_text(claude_out, encoding="utf-8")

    if code != 0:
        halt(state, f"Claude returned exit code {code}.", "claude_failed")
        return False

    claude_hash = sha256_text(claude_out)
    if claude_hash == state.get("last_claude_hash"):
        halt(state, "Claude output identical to previous cycle — no progress.",
             "stopped_no_progress_claude")
        return False
    state["last_claude_hash"] = claude_hash

    parsed = parse_claude_directive(claude_out)
    print(f"DIRECTIVE: {parsed['directive']}  STEP: {parsed['step']}")
    print(f"REASON: {parsed['reason']}")

    append_log(
        f"CLAUDE cycle {cycle} :: {parsed['directive'] or 'UNPARSED'}",
        claude_out,
    )

    if not parsed["directive"]:
        halt(state, "Claude output did not contain a parseable DIRECTIVE.",
             "stopped_unparseable_directive")
        return False

    if parsed["directive"] == "MISSION_COMPLETE":
        state["status"] = "mission_complete"
        save_state(state)
        print("\nMISSION COMPLETE")
        print(parsed["payload"])
        return False

    if parsed["directive"] == "OPERATOR_QUESTION":
        OPERATOR_QUESTIONS_FILE.write_text(
            f"# Operator question — cycle {cycle} {now()}\n\n"
            f"REASON: {parsed['reason']}\n\n"
            f"{parsed['payload']}\n",
            encoding="utf-8",
        )
        halt(state, "Claude paged the operator. See operator_questions.txt.",
             "stopped_operator_question")
        return False

    if parsed["directive"] == "HALT":
        halt(state, parsed["reason"] or "Claude requested HALT.",
             "stopped_claude_halt")
        return False

    # NEXT_CODEX_PROMPT
    if not parsed["payload"].strip():
        halt(state, "Claude said NEXT_CODEX_PROMPT but PAYLOAD was empty.",
             "stopped_empty_codex_prompt")
        return False

    PROMPT_FILE.write_text(parsed["payload"], encoding="utf-8")

    print("--- Codex ---")
    code, codex_raw = run_codex(parsed["payload"])
    formatted = format_codex_output(codex_raw)
    CODEX_OUTPUT_FILE.write_text(formatted, encoding="utf-8")

    append_log(f"CODEX cycle {cycle} :: exit={code}", formatted)

    if code != 0:
        halt(state, f"Codex returned exit code {code}. See codex_output.txt.",
             "stopped_codex_failed")
        return False

    codex_hash = sha256_text(formatted)
    if codex_hash == state.get("last_codex_hash"):
        halt(state, "Codex output identical to previous cycle — no progress.",
             "stopped_no_progress_codex")
        return False
    state["last_codex_hash"] = codex_hash

    state["cycle"] = cycle
    state["status"] = "cycle_complete"
    save_state(state)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission-driven Claude/Codex orchestrator")
    parser.add_argument("--max-cycles", type=int, default=20)
    parser.add_argument("--reset", action="store_true",
                        help="Clear state, log, HALT.flag, operator questions before running.")
    args = parser.parse_args()

    if args.reset:
        for f in (STATE_FILE, LOG_FILE, HALT_FILE, OPERATOR_QUESTIONS_FILE,
                  CODEX_OUTPUT_FILE, CLAUDE_OUTPUT_FILE, PROMPT_FILE):
            if f.exists():
                f.unlink()

    if not MISSION_FILE.exists():
        print(f"Missing mission file: {MISSION_FILE}")
        sys.exit(1)

    mission_text = MISSION_FILE.read_text(encoding="utf-8").strip()
    if not mission_text or "<Describe what I want done>" in mission_text:
        print("operator_mission.txt is empty or still has the placeholder. Fill it in first.")
        sys.exit(1)

    state = load_state()
    mission_hash = sha256_text(mission_text)
    if state.get("mission_hash") != mission_hash:
        # New mission -> reset progress markers but keep log for history.
        state["mission_hash"] = mission_hash
        state["cycle"] = 0
        state["last_codex_hash"] = None
        state["last_claude_hash"] = None
        state["halt_reason"] = None
        state["status"] = "new_mission"
        save_state(state)
        append_log("MISSION", mission_text)

    print("Mission orchestrator starting")
    print(f"Repo: {REPO_ROOT}")
    print(f"Max cycles: {args.max_cycles}")
    print(f"Resuming from cycle: {state.get('cycle', 0)}")

    start = state.get("cycle", 0) + 1
    end = start + args.max_cycles

    for cycle in range(start, end):
        if not run_one_cycle(cycle, state, mission_text):
            break
    else:
        halt(state, f"Reached max cycles ({args.max_cycles}). Mission still in flight.",
             "stopped_max_cycles")

    final = load_state()
    print(f"\nFinal status: {final.get('status')}")
    if final.get("halt_reason"):
        print(f"Halt reason: {final['halt_reason']}")


if __name__ == "__main__":
    main()
