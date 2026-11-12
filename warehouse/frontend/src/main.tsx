import {ThemeProvider} from "./Theme";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./tokens.css";
import "./style.css";
import "./design-system.css";
import "./vehicle-cards.css";
import "./premium-emerald-r10.css";
import "./theme-surfaces.css";
import "./themes.css";
import "./corporate-ux-v2.css";
import "./integrated-ux-polish.css";
import "./mobile-search-checkout.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider><App /></ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
