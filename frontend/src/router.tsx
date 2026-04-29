import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Dashboard } from "@/routes/Dashboard";
import { Strategies } from "@/routes/Strategies";
import { StrategyBuilder } from "@/routes/StrategyBuilder";
import { StrategyCompose } from "@/routes/StrategyCompose";
import { StrategyDetail } from "@/routes/StrategyDetail";
import { Components } from "@/routes/Components";
import { Watchlists } from "@/routes/Watchlists";
import { Accounts } from "@/routes/Accounts";
import { Deployments } from "@/routes/Deployments";
import { Operations } from "@/routes/Operations";
import { Providers } from "@/routes/Providers";
import { Settings } from "@/routes/Settings";
import { ChartLab } from "@/routes/ChartLab";
import { SimLab } from "@/routes/SimLab";
import { Backtests } from "@/routes/Backtests";
import { Optimization } from "@/routes/Optimization";
import { WalkForward } from "@/routes/WalkForward";
import { DataCenterHistoricalDatasets } from "@/routes/DataCenterHistoricalDatasets";
import { RiskPlans } from "@/routes/RiskPlans";
import { RiskPlanDetail } from "@/routes/RiskPlanDetail";
import { Screeners } from "@/routes/Screeners";
import { ScreenerDetail } from "@/routes/ScreenerDetail";
import { NotFound } from "@/routes/NotFound";

export const router = createBrowserRouter([
  // Focused-mode composer is mounted OUTSIDE AppShell so the operator never
  // sees the sidenav / topbar while composing — see Strategies redesign plan,
  // Slice 3 ("the whole screen should be focused on that"). Sibling top-level
  // route, not a child of the AppShell layout.
  { path: "/strategies/compose", element: <StrategyCompose /> },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "strategies", element: <Strategies /> },
      { path: "strategies/:strategyId", element: <StrategyDetail /> },
      { path: "strategies/:strategyId/builder/new", element: <StrategyBuilder /> },
      { path: "strategies/:strategyId/builder/:versionId", element: <StrategyBuilder /> },
      { path: "components", element: <Components /> },
      { path: "risk-plans", element: <RiskPlans /> },
      { path: "risk-plans/:riskPlanId", element: <RiskPlanDetail /> },
      { path: "watchlists", element: <Watchlists /> },
      { path: "screeners", element: <Screeners /> },
      { path: "screeners/:screenerId", element: <ScreenerDetail /> },
      { path: "accounts", element: <Accounts /> },
      { path: "deployments", element: <Deployments /> },
      { path: "operations", element: <Operations /> },
      { path: "providers", element: <Providers /> },
      { path: "data-center/historical-datasets", element: <DataCenterHistoricalDatasets /> },
      { path: "settings", element: <Settings /> },
      { path: "chart-lab", element: <ChartLab /> },
      { path: "sim-lab", element: <SimLab /> },
      { path: "backtests", element: <Backtests /> },
      { path: "optimization", element: <Optimization /> },
      { path: "walk-forward", element: <WalkForward /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
