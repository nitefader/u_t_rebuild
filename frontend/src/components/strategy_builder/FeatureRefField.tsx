import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import { FeaturePicker } from "./FeaturePicker";

/**
 * FeatureRefField — pill-styled feature picker for use inside condition
 * rows. Delegates to FeaturePicker which opens a structured combobox
 * with namespace-grouped catalog + per-feature param form.
 */
export interface FeatureRefFieldProps {
  value: string;
  onChange: (next: string) => void;
  catalog: FeatureCatalogItem[];
  placeholder?: string;
  invalid?: boolean;
  invalidMessage?: string | null;
  disabled?: boolean;
  className?: string;
  consumer?: string;
}

export function FeatureRefField(props: FeatureRefFieldProps): JSX.Element {
  return (
    <FeaturePicker
      value={props.value}
      onChange={props.onChange}
      catalog={props.catalog}
      consumer={props.consumer ?? "backtest"}
      invalid={props.invalid}
      invalidMessage={props.invalidMessage}
      disabled={props.disabled}
      placeholder={props.placeholder ?? "pick feature"}
      compact
    />
  );
}
