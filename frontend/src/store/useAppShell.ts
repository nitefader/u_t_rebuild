import { useEffect, useSyncExternalStore } from "react";

/**
 * Tiny store helper. Avoids pulling in zustand's full persist
 * middleware for what is one boolean and a string.
 */
type Listener = () => void;

interface AppShellState {
  sidebarCollapsed: boolean;
  theme: "dark" | "light";
}

const STORAGE_KEY = "ut.appShell.v1";

function readPersisted(): AppShellState {
  if (typeof window === "undefined") return { sidebarCollapsed: false, theme: "dark" };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { sidebarCollapsed: false, theme: "dark" };
    const parsed = JSON.parse(raw) as Partial<AppShellState>;
    return {
      sidebarCollapsed: Boolean(parsed.sidebarCollapsed),
      theme: parsed.theme === "light" ? "light" : "dark",
    };
  } catch {
    return { sidebarCollapsed: false, theme: "dark" };
  }
}

let state: AppShellState = readPersisted();
const listeners = new Set<Listener>();

function setState(patch: Partial<AppShellState>): void {
  state = { ...state, ...patch };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* storage may be disabled — ignore */
    }
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): AppShellState {
  return state;
}

function getServerSnapshot(): AppShellState {
  return { sidebarCollapsed: false, theme: "dark" };
}

export function useAppShell(): AppShellState {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export const AppShellActions = {
  toggleSidebar: () => setState({ sidebarCollapsed: !state.sidebarCollapsed }),
  setSidebarCollapsed: (collapsed: boolean) => setState({ sidebarCollapsed: collapsed }),
  setTheme: (theme: "dark" | "light") => setState({ theme }),
  toggleTheme: () => setState({ theme: state.theme === "dark" ? "light" : "dark" }),
};

/** Apply the persisted theme to the document root. */
export function useApplyTheme(): void {
  const { theme } = useAppShell();
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);
}
