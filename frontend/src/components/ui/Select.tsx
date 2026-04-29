import { forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, className, children, ...rest },
  ref,
) {
  return (
    <label className="block text-xs">
      {label ? <span className="text-fg-muted">{label}</span> : null}
      <select
        ref={ref}
        className={cn(
          "mt-1 block w-full rounded border border-border bg-bg-inset px-2 py-1.5 text-sm",
          "focus:border-accent focus:outline-none",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
      {hint ? <span className="mt-1 block text-fg-subtle">{hint}</span> : null}
    </label>
  );
});
