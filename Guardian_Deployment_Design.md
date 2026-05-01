Completed. P0-6 is now executed with the same hygiene and verified.

What I implemented
Race fix in backend/app/pipeline/orchestrator.py

Added per-parent-order locking for post-fill protective placement:
new lock map: self._post_fill_parent_locks
critical section now wraps the full sequence in _handle_post_fill_protective_placement:
read already_covered
compute protective plan
create children
submit children
This prevents concurrent partial-fill handlers from double-placing overlapping protective slices for the same parent order.
Regression test added in backend/tests/unit/pipeline/test_runtime_orchestrator_post_fill_bracket_critic_fixes.py

test_p0_6_concurrent_partial_fill_handlers_do_not_double_protect
Runs two threads against the same parent fill path and asserts only one first-slice stop leg (stop@10) exists.
Verification
Focused test:
python -m pytest backend/tests/unit/pipeline/test_runtime_orchestrator_post_fill_bracket_critic_fixes.py -q
6 passed
Wider handoff gate:
python -m pytest backend/tests/unit/pipeline backend/tests/unit/orders -q
145 passed
Coordination hygiene completed
Updated:
COORDINATION/LOCKS.md (leases acquired + released)
COORDINATION/INBOX_CLAUDE.md (heads-up posted)
COORDINATION/LEDGER.md (cross-boundary/internal ledger entry)
Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md (heartbeat + completion state)
P0 batch from the handoff is now complete (P0-4, P0-5, P0-6).