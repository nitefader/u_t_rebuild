# DO NOT READ#

Run <C:\Users\potij\Projects\Ultimate_Trading_OS_Rebuild\MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md> end to end using a 3-pass Wiggum loop.

----------------------------------
AUTONOMY RULE
----------------------------------

Do not stop for blockers.

For every blocker:
1. Perform a 5 Whys analysis
2. State the best educated assumption
3. Choose the safest implementation path
4. Continue execution

Only stop if continuing would:
- execute real-money trades
- delete user data outside scope
- expose secrets
- violate backend doctrine

----------------------------------
REQUIRED ROLES (EVERY PASS)
----------------------------------

1. Product Manager
   - operator value
   - workflow simplicity
   - acceptance criteria

2. Adversarial Agent
   - bugs
   - edge cases
   - overbuilt UX
   - hidden complexity

3. Doctrine Reviewer (Nanyel)
   - Strategy remains symbol-agnostic
   - SignalPlan remains neutral (no quantity, no execution leakage)
   - RiskResolver owns sizing
   - Governor is final approval gate
   - BrokerAdapter only submits
   - BrokerSync is only truth writer
   - No duplicate runtime flows
   - No frontend-driven backend changes

----------------------------------
EXECUTION RULES
----------------------------------

- Do NOT modify unrelated files
- Do NOT introduce new entities without justification
- Do NOT refactor architecture unless required
- Prefer minimal, precise changes

----------------------------------
TIMESTAMPED LOGGING (REQUIRED)
----------------------------------

All outputs MUST be logged to a timestamped file.

Directory:
docs/agent_logs/

File naming format:
YYYY-MM-DD_HH-mm-ss_<task_name>.md

Example:
2026-04-29_20-41-12_strategy_execution_pass1.md

----------------------------------
LOG ENTRY FORMAT (APPEND EACH PASS)
----------------------------------

Each pass MUST append a new section:

```text
# PASS X
Timestamp: YYYY-MM-DD HH:mm:ss -04:00
Agent Roles Active:
- Product Manager
- Adversarial Agent
- Doctrine Reviewer

## Findings
...

## Risks
...

## Decisions
...

## Files Changed
...

## Tests Run
Command:
Result:

## Remaining Issues
...

## Next Action
...

----------------------------------
IMPLEMENTATION FLOW
----------------------------------

Pass 1:
- Understand
- Implement baseline
- Fix obvious issues

Pass 2:
- Harden logic
- Handle edge cases
- Improve correctness

Pass 3:
- Simplify
- Remove overengineering
- Ensure doctrine alignment

----------------------------------
FINAL REQUIREMENT
----------------------------------

At the end:

- Verify full system flow:
  Strategy → Deployment → SignalPlan → Account → RiskResolver → Governor → Order → BrokerSync → Position

- Confirm:
  - No broken contracts
  - No silent failures
  - All tests passing
  - Backend restarted
  - Frontend restarted

- Commit and push scoped changes only.

----------------------------------
NO SHORTCUTS
----------------------------------

Correctness > speed.

My command is in ==> C:\Users\potij\Projects\Ultimate_Trading_OS_Rebuild\MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md