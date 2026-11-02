import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider } from "./AuthContext";
import { router } from "./router";
import { TestSandboxBanner } from "./TestSandboxBanner";
import "./theme.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root element not found");

createRoot(root).render(
  <StrictMode>
    <AuthProvider>
      <TestSandboxBanner />
      <RouterProvider router={router} />
    </AuthProvider>
  </StrictMode>,
);
