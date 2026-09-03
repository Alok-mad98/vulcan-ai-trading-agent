import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./Layout";
import Overview from "./pages/Overview";
import Positions from "./pages/Positions";
import Trades from "./pages/Trades";
import Agent from "./pages/Agent";
import Backtest from "./pages/Backtest";
import MonteCarlo from "./pages/MonteCarlo";
import Risk from "./pages/Risk";
import Data from "./pages/Data";
import "./index.css";

function Shell() {
  return (
    <Layout live={true} ts={new Date().toLocaleTimeString()}>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/trades" element={<Trades />} />
        <Route path="/agent" element={<Agent />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/montecarlo" element={<MonteCarlo />} />
        <Route path="/risk" element={<Risk />} />
        <Route path="/data" element={<Data />} />
      </Routes>
    </Layout>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </StrictMode>
);
