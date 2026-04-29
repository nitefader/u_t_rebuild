import type { BrokerSyncState } from "@/api/schemas/accounts";

export function latestBrokerSyncTimestamp(state: BrokerSyncState | null | undefined): string | null {
  return (
    state?.last_successful_sync_at ??
    state?.last_poll_sync_at ??
    state?.last_event_at ??
    state?.last_sync_at ??
    null
  );
}
