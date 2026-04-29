import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Right-side slideout. Built on Radix Dialog because Radix doesn't
 * have a primitive named Drawer; the Dialog primitive gives us the
 * focus trap, Esc-to-close, and portal behavior the operator
 * surface needs.
 *
 * 200ms transition; honors prefers-reduced-motion via theme.css.
 */
export const Drawer = DialogPrimitive.Root;
export const DrawerTrigger = DialogPrimitive.Trigger;
export const DrawerPortal = DialogPrimitive.Portal;
export const DrawerClose = DialogPrimitive.Close;

export function DrawerContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DrawerPortal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm" />
      <DialogPrimitive.Content
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col",
          "border-l border-border bg-bg-raised shadow-raised animate-ut-slide-in-right",
          "focus:outline-none",
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          aria-label="Close drawer"
          className="absolute right-2 top-2 rounded p-1 text-fg-muted hover:bg-bg-subtle hover:text-fg"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DrawerPortal>
  );
}

export function DrawerHeader({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("border-b border-border px-4 py-3", className)}>
      {children}
    </div>
  );
}

export function DrawerTitle({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Title className={cn("text-base font-semibold", className)}>
      {children}
    </DialogPrimitive.Title>
  );
}

export function DrawerDescription({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Description
      className={cn("mt-1 text-sm text-fg-muted", className)}
    >
      {children}
    </DialogPrimitive.Description>
  );
}

export function DrawerBody({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex-1 overflow-y-auto px-4 py-3", className)}>
      {children}
    </div>
  );
}

export function DrawerFooter({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-2 border-t border-border px-4 py-3",
        className,
      )}
    >
      {children}
    </div>
  );
}
