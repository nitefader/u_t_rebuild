import { NavLink } from "react-router-dom";
import {
  Activity,
  Brain,
  ChevronLeft,
  ChevronRight,
  Filter,
  HardDrive,
  Layers,
  List,
  Code2,
  Sliders,
  Send,
  Monitor,
  Server,
  Settings as SettingsIcon,
  Shield,
  Sun,
  Moon,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { ROUTE_STRATEGIES, ROUTE_STRATEGIES_COMPOSE } from "@/strategy_ide_v4/routes";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/cn";
import { AppShellActions, useAppShell } from "@/store/useAppShell";

interface NavItem {
  to: string;
  label: string;
  Icon: LucideIcon;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  {
    label: "Trade",
    items: [
      { to: "/", label: "Dashboard", Icon: Monitor },
      { to: "/operations", label: "Operations", Icon: Activity },
      { to: "/accounts", label: "Accounts", Icon: Shield },
      { to: "/deployments", label: "Deployments", Icon: Zap },
    ],
  },
  {
    label: "Author",
    items: [
      { to: ROUTE_STRATEGIES, label: "Strategies", Icon: Layers },
      { to: ROUTE_STRATEGIES_COMPOSE, label: "Compose", Icon: Code2 },
      { to: "/controls", label: "Strategy Controls", Icon: Sliders },
      { to: "/execution-plans", label: "Execution Plans", Icon: Send },
      { to: "/components", label: "Components", Icon: Brain },
      { to: "/risk-plans", label: "Risk Plans", Icon: Shield },
      { to: "/watchlists", label: "Watchlists", Icon: List },
      { to: "/screeners", label: "Screeners", Icon: Filter },
    ],
  },
  {
    label: "Data Center",
    items: [{ to: "/data-center/historical-datasets", label: "Historical Datasets", Icon: HardDrive }],
  },
  {
    label: "Platform",
    items: [
      { to: "/providers", label: "Providers", Icon: Server },
      { to: "/settings", label: "Settings", Icon: SettingsIcon },
    ],
  },
];

export function SideNav(): JSX.Element {
  const { sidebarCollapsed, theme } = useAppShell();
  const widthClass = sidebarCollapsed ? "w-12" : "w-56";

  return (
    <aside
      className={cn(
        "sticky top-0 z-30 flex h-screen shrink-0 flex-col border-r border-border bg-bg-subtle/60 transition-[width] duration-150",
        widthClass,
      )}
      aria-label="Primary navigation"
    >
      <div
        className={cn(
          "flex items-center border-b border-border h-12",
          sidebarCollapsed ? "justify-center" : "justify-between gap-2 px-3",
        )}
      >
        <NavLink
          to="/"
          className="flex items-center gap-2 text-sm font-semibold tracking-tight text-fg"
          aria-label="Ultimate Trader home"
        >
          <span aria-hidden="true" className="text-base text-accent">
            ▣
          </span>
          {!sidebarCollapsed && <span>Ultimate Trader</span>}
        </NavLink>
      </div>

      <nav className="flex-1 overflow-y-auto px-1 py-2">
        <TooltipPrimitive.Provider delayDuration={150}>
          {GROUPS.map((group) => (
            <div key={group.label} className="mb-3 last:mb-0">
              {!sidebarCollapsed ? (
                <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">
                  {group.label}
                </div>
              ) : (
                <div className="my-1 h-px bg-border/60" aria-hidden="true" />
              )}
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.to}>
                    <SideNavLink item={item} collapsed={sidebarCollapsed} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </TooltipPrimitive.Provider>
      </nav>

      <div
        className={cn(
          "flex items-center border-t border-border py-1",
          sidebarCollapsed ? "flex-col gap-1 px-1" : "gap-1 px-2",
        )}
      >
        <button
          type="button"
          onClick={AppShellActions.toggleTheme}
          className="inline-flex h-8 w-8 items-center justify-center rounded text-fg-muted hover:bg-bg-subtle hover:text-fg"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Moon className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          onClick={AppShellActions.toggleSidebar}
          className={cn(
            "inline-flex items-center gap-2 rounded px-2 py-1 text-xs font-medium text-fg-muted hover:bg-bg-subtle hover:text-fg",
            sidebarCollapsed ? "h-8 w-8 justify-center" : "ml-auto",
          )}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          ) : (
            <>
              <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

function SideNavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }): JSX.Element {
  const link = (
    <NavLink
      end={item.to === "/"}
      to={item.to}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-2 rounded px-2 py-1.5 text-xs font-medium transition-colors",
          isActive
            ? "bg-bg-raised text-fg shadow-card"
            : "text-fg-muted hover:bg-bg-subtle hover:text-fg",
          collapsed && "justify-center px-0",
        )
      }
    >
      <item.Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </NavLink>
  );
  if (!collapsed) return link;
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{link}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side="right"
          sideOffset={8}
          className="z-50 rounded border border-border bg-bg-raised px-2 py-1 text-xs text-fg shadow-raised"
        >
          {item.label}
          <TooltipPrimitive.Arrow className="fill-bg-raised" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
