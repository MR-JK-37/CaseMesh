import { Outlet, createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { AlertsPage } from "./pages/AlertsPage";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { CaseRegistrationPage } from "./pages/CaseRegistrationPage";
import { CasesListPage } from "./pages/CasesListPage";
import { GalleryPage } from "./pages/GalleryPage";
import { HomePage } from "./pages/HomePage";
import { ImportPage } from "./pages/ImportPage";
import { InstitutionProfilePage } from "./pages/InstitutionProfilePage";
import { InstitutionsListPage } from "./pages/InstitutionsListPage";
import { OverlapQueuePage } from "./pages/OverlapQueuePage";
import { ProfileSecurityPage } from "./pages/ProfileSecurityPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SignInPage } from "./pages/SignInPage";
import { RequireAuth } from "./RequireAuth";

const rootRoute = createRootRoute({
  component: () => <Outlet />,
});

const signInRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: SignInPage,
});

const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/home",
  component: () => (
    <RequireAuth>
      <HomePage />
    </RequireAuth>
  ),
});

const securityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/security",
  component: () => (
    <RequireAuth>
      <ProfileSecurityPage />
    </RequireAuth>
  ),
});

const adminUsersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users",
  component: () => (
    <RequireAuth>
      <AdminUsersPage />
    </RequireAuth>
  ),
});

const institutionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/institutions",
  component: () => (
    <RequireAuth>
      <InstitutionsListPage />
    </RequireAuth>
  ),
});

const institutionProfileRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/institutions/$id",
  component: () => (
    <RequireAuth>
      <InstitutionProfilePage />
    </RequireAuth>
  ),
});

const importRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/import",
  component: () => (
    <RequireAuth>
      <ImportPage />
    </RequireAuth>
  ),
});

const casesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/cases",
  component: () => (
    <RequireAuth>
      <CasesListPage />
    </RequireAuth>
  ),
});

const caseDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/cases/$id",
  component: () => (
    <RequireAuth>
      <CaseDetailPage />
    </RequireAuth>
  ),
});

const caseRegisterRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/cases/register",
  component: () => (
    <RequireAuth>
      <CaseRegistrationPage />
    </RequireAuth>
  ),
});

const overlapRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/overlap",
  component: () => (
    <RequireAuth>
      <OverlapQueuePage />
    </RequireAuth>
  ),
});

const alertsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/alerts",
  component: () => (
    <RequireAuth>
      <AlertsPage />
    </RequireAuth>
  ),
});

const reportsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reports",
  component: () => (
    <RequireAuth>
      <ReportsPage />
    </RequireAuth>
  ),
});

const galleryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/dev/gallery",
  component: GalleryPage,
});

const routeTree = rootRoute.addChildren([
  signInRoute,
  homeRoute,
  securityRoute,
  adminUsersRoute,
  institutionsRoute,
  institutionProfileRoute,
  importRoute,
  casesRoute,
  caseRegisterRoute,
  caseDetailRoute,
  overlapRoute,
  alertsRoute,
  reportsRoute,
  galleryRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
