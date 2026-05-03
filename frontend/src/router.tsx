import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Dashboard } from "@/routes/Dashboard";
import { StrategiesV4 } from "@/routes/StrategiesV4";
import { Components } from "@/routes/Components";
import { Watchlists } from "@/routes/Watchlists";
import { Accounts } from "@/routes/Accounts";
import { Deployments } from "@/routes/Deployments";
import { DeploymentDetail } from "@/routes/DeploymentDetail";
import { NewDeploymentScreen } from "@/routes/NewDeploymentScreen";
import { Operations } from "@/routes/Operations";
import { Providers } from "@/routes/Providers";
import { Settings } from "@/routes/Settings";
import { DataCenterHistoricalDatasets } from "@/routes/DataCenterHistoricalDatasets";
import { RiskPlans } from "@/routes/RiskPlans";
import { RiskPlanDetail } from "@/routes/RiskPlanDetail";
import { Screeners } from "@/routes/Screeners";
import { ScreenerDetail } from "@/routes/ScreenerDetail";
import { ExecutionPlans } from "@/routes/ExecutionPlans";
import { ExecutionPlansEdit } from "@/routes/ExecutionPlansEdit";
import { StrategyControls } from "@/routes/StrategyControls";
import { StrategyControlsEdit } from "@/routes/StrategyControlsEdit";
import { StrategyComposeV4 } from "@/routes/StrategyComposeV4";
import { NotFound } from "@/routes/NotFound";
import {
  ROUTE_DEPLOYMENT_DETAIL,
  ROUTE_DEPLOYMENTS_NEW,
  ROUTE_STRATEGIES_COMPOSE,
} from "@/strategy_ide_v4/routes";

export const router = createBrowserRouter([
  // Focused-mode pages are mounted OUTSIDE AppShell so the operator never
  // sees the sidenav / topbar while using them.
  { path: ROUTE_STRATEGIES_COMPOSE, element: <StrategyComposeV4 /> },
  { path: ROUTE_DEPLOYMENTS_NEW, element: <NewDeploymentScreen /> },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "strategies", element: <StrategiesV4 /> },
      { path: "components", element: <Components /> },
      { path: "risk-plans", element: <RiskPlans /> },
      { path: "risk-plans/:riskPlanId", element: <RiskPlanDetail /> },
      { path: "watchlists", element: <Watchlists /> },
      { path: "controls", element: <StrategyControls /> },
      { path: "controls/:id/edit", element: <StrategyControlsEdit /> },
      { path: "execution-plans", element: <ExecutionPlans /> },
      { path: "execution-plans/:id/edit", element: <ExecutionPlansEdit /> },
      { path: "screeners", element: <Screeners /> },
      { path: "screeners/:screenerId", element: <ScreenerDetail /> },
      { path: "accounts", element: <Accounts /> },
      { path: "deployments", element: <Deployments /> },
      { path: ROUTE_DEPLOYMENT_DETAIL, element: <DeploymentDetail /> },
      { path: "operations", element: <Operations /> },
      { path: "providers", element: <Providers /> },
      { path: "data-center/historical-datasets", element: <DataCenterHistoricalDatasets /> },
      { path: "settings", element: <Settings /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
