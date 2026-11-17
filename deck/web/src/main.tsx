import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import { PortsProvider } from "./ports/context";
import { realPorts } from "./ports/real";
import "./index.css";
import "./base.css";

const router = createBrowserRouter([{ path: "*", element: <App /> }]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PortsProvider ports={realPorts()}>
      <RouterProvider router={router} />
    </PortsProvider>
  </React.StrictMode>
);
