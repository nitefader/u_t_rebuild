import { forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface TextFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  invalid?: boolean;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, hint, invalid, className, ...rest },
  ref,
) {
  return (
    <label className="block text-xs">
      {label ? <span className="text-fg-muted">{label}</span> : null}
      <input
        ref={ref}
        className={cn(
          "mt-1 block w-full rounded border bg-bg-inset px-2 py-1.5 text-sm",
          invalid ? "border-danger" : "border-border focus:border-accent",
          "focus:outline-none",
          className,
        )}
        {...rest}
      />
      {hint ? <span className={cn("mt-1 block", invalid ? "text-danger" : "text-fg-subtle")}>{hint}</span> : null}
    </label>
  );
});
