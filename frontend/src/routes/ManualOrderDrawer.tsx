import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { ManualTradeApi } from "@/api/manualTrade";
import type { BrokerAccount } from "@/api/schemas/accounts";
import type {
  ManualOrderIntent,
  ManualOrderResponse,
  OrderSide,
  OrderType,
  TimeInForce,
} from "@/api/schemas/manualTrade";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";

interface ManualOrderDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: BrokerAccount;
}

function nextIdempotencyKey(): string {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
      : Math.random().toString(36).slice(2, 18);
  return `manual-${Date.now().toString(36)}-${suffix}`;
}

export function ManualOrderDrawer({
  open,
  onOpenChange,
  account,
}: ManualOrderDrawerProps): JSX.Element {
  const queryClient = useQueryClient();
  const isLive = account.mode === "BROKER_LIVE";
  // Rotate the idempotency key on every drawer open AND after every
  // successful submit so a follow-up order in the same session is a
  // distinct request to the broker. `submitNonce` advances on success.
  const [submitNonce, setSubmitNonce] = useState(0);
  const idempotencyKey = useMemo(() => nextIdempotencyKey(), [open, submitNonce]);

  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [side, setSide] = useState<OrderSide>("long");
  const [orderType, setOrderType] = useState<OrderType>("market");
  const [timeInForce, setTimeInForce] = useState<TimeInForce>("day");
  const [intent, setIntent] = useState<ManualOrderIntent>("open");
  const [reason, setReason] = useState("Operator manual order");
  const [confirmName, setConfirmName] = useState("");
  const [lastResult, setLastResult] = useState<ManualOrderResponse | null>(null);

  // Reset transient state when the drawer reopens for a new submit.
  useEffect(() => {
    if (!open) return;
    setLastResult(null);
  }, [open]);

  const qtyNumber = Number(quantity);
  const symbolClean = symbol.trim().toUpperCase();
  const reasonClean = reason.trim();
  const liveConfirmed = !isLive || confirmName.trim() === account.display_name;
  const canSubmit =
    symbolClean.length > 0 &&
    Number.isFinite(qtyNumber) &&
    qtyNumber > 0 &&
    reasonClean.length > 0 &&
    liveConfirmed;

  const submit = useMutation({
    mutationFn: () =>
      ManualTradeApi.submit(account.id, {
        symbol: symbolClean,
        side,
        qty: qtyNumber,
        order_type: orderType,
        time_in_force: timeInForce,
        intent,
        reason: reasonClean,
        idempotency_key: idempotencyKey,
        confirm_live: isLive,
        confirm_account_display_name: isLive ? confirmName.trim() : null,
      }),
    // Don't auto-close the drawer. Show the result inline so the
    // operator can verify it landed before composing another order.
    // Force-refetch every consumer of the order/position state.
    onSuccess: async (resp) => {
      setLastResult(resp);
      // Clear the submit-only fields; keep symbol + side + intent so a
      // back-to-back order on the same symbol is one click away.
      setQuantity("");
      setReason("Operator manual order");
      setConfirmName("");
      setSubmitNonce((n) => n + 1);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["operations", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["operations", "account", account.id] }),
        queryClient.invalidateQueries({ queryKey: ["manual-trade", "list", account.id] }),
        queryClient.invalidateQueries({ queryKey: ["accounts", "list"] }),
      ]);
    },
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Manual order</DrawerTitle>
          <DrawerDescription>
            Account-scoped operator order. Backend preflight, OrderManager,
            BrokerAdapter, and BrokerSync remain the boundaries.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {submit.isError ? (
            <Banner
              severity="danger"
              title="Order was not submitted"
              message={(submit.error as Error)?.message}
            />
          ) : null}

          {lastResult ? (
            <Banner
              severity={lastResult.duplicate ? "info" : "success"}
              title={
                lastResult.duplicate
                  ? "Idempotent — same request returned the existing order"
                  : "Order submitted"
              }
              message={`${lastResult.symbol} ${lastResult.side} ${lastResult.quantity} · status ${lastResult.status} · order id ${lastResult.order_id.slice(0, 8)} · operator can compose another below or close.`}
            />
          ) : null}

          {isLive ? (
            <Banner
              severity="warning"
              title="Live account"
              message={`Type ${account.display_name} exactly before submitting.`}
            />
          ) : (
            <Banner
              severity="info"
              title="Paper account"
              message="This still routes through the production manual order boundary."
            />
          )}

          <div className="grid grid-cols-2 gap-3">
            <TextField
              label="Symbol"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="AAPL"
              autoCapitalize="characters"
            />
            <TextField
              label="Quantity"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              placeholder="1"
              inputMode="decimal"
              invalid={quantity.length > 0 && (!Number.isFinite(qtyNumber) || qtyNumber <= 0)}
            />
            <Select
              label="Side"
              value={side}
              onChange={(event) => setSide(event.target.value as OrderSide)}
            >
              <option value="long">Long / buy</option>
              <option value="short">Short / sell</option>
            </Select>
            <Select
              label="Intent"
              value={intent}
              onChange={(event) => setIntent(event.target.value as ManualOrderIntent)}
            >
              <option value="open">Open</option>
              <option value="reduce">Reduce</option>
              <option value="close">Close</option>
            </Select>
            <Select
              label="Order type"
              value={orderType}
              onChange={(event) => setOrderType(event.target.value as OrderType)}
            >
              <option value="market">Market</option>
              <option value="limit">Limit</option>
              <option value="stop">Stop</option>
              <option value="stop_limit">Stop limit</option>
            </Select>
            <Select
              label="Time in force"
              value={timeInForce}
              onChange={(event) => setTimeInForce(event.target.value as TimeInForce)}
            >
              <option value="day">Day</option>
              <option value="gtc">GTC</option>
              <option value="ioc">IOC</option>
              <option value="fok">FOK</option>
              <option value="opg">OPG</option>
              <option value="cls">CLS</option>
            </Select>
          </div>

          <TextField
            label="Reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why this manual order is needed"
          />

          {isLive ? (
            <TextField
              label="Live confirmation"
              value={confirmName}
              onChange={(event) => setConfirmName(event.target.value)}
              placeholder={account.display_name}
              invalid={confirmName.length > 0 && !liveConfirmed}
            />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant={isLive ? "danger" : "primary"}
            loading={submit.isPending}
            disabled={!canSubmit}
            leftIcon={<Send className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => submit.mutate()}
          >
            Submit order
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
