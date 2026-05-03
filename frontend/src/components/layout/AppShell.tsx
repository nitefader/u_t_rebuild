import { Outlet } from "react-router-dom";
import { SideNav } from "./SideNav";
import { TopBar } from "./TopBar";
import { ToastProvider } from "@/components/ui/Toast";
import { useApplyTheme } from "@/store/useAppShell";

export function AppShell(): JSX.Element {
  useApplyTheme();
  return (
    <ToastProvider>
      <div className="flex min-h-screen w-full">
        <SideNav />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <main className="flex-1 px-6 py-5">
            <Outlet />
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
