import { forwardRef } from "react";
import { cn } from "@/lib/cn";

/**
 * Operator button. Quiet by default, never marketing-loud.
 * Danger variant is reserved for actions that create or remove
 * broker risk; pair with a type-name-to-confirm step elsewhere.
 */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "ok";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const VARIANT_MAP: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-bg hover:bg-accent/90 disabled:opacity-50 border border-transparent",
  secondary:
    "bg-bg-raised text-fg border border-border hover:bg-bg-subtle disabled:opacity-50",
  ghost:
    "bg-transparent text-fg-muted hover:text-fg hover:bg-bg-subtle border border-transparent",
  danger:
    "bg-danger text-white hover:bg-danger/90 disabled:opacity-50 border border-transparent",
  ok: "bg-ok text-white hover:bg-ok/90 disabled:opacity-50 border border-transparent",
};

const SIZE_MAP: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-8 px-3 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "md", loading, leftIcon, rightIcon, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded font-medium transition-colors",
        "disabled:cursor-not-allowed",
        VARIANT_MAP[variant],
        SIZE_MAP[size],
        className,
      )}
      {...rest}
    >
      {leftIcon}
      <span>{children}</span>
      {loading ? (
        <span className="ml-1 inline-block h-3 w-3 animate-spin rounded-full border border-current border-t-transparent" aria-hidden="true" />
      ) : (
        rightIcon
      )}
    </button>
  );
});
