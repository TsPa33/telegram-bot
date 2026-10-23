import {
  Archive as ArchiveIcon,
  ArrowDownLeft,
  Boxes,
  CarFront,
  ChartNoAxesCombined,
  ChevronRight,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings2,
  Search,
  ShieldCheck,
  Warehouse,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { api, type Row } from "./api";

import Archive from "./pages/Archive";
import Audit from "./pages/Audit";
import Auth from "./pages/Auth";
import Catalog from "./pages/Catalog";
import Dashboard from "./pages/Dashboard";
import Inventory from "./pages/Inventory";
import SalesWorkspace from "./SalesWorkspace";
import Operations from "./pages/Operations";
import Settings from "./pages/Settings";
import Vehicles from "./pages/Vehicles";
const nav = [
  { to: "/", label: "Пошук запчастин", icon: Search },
  { to: "/vehicles", label: "Автомобілі", icon: CarFront },
  { to: "/inventory", label: "Склад", icon: Boxes },
  { to: "/statistics", label: "Статистика", icon: ChartNoAxesCombined },
];
const secondary = [
  {to:"/settings",label:"Налаштування"},
  {to:"/catalog",label:"Довідник запчастин"},
  {to:"/operations",label:"Журнал операцій"},
  {to:"/analytics",label:"Аудит"},
  {to:"/archive",label:"Архів"},
];

type Notify = (text: string) => void;
export default function App() {
  const [user, setUser] = useState<Row | null>(null),
    [checking, setChecking] = useState(true),
    [menu, setMenu] = useState(false),
    [toast, setToast] = useState("");
  const location = useLocation(),
    navigate = useNavigate();
  useEffect(() => {
    api("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
    const logout = () => setUser(null);
    window.addEventListener("warehouse:logout", logout);
    return () => window.removeEventListener("warehouse:logout", logout);
  }, []);
  useEffect(() => setMenu(false), [location.pathname]);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(""), 5000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  const notify: Notify = useCallback((text) => setToast(text), []);
  if (checking)
    return (
      <div className="boot">
        <Warehouse />
        <p>CarPot Warehouse</p>
        <span>Підготовка робочого простору…</span>
      </div>
    );
  if (!user)
    return (
      <Auth
        onLogin={(u) => {
          setUser(u);
          navigate("/");
        }}
      />
    );
  const current = [...nav,...secondary].find((n) => n.to === location.pathname);
  return (
    <div className="app">
      <aside className={menu ? "sidebar open" : "sidebar"}>
        <Link to="/" className="brand">
          <span className="brand-icon">
            <Warehouse size={23} />
          </span>
          <span>
            CarPot<strong>WAREHOUSE</strong>
          </span>
        </Link>
        <div className="workspace">
          <span className="workspace-letter">
            {user.name.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <b>Мій склад</b>
            <small>Робочий простір</small>
          </div>
          <ShieldCheck size={16} />
        </div>
        <div className="nav-label">УПРАВЛІННЯ</div>
        <nav>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end>
              <n.icon size={18} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <NavLink className="settings-nav" to="/settings"><Settings2 size={18}/>Налаштування</NavLink>
        <div className="sidebar-foot">
          <div className="safe-dot" />
          Незалежний облік складу<small>CarPot Warehouse · MVP</small>
        </div>
      </aside>
      {menu && (
        <button
          aria-label="Закрити меню"
          className="shade"
          onClick={() => setMenu(false)}
        />
      )}
      <div className="main">
        <header className="topbar">
          <div>
            <button
              aria-label="Відкрити меню"
              className="mobile-menu icon-button"
              onClick={() => setMenu(!menu)}
            >
              <Menu size={22} />
            </button>
            <span className="breadcrumb">
              Робочий простір <ChevronRight size={14} />
              <b>{current?.label || "Склад"}</b>
            </span>
          </div>
          <div className="user">
            <span className="avatar">
              {user.name.slice(0, 1).toUpperCase()}
            </span>
            <span>
              {user.name}
              <small>Власник облікового запису</small>
            </span>
            <button
              className="icon-button"
              title="Вийти"
              aria-label="Вийти"
              onClick={async () => {
                try {
                  await api("/auth/logout", "POST");
                  setUser(null);
                } catch (e) {
                  notify((e as Error).message);
                }
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<SalesWorkspace accountId={user.id} quick notify={notify}/>} />
            <Route path="/statistics" element={<Dashboard/>}/>
            <Route path="/vehicles" element={<Vehicles notify={notify} />} />
            <Route path="/catalog" element={<Catalog notify={notify} />} />
            <Route path="/inventory" element={<SalesWorkspace accountId={user.id} notify={notify}/>} />
            <Route path="/inventory/advanced" element={<Inventory notify={notify}/>} />
            <Route path="/search" element={<SalesWorkspace accountId={user.id} quick notify={notify}/>} />
            <Route
              path="/operations"
              element={<Operations notify={notify} />}
            />
            <Route path="/analytics" element={<Audit />} />
            <Route path="/archive" element={<Archive notify={notify} />} />
            <Route path="/settings" element={<Settings user={user} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <footer>
          CarPot Warehouse <span>Ваші дані. Ваш склад. Повний контроль.</span>
        </footer>
      </div>
      {toast && (
        <div className="toast" role="status">
          {toast}
          <button
            aria-label="Закрити повідомлення"
            onClick={() => setToast("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
