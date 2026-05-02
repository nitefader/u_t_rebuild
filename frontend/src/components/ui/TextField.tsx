import { forwardRef, useId } from "react";
import { cn } from "@/lib/cn";

export interface TextFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  invalid?: boolean;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, hint, invalid, className, id, "aria-describedby": ariaDescribedByProp, ...rest },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const ariaDescribedBy =
    [ariaDescribedByProp, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <label className="block text-xs" htmlFor={inputId}>
      {label ? <span className="text-fg-muted">{label}</span> : null}
      <input
        ref={ref}
        id={inputId}
        aria-invalid={invalid || undefined}
        aria-describedby={ariaDescribedBy}
        className={cn(
          "mt-1 block w-full rounded border bg-bg-inset px-2 py-1.5 text-sm",
          invalid ? "border-danger" : "border-border focus:border-accent",
          "focus:outline-none",
          className,
        )}
        {...rest}
      />
      {hint ? (
        <span
          id={hintId}
          className={cn("mt-1 block", invalid ? "text-danger" : "text-fg-subtle")}
        >
          {hint}
        </span>
      ) : null}
    </label>
  );
});
