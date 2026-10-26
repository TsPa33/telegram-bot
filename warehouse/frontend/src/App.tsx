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
import { useCallback, useEffect, useRef, useState } from "react";
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

import Team,{PasswordChange} from './Team';
import {TeamIdentity,allowed,roleLabel,identityKey,ADVANCED_PERMISSIONS} from './permissions';
import Archive from "./pages/Archive";
import Audit from "./pages/Audit";
import Auth from "./pages/Auth";
import Catalog from "./pages/Catalog";
import Dashboard from "./pages/Dashboard";
import Inventory from "./pages/Inventory";
import SalesWorkspace from "./SalesWorkspace";
import InventoryWorkspace from "./InventoryWorkspace";
import Orders from "./Orders";
import SalesLedger from "./SalesLedger";
import Operations from "./pages/Operations";
import Settings from "./pages/Settings";
import Vehicles from "./pages/Vehicles";
const nav = [
  { to: "/", label: "Пошук запчастин", icon: Search },
  { to: "/vehicles", label: "Автомобілі", icon: CarFront },
  { to: "/inventory", label: "Склад", icon: Boxes },
  { to: "/sales", label: "Продажі", icon: ArrowDownLeft },
  { to: "/orders", label: "Замовлення", icon: ClipboardList },
  { to: "/statistics", label: "Статистика", icon: ChartNoAxesCombined },
];
const secondary = [
  {to:"/team",label:"Команда"},
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
  const [accessUnverified,setAccessUnverified]=useState(false);
  const currentUser=useRef<Row|null>(null),generation=useRef(0),inFlight=useRef(0);
  const retryIdentity=useRef<(force?:boolean)=>void>(()=>{});
  const changeUser=useCallback((next:Row|null)=>{
    generation.current++;inFlight.current=0;currentUser.current=next;
    setUser(next);setAccessUnverified(false);setToast('');
  },[]);
  useEffect(() => {
    let mounted=true;
    async function refresh(force=false){
      if(inFlight.current&&!force)return;
      const ticket=++generation.current;inFlight.current=ticket;
      // Preserve a failed form until rights are verified. Remounting on every
      // unrelated 403 (e.g. CSRF) could repeatedly trigger mount-time requests.
      // A changed identity key still discards every protected cache atomically.
      try{
        const next=await api('/auth/me');
        if(mounted&&ticket===generation.current){
          if(identityKey(next)!==identityKey(currentUser.current))setToast('');
          currentUser.current=next;setUser(next);setAccessUnverified(false);if(force)setToast('Права доступу перевірено. Доступні дії оновлено.');
        }
      }catch(error){
        if(mounted&&ticket===generation.current){
          if((error as {status?:number}).status===401)changeUser(null);
          else setAccessUnverified(true);
        }
      }finally{
        if(inFlight.current===ticket)inFlight.current=0;
        if(mounted)setChecking(false);
      }
    }
    retryIdentity.current=refresh;
    const focus=()=>{if(currentUser.current)void refresh();};
    const permissions=()=>{if(currentUser.current)void refresh(true);};
    const visible=()=>{if(document.visibilityState==='visible')focus();};
    const logout=()=>changeUser(null);
    void refresh();
    window.addEventListener('focus',focus);
    document.addEventListener('visibilitychange',visible);
    window.addEventListener('warehouse:permissions-changed',permissions);
    window.addEventListener('warehouse:logout',logout);
    const timer=setInterval(focus,30000);
    return ()=>{
      mounted=false;generation.current++;clearInterval(timer);
      window.removeEventListener('focus',focus);
      document.removeEventListener('visibilitychange',visible);
      window.removeEventListener('warehouse:permissions-changed',permissions);
      window.removeEventListener('warehouse:logout',logout);
    };
  },[changeUser]);
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
          changeUser(u);
          navigate("/");
        }}
      />
    );
  if(user.must_change_password)return <PasswordChange user={user} onDone={()=>changeUser(null)}/>;
  const can=(p:string)=>allowed(user,p);
  const routePermission=(path:string)=>path==='/settings'?'':path==='/inventory/advanced'||path==='/operations'?'inventory.adjust_quantity':path.startsWith('/team')?'team.view':path.startsWith('/orders')?'orders.view':path==='/vehicles'?'vehicles.view':path==='/statistics'?'analytics.view':path==='/sales'?'sales.view':path==='/catalog'?'catalog.view':path==='/analytics'||path==='/operations'?'audit.view':path==='/archive'?'inventory.archive':'inventory.view';
  const advanced=ADVANCED_PERMISSIONS;
  const routeAllowed=(!routePermission(location.pathname)||can(routePermission(location.pathname)))&&(!['/inventory/advanced','/operations'].includes(location.pathname)||advanced.every(can))&&(location.pathname!=='/archive'||can('inventory.view'));
  const current = [...nav,...secondary].find((n) => n.to === location.pathname || (n.to === "/orders" && location.pathname.startsWith("/orders/")));
  return (
    <TeamIdentity.Provider value={user}><div className="app">
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
            <b>{user.workspace_name||'Мій склад'}</b>
            <small>Робочий простір</small>
          </div>
          <ShieldCheck size={16} />
        </div>
        <div className="nav-label">УПРАВЛІННЯ</div>
        <nav>
          {nav.filter(n=>can(routePermission(n.to))).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to!=="/orders"}>
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
              <small>{roleLabel(user.role)} · {user.workspace_name||'Мій склад'}</small>
            </span>
            <button
              className="icon-button"
              title="Вийти"
              aria-label="Вийти"
              onClick={async () => {
                try {
                  await api("/auth/logout", "POST");
                  changeUser(null);
                } catch (e) {
                  notify((e as Error).message);
                }
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <div className="team-identity-line" role="region" aria-label="Працівник і склад"><strong>{user.name}</strong><span>{roleLabel(user.role)} · {user.workspace_name||'Мій склад'}</span></div>
        <main key={identityKey(user)}>
          {accessUnverified?<section className="panel padded"><h1>Перевіряємо доступ</h1><p>Дані приховані, доки сервер не підтвердить ваші поточні права.</p><button onClick={()=>retryIdentity.current(true)}>Перевірити доступ</button></section>:!routeAllowed?<section className="panel padded"><h1>Доступ обмежено</h1><p>Зверніться до директора для надання дозволу.</p></section>:<Routes>
            <Route path="/team" element={<Team user={user} notify={notify}/>}/>
            <Route path="/" element={<SalesWorkspace accountId={user.id} quick notify={notify}/>} />
            <Route path="/sales" element={<SalesLedger/>}/>
            <Route path="/orders" element={<Orders key={user.id} accountId={user.id} notify={notify}/>} />
            <Route path="/orders/:id" element={<Orders key={user.id} accountId={user.id} notify={notify}/>} />
            <Route path="/statistics" element={<Dashboard/>}/>
            <Route path="/vehicles" element={<Vehicles notify={notify} />} />
            <Route path="/catalog" element={<Catalog notify={notify} />} />
            <Route path="/inventory" element={<InventoryWorkspace key={user.id} accountId={user.id} notify={notify}/>} />
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
          </Routes>}
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
    </div></TeamIdentity.Provider>
  );
}
