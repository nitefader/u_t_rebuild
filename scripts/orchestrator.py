import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(r"C:\Users\potij\Projects\Ultimate_Trading_OS_Rebuild")
SCRIPTS_DIR = REPO_ROOT / "scripts"

PROMPT_FILE = SCRIPTS_DIR / "prompt.txt"
CODEX_OUTPUT_FILE = SCRIPTS_DIR / "codex_output.txt"
CLAUDE_OUTPUT_FILE = SCRIPTS_DIR / "claude_output.txt"
STATE_FILE = SCRIPTS_DIR / "orchestrator_state.json"
CODEX_SCHEMA_FILE = SCRIPTS_DIR / "codex_report_schema.json"

CODEX_TIMEOUT_SECONDS = 1800
CLAUDE_TIMEOUT_SECONDS = 900


def now():
    return datetime.now().isoformat(timespec="seconds")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_state():
    if not STATE_FILE.exists():
        return {
            "status": "new",
            "cycle": 0,
            "last_prompt_hash": None,
            "last_codex_hash": None,
            "last_claude_hash": None,
            "updated_at": now(),
        }

    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    state["updated_at"] = now()
    STATE_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")


def run_process(command, timeout_seconds):
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        raise TimeoutError(f"Process timed out: {' '.join(command)}\n{stderr}")

    output = stdout if stdout else stderr
    return process.returncode, output


def run_codex(prompt: str):
    command = [
        "codex.cmd",
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--color",
        "never",
        "--output-schema",
        str(CODEX_SCHEMA_FILE),
        prompt,
    ]

    return run_process(command, CODEX_TIMEOUT_SECONDS)


def run_claude(prompt: str):
    command = ["claude", "-p", prompt]
    return run_process(command, CLAUDE_TIMEOUT_SECONDS)


def format_codex_output(raw_output: str) -> str:
    try:
        parsed = json.loads(raw_output)
        return json.dumps(parsed, indent=4)
    except Exception:
        return raw_output


def extract_decision(claude_output: str) -> str:
    upper = claude_output.upper()

    if "NEEDS REPAIR" in upper:
        return "NEEDS REPAIR"
    if "FAIL" in upper:
        return "FAIL"
    if "PASS" in upper:
        return "PASS"

    return "UNKNOWN"


def extract_next_prompt(claude_output: str) -> str:
    markers = [
        "NEXT CODEX PROMPT ONLY:",
        "NEXT CODEX PROMPT:",
        "NEXT PROMPT:",
    ]

    for marker in markers:
        idx = claude_output.upper().find(marker)
        if idx != -1:
            return claude_output[idx + len(marker):].strip()

    lines = claude_output.strip().splitlines()

    if len(lines) >= 3:
        return "\n".join(lines[2:]).strip()

    return ""


def build_claude_review_prompt(formatted_codex: str) -> str:
    return f"""
You are the Claude reviewer in an automated Ultimate Trader engineering loop.

Role:
- Senior software engineer
- Architect
- Quant reviewer
- Alpaca API reviewer
- Codex output reviewer

Operating rules:
- Review Codex output strictly.
- Do not implement code.
- Do not expand scope.
- Decide PASS, FAIL, or NEEDS REPAIR.
- If Codex did not actually perform the task, return NEEDS REPAIR.
- If tests failed, return FAIL unless the next prompt is specifically a repair prompt.
- If blockers exist, return NEEDS REPAIR or FAIL.
- If output is acceptable, return PASS.

Return format:
DECISION: PASS | FAIL | NEEDS REPAIR
REASON: one short sentence
NEXT CODEX PROMPT ONLY:
<one concrete next Codex prompt>

Codex output:
{formatted_codex}
""".strip()


def run_cycle(cycle_number: int, state: dict) -> bool:
    print(f"\n=== CYCLE {cycle_number} STARTED ===")

    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Missing prompt file: {PROMPT_FILE}")

    codex_prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()

    if not codex_prompt:
        raise ValueError("prompt.txt is empty")

    prompt_hash = sha256_text(codex_prompt)

    if prompt_hash == state.get("last_prompt_hash"):
        print("STOP: prompt.txt has not changed since the last cycle.")
        state["status"] = "stopped_prompt_unchanged"
        save_state(state)
        return False

    state["status"] = "running_codex"
    state["cycle"] = cycle_number
    state["last_prompt_hash"] = prompt_hash
    save_state(state)

    print("--- Running Codex ---")
    codex_code, codex_raw = run_codex(codex_prompt)

    formatted_codex = format_codex_output(codex_raw)
    codex_hash = sha256_text(formatted_codex)

    CODEX_OUTPUT_FILE.write_text(formatted_codex, encoding="utf-8")

    if codex_code != 0:
        print("STOP: Codex returned non-zero exit code.")
        state["status"] = "codex_failed"
        state["last_codex_hash"] = codex_hash
        save_state(state)
        return False

    if codex_hash == state.get("last_codex_hash"):
        print("STOP: Codex output did not change.")
        state["status"] = "stopped_codex_output_unchanged"
        save_state(state)
        return False

    state["status"] = "running_claude"
    state["last_codex_hash"] = codex_hash
    save_state(state)

    print("--- Running Claude Review ---")
    review_prompt = build_claude_review_prompt(formatted_codex)
    claude_code, claude_output = run_claude(review_prompt)

    claude_output = claude_output.strip()
    claude_hash = sha256_text(claude_output)

    CLAUDE_OUTPUT_FILE.write_text(claude_output, encoding="utf-8")

    if claude_code != 0:
        print("STOP: Claude returned non-zero exit code.")
        state["status"] = "claude_failed"
        state["last_claude_hash"] = claude_hash
        save_state(state)
        return False

    if claude_hash == state.get("last_claude_hash"):
        print("STOP: Claude output did not change.")
        state["status"] = "stopped_claude_output_unchanged"
        save_state(state)
        return False

    decision = extract_decision(claude_output)
    next_prompt = extract_next_prompt(claude_output)

    state["last_claude_hash"] = claude_hash
    state["last_decision"] = decision
    save_state(state)

    print("\n--- Claude Review ---")
    print(claude_output)

    if decision == "FAIL":
        print("\nSTOP: Claude returned FAIL.")
        state["status"] = "stopped_fail"
        save_state(state)
        return False

    if decision == "NEEDS REPAIR":
        print("\nSTOP: Claude returned NEEDS REPAIR.")
        print("Review claude_output.txt and manually approve the next repair prompt.")
        state["status"] = "stopped_needs_repair"
        save_state(state)
        return False

    if decision != "PASS":
        print("\nSTOP: Claude decision was unclear.")
        state["status"] = "stopped_unknown_decision"
        save_state(state)
        return False

    if not next_prompt:
        print("\nSTOP: Claude did not provide a next prompt.")
        state["status"] = "stopped_missing_next_prompt"
        save_state(state)
        return False

    PROMPT_FILE.write_text(next_prompt, encoding="utf-8")

    state["status"] = "cycle_complete"
    save_state(state)

    print(f"\n=== CYCLE {cycle_number} COMPLETE ===")
    print("Next prompt written to prompt.txt")
    return True


def main():
    parser = argparse.ArgumentParser(description="Ultimate Trader Claude/Codex orchestrator")
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--reset-state", action="store_true")
    args = parser.parse_args()

    if args.max_cycles < 1:
        print("max-cycles must be at least 1")
        sys.exit(1)

    if args.reset_state and STATE_FILE.exists():
        STATE_FILE.unlink()

    state = load_state()

    print("Ultimate Trader Orchestrator Started")
    print(f"Repo root: {REPO_ROOT}")
    print(f"Max cycles: {args.max_cycles}")

    for cycle in range(1, args.max_cycles + 1):
        should_continue = run_cycle(cycle, state)

        if not should_continue:
            break

        time.sleep(1)

    state = load_state()
    state["status"] = f"finished_after_{state.get('cycle', 0)}_cycle(s)"
    save_state(state)

    print("\nOrchestrator stopped safely.")
    print(f"Final state: {state['status']}")


if __name__ == "__main__":
    main()