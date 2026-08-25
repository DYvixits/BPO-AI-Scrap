import { Navigate, createBrowserRouter } from "react-router-dom";

import { RequireAuth } from "@/app/RequireAuth";
import { AppLayout } from "@/layouts/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoginPage } from "@/pages/LoginPage";
import { NewResearchPage } from "@/pages/NewResearchPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { ResearchDetailPage } from "@/pages/ResearchDetailPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/dashboard", element: <DashboardPage /> },
          { path: "/research/new", element: <NewResearchPage /> },
          { path: "/research/:id", element: <ResearchDetailPage /> },
        ],
      },
    ],
  },
  { path: "/", element: <Navigate to="/dashboard" replace /> },
  { path: "*", element: <Navigate to="/dashboard" replace /> },
]);
