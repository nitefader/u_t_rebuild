"""
Mission-driven Claude/Codex orchestrator with operator email paging.

Operator flow:
  1. Claude emits OPERATOR_QUESTION.
  2. This script writes scripts/operator_questions.txt.
  3. This script emails the same question to the operator.
  4. This script writes HALT.flag and stops.
  5. Operator answers under ANSWER: in scripts/operator_questions.txt.
  6. Operator reruns the loop.
  7. Claude receives the answer and continues.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
from datetime import datetime
from email.message import EmailMessage
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
LOG_TAIL_CYCLES = 6

CODEX_DANGEROUS_FLAG = "--dangerously-bypass-approvals-and-sandbox"
CLAUDE_DANGEROUS_FLAG = "--dangerously-skip-permissions"


# ---------------------------------------------------------------------------
# CLI resolution
# ---------------------------------------------------------------------------

def _resolve_cli(name: str) -> str:
    for candidate in (name, f"{name}.cmd", f"{name}.exe", f"{name}.bat"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError(
        f"Could not find '{name}' on PATH. Tried {name}, {name}.cmd, "
        f"{name}.exe, {name}.bat."
    )


CLAUDE_BIN = _resolve_cli("claude")
CODEX_BIN = _resolve_cli("codex")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def unlink_if_exists(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError as exc:
        raise RuntimeError(f"Cannot delete {path}: permission denied") from exc


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
    block = f"\n## {now()} {section_title}\n\n{body.strip()}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fp:
        fp.write(block)


def read_log_tail(n_cycles: int) -> str:
    if not LOG_FILE.exists():
        return "(empty log)"

    text = LOG_FILE.read_text(encoding="utf-8")
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    sections = [section for section in sections if section.strip()]
    keep = sections[-(2 * n_cycles):]

    return "".join(keep).strip() or "(empty log)"


# ---------------------------------------------------------------------------
# Operator question and answer handling
# ---------------------------------------------------------------------------

def read_operator_question_context() -> str:
    if not OPERATOR_QUESTIONS_FILE.exists():
        return ""

    text = OPERATOR_QUESTIONS_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return ""

    return f"""
OPERATOR QUESTION / ANSWER CONTEXT:
---
{text}
---

If this file contains an ANSWER section from Nanyel, treat that answer as
authoritative operator guidance. Use it to continue the mission. Do not ask the
same question again unless the answer is ambiguous or creates a new safety issue.
""".strip()


def operator_answer_present() -> bool:
    if not OPERATOR_QUESTIONS_FILE.exists():
        return False

    text = OPERATOR_QUESTIONS_FILE.read_text(encoding="utf-8")
    match = re.search(r"(?im)^ANSWER\s*:\s*(.*)", text)

    if not match:
        return False

    after_answer = text[match.end():].strip()
    inline_answer = match.group(1).strip()

    return bool(inline_answer or after_answer)


def clear_halt_only() -> None:
    unlink_if_exists(HALT_FILE)


def discard_operator_question() -> None:
    unlink_if_exists(OPERATOR_QUESTIONS_FILE)


def write_operator_question(cycle: int, reason: str, payload: str) -> str:
    body = f"""# Operator question - cycle {cycle} {now()}

REASON: {reason}

{payload}

ANSWER:
"""
    OPERATOR_QUESTIONS_FILE.write_text(body, encoding="utf-8")
    return body


def consume_operator_question_if_safe(parsed_directive: str) -> None:
    if not OPERATOR_QUESTIONS_FILE.exists():
        return

    if not operator_answer_present():
        return

    if parsed_directive == "NEXT_CODEX_PROMPT":
        append_log(
            "OPERATOR ANSWER CONSUMED",
            OPERATOR_QUESTIONS_FILE.read_text(encoding="utf-8"),
        )
        discard_operator_question()


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------

def email_notifications_enabled() -> bool:
    required = [
        "UT_NOTIFY_EMAIL_FROM",
        "UT_NOTIFY_EMAIL_TO",
        "UT_NOTIFY_EMAIL_APP_PASSWORD",
    ]
    return all(os.environ.get(name) for name in required)


def notify_operator_email(subject: str, body: str) -> None:
    """
    Sends email through Gmail SMTP by default.

    Required environment variables:
      UT_NOTIFY_EMAIL_FROM
      UT_NOTIFY_EMAIL_TO
      UT_NOTIFY_EMAIL_APP_PASSWORD

    Optional:
      UT_NOTIFY_SMTP_HOST default smtp.gmail.com
      UT_NOTIFY_SMTP_PORT default 465
    """
    sender = os.environ["UT_NOTIFY_EMAIL_FROM"]
    recipient = os.environ["UT_NOTIFY_EMAIL_TO"]
    password = os.environ["UT_NOTIFY_EMAIL_APP_PASSWORD"]

    smtp_host = os.environ.get("UT_NOTIFY_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("UT_NOTIFY_SMTP_PORT", "465"))

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)


def notify_operator(subject: str, body: str) -> None:
    if not email_notifications_enabled():
        append_log(
            "NOTIFICATION SKIPPED",
            (
                "Email notification skipped because one or more required "
                "environment variables are missing: "
                "UT_NOTIFY_EMAIL_FROM, UT_NOTIFY_EMAIL_TO, "
                "UT_NOTIFY_EMAIL_APP_PASSWORD."
            ),
        )
        return

    try:
        notify_operator_email(subject, body)
        append_log("NOTIFICATION SENT", f"Email sent: {subject}")
    except Exception as exc:
        append_log("NOTIFICATION FAILED", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Process runners
# ---------------------------------------------------------------------------

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
        stdout, stderr = process.communicate(
            input=stdin_text,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return 124, f"TIMEOUT\n{stderr}"

    return process.returncode, stdout if stdout else stderr


def run_codex(prompt: str, dangerous: bool = False) -> tuple[int, str]:
    command = [CODEX_BIN, "exec"]

    if dangerous:
        command.append(CODEX_DANGEROUS_FLAG)

    command += [
        "--cd",
        str(REPO_ROOT),
        "--color",
        "never",
        "--output-schema",
        str(CODEX_SCHEMA_FILE),
        "-",
    ]

    return run_process(command, CODEX_TIMEOUT_SECONDS, stdin_text=prompt)


def run_claude(prompt: str, dangerous: bool = False) -> tuple[int, str]:
    command = [CLAUDE_BIN, "-p"]

    if dangerous:
        command.append(CLAUDE_DANGEROUS_FLAG)

    return run_process(command, CLAUDE_TIMEOUT_SECONDS, stdin_text=prompt)


def format_codex_output(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2)
    except Exception:
        return raw.strip()


# ---------------------------------------------------------------------------
# Claude PM prompt
# ---------------------------------------------------------------------------

def build_pm_prompt(
    mission_text: str,
    log_tail: str,
    last_codex: str | None,
    operator_context: str,
) -> str:
    last_codex_block = (
        f"LAST_CODEX_OUTPUT latest cycle JSON:\n{last_codex}\n"
        if last_codex
        else "LAST_CODEX_OUTPUT: none yet, this is the first cycle\n"
    )

    operator_block = (
        f"\n{operator_context}\n"
        if operator_context
        else "\nOPERATOR QUESTION / ANSWER CONTEXT: none\n"
    )

    return f"""
You are Claude in PM/architect/reviewer mode driving an autonomous engineering
loop for the Ultimate Trader project. Your peer is Codex, the implementer.

OPERATOR MISSION frozen, do not reinterpret:
---
{mission_text.strip()}
---

RECENT CYCLE LOG last {LOG_TAIL_CYCLES} cycles, oldest first:
---
{log_tail}
---

{last_codex_block}
{operator_block}

YOUR JOB:
- Decompose the mission into the minimum safe sequence of Codex tasks.
- If Nanyel answered an operator question, fold that answer into the next
  Codex prompt or use it to decide HALT / MISSION_COMPLETE.
- If Codex's last output has a non-empty QUESTIONS field, answer it yourself
  only when the answer is clear from mission, repo doctrine, prior log, or
  operator guidance.
- If the question cannot be safely answered, escalate to the operator.
- If Codex reports blockers or failure, do not issue repair unless the fix is
  obvious and safe.
- Never expand scope beyond the mission.
- Never approve destructive operations, broker/live-trading changes, or unclear
  architecture ownership without operator sign-off.

OUTPUT FORMAT strict:
STATUS: <one line of mission progress>
STEP: <numbered step, e.g. "2 of 4">
DIRECTIVE: NEXT_CODEX_PROMPT | OPERATOR_QUESTION | MISSION_COMPLETE | HALT
REASON: <one short sentence>
PAYLOAD:
<For NEXT_CODEX_PROMPT: literal Codex prompt, ready to send.>
<For OPERATOR_QUESTION: question for Nanyel plus what you need to unblock.>
<For MISSION_COMPLETE: short summary of what shipped and where artifacts live.>
<For HALT: reason and what the operator should inspect.>
""".strip()


DIRECTIVES = ("NEXT_CODEX_PROMPT", "OPERATOR_QUESTION", "MISSION_COMPLETE", "HALT")


def parse_claude_directive(text: str) -> dict:
    out = {
        "status": "",
        "step": "",
        "directive": "",
        "reason": "",
        "payload": "",
    }

    def grab(label: str) -> str:
        match = re.search(rf"^{label}:\s*(.*)$", text, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    out["status"] = grab("STATUS")
    out["step"] = grab("STEP")
    out["directive"] = grab("DIRECTIVE").upper()
    out["reason"] = grab("REASON")

    payload_match = re.search(
        r"^PAYLOAD:\s*\n(.*)\Z",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if payload_match:
        out["payload"] = payload_match.group(1).strip()

    if out["directive"] not in DIRECTIVES:
        out["directive"] = ""

    return out


# ---------------------------------------------------------------------------
# Loop control
# ---------------------------------------------------------------------------

def halt(state: dict, reason: str, code: str) -> None:
    state["status"] = code
    state["halt_reason"] = reason
    save_state(state)

    HALT_FILE.write_text(f"{now()} {code}\n{reason}\n", encoding="utf-8")

    print(f"\nHALT: {code}")
    print(reason)


def run_one_cycle(
    cycle: int,
    state: dict,
    mission_text: str,
    dangerous: bool = False,
) -> bool:
    print(f"\n=== CYCLE {cycle} ===")

    if HALT_FILE.exists():
        if operator_answer_present():
            print("HALT.flag present, but operator answer exists. Clearing HALT and resuming.")
            clear_halt_only()
        else:
            print("HALT.flag present and no operator answer found. Stopping.")
            return False

    log_tail = read_log_tail(LOG_TAIL_CYCLES)
    operator_context = read_operator_question_context()

    last_codex = (
        CODEX_OUTPUT_FILE.read_text(encoding="utf-8").strip()
        if CODEX_OUTPUT_FILE.exists() and state.get("last_codex_hash")
        else None
    )

    pm_prompt = build_pm_prompt(
        mission_text=mission_text,
        log_tail=log_tail,
        last_codex=last_codex,
        operator_context=operator_context,
    )

    print("--- Claude PM ---")
    code, claude_raw = run_claude(pm_prompt, dangerous=dangerous)
    claude_out = claude_raw.strip()
    CLAUDE_OUTPUT_FILE.write_text(claude_out, encoding="utf-8")

    if code != 0:
        halt(state, f"Claude returned exit code {code}.", "claude_failed")
        return False

    claude_hash = sha256_text(claude_out)

    if claude_hash == state.get("last_claude_hash"):
        halt(
            state,
            "Claude output identical to previous cycle. No progress.",
            "stopped_no_progress_claude",
        )
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
        halt(
            state,
            "Claude output did not contain a parseable DIRECTIVE.",
            "stopped_unparseable_directive",
        )
        return False

    if parsed["directive"] == "MISSION_COMPLETE":
        consume_operator_question_if_safe(parsed["directive"])
        state["status"] = "mission_complete"
        state["halt_reason"] = None
        save_state(state)

        print("\nMISSION COMPLETE")
        print(parsed["payload"])
        return False

    if parsed["directive"] == "OPERATOR_QUESTION":
        question_body = write_operator_question(
            cycle=cycle,
            reason=parsed["reason"],
            payload=parsed["payload"],
        )

        notify_operator(
            subject=f"Ultimate Trader needs your decision - cycle {cycle}",
            body=question_body,
        )

        halt(
            state,
            "Claude paged the operator. Add your answer to scripts/operator_questions.txt.",
            "stopped_operator_question",
        )
        return False

    if parsed["directive"] == "HALT":
        halt(
            state,
            parsed["reason"] or "Claude requested HALT.",
            "stopped_claude_halt",
        )
        return False

    if not parsed["payload"].strip():
        halt(
            state,
            "Claude said NEXT_CODEX_PROMPT but PAYLOAD was empty.",
            "stopped_empty_codex_prompt",
        )
        return False

    consume_operator_question_if_safe(parsed["directive"])

    PROMPT_FILE.write_text(parsed["payload"], encoding="utf-8")

    print("--- Codex ---")
    code, codex_raw = run_codex(parsed["payload"], dangerous=dangerous)
    formatted = format_codex_output(codex_raw)
    CODEX_OUTPUT_FILE.write_text(formatted, encoding="utf-8")

    append_log(f"CODEX cycle {cycle} :: exit={code}", formatted)

    if code != 0:
        halt(
            state,
            f"Codex returned exit code {code}. See codex_output.txt.",
            "stopped_codex_failed",
        )
        return False

    codex_hash = sha256_text(formatted)

    if codex_hash == state.get("last_codex_hash"):
        halt(
            state,
            "Codex output identical to previous cycle. No progress.",
            "stopped_no_progress_codex",
        )
        return False

    state["last_codex_hash"] = codex_hash
    state["cycle"] = cycle
    state["status"] = "cycle_complete"
    state["halt_reason"] = None
    save_state(state)

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mission-driven Claude/Codex orchestrator"
    )

    parser.add_argument("--max-cycles", type=int, default=20)

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear state, log, HALT.flag, operator questions, and outputs.",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Clear HALT.flag only and preserve operator_questions.txt for answer replay.",
    )

    parser.add_argument(
        "--discard-question",
        action="store_true",
        help="Delete operator_questions.txt if you want to abandon a pending answer.",
    )

    parser.add_argument(
        "--dangerous",
        action="store_true",
        help="Run Claude/Codex with approval and sandbox bypass flags.",
    )

    args = parser.parse_args()

    if args.reset:
        for path in (
            STATE_FILE,
            LOG_FILE,
            HALT_FILE,
            OPERATOR_QUESTIONS_FILE,
            CODEX_OUTPUT_FILE,
            CLAUDE_OUTPUT_FILE,
            PROMPT_FILE,
        ):
            unlink_if_exists(path)

    if args.discard_question:
        discard_operator_question()

    if args.resume:
        clear_halt_only()

    if not MISSION_FILE.exists():
        print(f"Missing mission file: {MISSION_FILE}")
        sys.exit(1)

    mission_text = MISSION_FILE.read_text(encoding="utf-8").strip()

    if not mission_text or "<Describe what I want done>" in mission_text:
        print("operator_mission.txt is empty or still has the placeholder.")
        sys.exit(1)

    state = load_state()
    mission_hash = sha256_text(mission_text)

    if state.get("mission_hash") != mission_hash:
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
    print(f"Dangerous mode: {args.dangerous}")
    print(f"Email notifications enabled: {email_notifications_enabled()}")
    print(f"Resuming from cycle: {state.get('cycle', 0)}")

    start = state.get("cycle", 0) + 1
    end = start + args.max_cycles

    for cycle in range(start, end):
        if not run_one_cycle(
            cycle=cycle,
            state=state,
            mission_text=mission_text,
            dangerous=args.dangerous,
        ):
            break
    else:
        halt(
            state,
            f"Reached max cycles {args.max_cycles}. Mission still in flight.",
            "stopped_max_cycles",
        )

    final = load_state()

    print(f"\nFinal status: {final.get('status')}")

    if final.get("halt_reason"):
        print(f"Halt reason: {final['halt_reason']}")


if __name__ == "__main__":
    main()