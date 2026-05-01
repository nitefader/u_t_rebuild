/**
 * Route constants for the v4 Strategy IDE and related screens.
 *
 * All navigation that links to or from the strategy list / compose pages
 * or the deployment screens must import from here. No other file in
 * frontend/ may hardcode these strings.
 */

/** The strategy list page — shows saved v4 strategies. */
export const ROUTE_STRATEGIES = "/strategies";

/** The v4 compose / edit page. Append ?id=<version_id> to open an existing strategy. */
export const ROUTE_STRATEGIES_COMPOSE = "/strategies/compose";

/** The deployment list page. */
export const ROUTE_DEPLOYMENTS = "/deployments";

/** The 6-step new-deployment wizard. Mounted outside AppShell (focused mode). */
export const ROUTE_DEPLOYMENTS_NEW = "/deployments/new";

/** The deployment detail view. :id is the deployment_id UUID. */
export const ROUTE_DEPLOYMENT_DETAIL = "/deployments/:id";

/** Helper: build a concrete deployment detail path. */
export function deploymentDetailPath(id: string): string {
  return `/deployments/${id}`;
}
