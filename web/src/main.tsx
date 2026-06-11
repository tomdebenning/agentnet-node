import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import App from "./App";
import { FleetPage } from "./FleetPage";
import { InteractivePage } from "./InteractivePage";
import { InstanceDetailPage } from "./InstanceDetailPage";
import {
  CreateDefinitionPage,
  DefinitionDetailPage,
  DefinitionsPage,
  SpawnInstancePage,
} from "./DefinitionsPage";
import { SpawnPickerPage } from "./SpawnPickerPage";
import "./index.css";

function LegacyDefinitionsRedirect() {
  const { pathname } = useLocation();
  return <Navigate to={pathname.replace(/^\/templates/, "/definitions")} replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <div className="layout">
        <header>
          <h1><Link to="/">Agentnet Node</Link></h1>
          <nav className="row">
            <Link to="/">Fleet</Link>
            <Link to="/definitions">Definitions</Link>
            <Link to="/instances/spawn">Spawn instance</Link>
            <Link className="button secondary" to="/definitions/new">New definition</Link>
            <Link className="button secondary" to="/instances/new">New instance</Link>
          </nav>
        </header>
        <Routes>
          <Route path="/" element={<FleetPage />} />
          <Route path="/definitions" element={<DefinitionsPage />} />
          <Route path="/definitions/new" element={<CreateDefinitionPage />} />
          <Route path="/definitions/:definitionId/spawn" element={<SpawnInstancePage />} />
          <Route path="/definitions/:definitionId" element={<DefinitionDetailPage />} />
          <Route path="/instances/spawn" element={<SpawnPickerPage />} />
          <Route path="/instances/:instanceId/interactive" element={<InteractivePage />} />
          <Route path="/instances/:instanceId" element={<InstanceDetailPage />} />
          <Route path="/instances/new" element={<App createMode />} />
          <Route path="/agents/new" element={<Navigate to="/instances/new" replace />} />
          <Route path="/agents/:agentId" element={<App detailMode redirectToInstance />} />
          <Route path="/templates/*" element={<LegacyDefinitionsRedirect />} />
        </Routes>
      </div>
    </BrowserRouter>
  </React.StrictMode>,
);
