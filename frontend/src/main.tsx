import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <div className="layout">
        <header>
          <h1><Link to="/">Agentnet Node</Link></h1>
          <Link className="button" to="/agents/new">New agent</Link>
        </header>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/agents/new" element={<App createMode />} />
          <Route path="/agents/:agentId" element={<App detailMode />} />
        </Routes>
      </div>
    </BrowserRouter>
  </React.StrictMode>,
);
