import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { SystemApi } from "@/api/system";
import type { SystemSettings } from "@/api/schemas/system";
import { ApiError } from "@/api/client";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { PageHeader } from "./PageHeader";

export function Settings(): JSX.Element {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["system", "settings"], queryFn: () => SystemApi.getSettings() });

  const [draft, setDraft] = useState<SystemSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (q.data && draft === null) setDraft(q.data);
  }, [q.data, draft]);

  const save = useMutation({
    mutationFn: () => SystemApi.putSettings(draft ?? {}),
    onSuccess: (next) => {
      setDraft(next);
      setNotice("Settings saved.");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["system", "settings"] });
      void qc.invalidateQueries({ queryKey: ["system", "status"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  if (q.isLoading) return <LoadingState title="Loading settings" />;
  if (q.isError)
    return (
      <ErrorState
        title="Could not load settings"
        detail={(q.error as Error)?.message}
        onRetry={() => q.refetch()}
      />
    );

  const useTestStream = Boolean(draft?.alpaca_use_test_stream);
  const dataFeed = draft?.alpaca_data_feed ?? "iex";
  const defaultSymbol = draft?.default_symbol ?? "SPY";
  const chartLabFakepaca = Boolean(draft?.chart_lab_one_symbol_fakepaca);

  function patch(next: Partial<SystemSettings>): void {
    setDraft({ ...(draft ?? {}), ...next });
    setNotice(null);
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Settings"
        subtitle="Platform preferences only. Runtime controls live in Operations."
        explainSlug="settings"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Save className="h-3.5 w-3.5" aria-hidden="true" />}
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            Save
          </Button>
        }
      />

      {error ? <Banner severity="danger" title="Save failed" message={error} /> : null}
      {notice ? <Banner severity="success" title="Saved" message={notice} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Live Stock Market Data Stream</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <Select
            label="Default data feed"
            hint="Used by the platform live stock market data hub when no role override is set."
            value={dataFeed}
            onChange={(e) => patch({ alpaca_data_feed: e.target.value })}
          >
            <option value="iex">IEX</option>
            <option value="sip">SIP (paid)</option>
            <option value="otc">OTC</option>
            <option value="boats">BOATS</option>
          </Select>

          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={useTestStream}
              onChange={(e) => patch({ alpaca_use_test_stream: e.target.checked })}
            />
            <span>
              <span className="font-medium">Use FAKEPACA test stream</span>
              <span className="block text-xs text-fg-muted">Synthetic 24/7 stream for off-hours dev. Disabled in production.</span>
            </span>
          </label>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Chart Lab</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <TextField
            label="Default symbol"
            hint="Symbol Chart Lab opens with on first load."
            value={defaultSymbol}
            onChange={(e) => patch({ default_symbol: e.target.value.toUpperCase() })}
          />
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={chartLabFakepaca}
              onChange={(e) => patch({ chart_lab_one_symbol_fakepaca: e.target.checked })}
            />
            <span>
              <span className="font-medium">Pin Chart Lab to FAKEPACA</span>
              <span className="block text-xs text-fg-muted">Forces synthetic stream regardless of Auto resolver.</span>
            </span>
          </label>
        </CardBody>
      </Card>
    </div>
  );
}
