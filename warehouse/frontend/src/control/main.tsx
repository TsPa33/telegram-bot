import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Box,
  ChevronDown,
  ClipboardList,
  Globe,
  LayoutDashboard,
  LogOut,
  Menu,
  RefreshCw,
  Send,
  Share2,
  ShieldCheck,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { ThemeProvider, MobileThemeSwitch } from "../Theme";
import { api, type Row, type Staff } from "./api";
import { parseRoute } from "./model";
import {
  Empty,
  Feedback,
  Freshness,
  PageHeader,
  useLoad,
  useRevision,
} from "./shared";
import Login from "./Login";
import Directory from "./Directory";
import Overview from "./Overview";
import CompanyProfile from "./CompanyProfile";
import WorkQueue from "./Tasks";
import SecuritySettings from "./SecuritySettings";
import "../tokens.css";
import "../themes.css";
import "./style.css";
function useRoute() {
  const [hash, setHash] = useState(() => location.hash);
  useEffect(() => {
    const changed = () => setHash(location.hash);
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return { route: parseRoute(hash), hash };
}
function Workspace({
  staff,
  status,
  logout,
}: {
  staff: Staff;
  status: Row;
  logout: () => void;
}) {
  const { route, hash } = useRoute(),
    [revision, refresh] = useRevision(),
    overview = useLoad<Row>("/overview", revision),
    staffList = useLoad<Staff[]>(staff.can_assign ? "/staff" : null, revision);
  const [drawer, setDrawer] = useState(false),
    [clientsOpen, setClientsOpen] = useState(true),
    [compact, setCompact] = useState(
      () => matchMedia("(max-width:1100px)").matches,
    ),
    [error, setError] = useState(""),
    [signingOut, setSigningOut] = useState(false);
  const aside = useRef<HTMLElement>(null),
    content = useRef<HTMLDivElement>(null),
    menu = useRef<HTMLButtonElement>(null),
    main = useRef<HTMLElement>(null);
  useEffect(() => {
    const media = matchMedia("(max-width:1100px)"),
      change = () => {
        setCompact(media.matches);
        setDrawer(false);
      };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    const sidebar = aside.current,
      body = content.current;
    if (!sidebar || !body) return;
    sidebar.inert = compact && !drawer;
    body.inert = compact && drawer;
    if (!compact || !drawer) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () =>
      [
        ...sidebar.querySelectorAll<HTMLElement>(
          'a[href],button:not(:disabled),input,select,[tabindex="0"]',
        ),
      ].filter((e) => e.getClientRects().length);
    focusable()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setDrawer(false);
      }
      if (e.key === "Tab") {
        const all = focusable(),
          first = all[0],
          last = all.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      document.body.style.overflow = previous;
      body.inert = false;
      if (
        (sidebar.contains(document.activeElement) ||
          document.activeElement === document.body) &&
        menu.current?.getClientRects().length
      )
        menu.current.focus();
    };
  }, [compact, drawer]);
  useLayoutEffect(() => {
    setDrawer(false);
    if (content.current) content.current.inert = false;
    main.current
      ?.querySelector<HTMLElement>("h1")
      ?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [hash]);
  const active = route.view === "company" ? "clients" : route.view,
    title = {
      overview: "Огляд",
      clients: "Клієнти",
      company: "Профіль клієнта",
      queue: "Робоча черга",
      security: "Безпека та налаштування",
      missing: "Сторінка недоступна",
    }[route.view];
  const staffOptions = staffList.data || [];
  async function signOut() {
    setSigningOut(true);
    setError("");
    try {
      await api("/auth/logout", "POST");
      sessionStorage.removeItem("control.csrf");
      location.hash = "#/overview";
      logout();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSigningOut(false);
    }
  }
  return (
    <div className={"cc-shell " + (compact && drawer ? "drawer-open" : "")}>
      <a
        className="cc-skip"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          main.current?.focus();
        }}
      >
        До вмісту
      </a>
      <aside
        ref={aside}
        id="cc-sidebar-region"
        className="cc-sidebar"
        role={compact && drawer ? "dialog" : undefined}
        aria-modal={compact && drawer ? true : undefined}
        aria-label="Головне меню"
      >
        <button
          className="cc-drawer-close cc-icon-button"
          aria-label="Закрити меню"
          onClick={() => setDrawer(false)}
        >
          <X size={20} />
        </button>
        <a className="cc-brand" href="#/overview">
          <span className="cc-brandmark">
            C<span>→</span>
          </span>
          <span>
            CarPot<small>GLOBAL CRM</small>
          </span>
        </a>
        <div className="cc-workspace">
          <Box size={24} />
          <div>
            <strong>CarPot Workspace</strong>
            <small>Внутрішня команда</small>
          </div>
        </div>
        <nav className="cc-nav" aria-label="Global CRM">
          <p className="cc-nav-label">УПРАВЛІННЯ</p>
          <a
            href="#/overview"
            aria-current={active === "overview" ? "page" : undefined}
          >
            <LayoutDashboard size={18} /> Огляд
          </a>
          <button
            className={"cc-nav-group " + (active === "clients" ? "active" : "")}
            aria-expanded={clientsOpen}
            aria-controls="cc-client-menu"
            aria-current={
              active === "clients" && !clientsOpen ? "page" : undefined
            }
            onClick={() => setClientsOpen((v) => !v)}
          >
            <Users size={18} /> Клієнти
            <ChevronDown size={15} />
          </button>
          <div className="cc-submenu" id="cc-client-menu" hidden={!clientsOpen}>
            <a
              href="#/clients"
              aria-current={
                active === "clients" &&
                !route.query.get("status") &&
                !route.query.get("linking")
                  ? "page"
                  : undefined
              }
            >
              Усі клієнти
            </a>
            <a
              href="#/clients?status=EXPIRED"
              aria-current={
                active === "clients" && route.query.get("status") === "EXPIRED"
                  ? "page"
                  : undefined
              }
            >
              Завершені періоди
            </a>
            <a
              href="#/clients?status=UNKNOWN"
              aria-current={
                active === "clients" && route.query.get("status") === "UNKNOWN"
                  ? "page"
                  : undefined
              }
            >
              Недостатньо даних
            </a>
          </div>
          <a
            href="#/queue"
            aria-current={active === "queue" ? "page" : undefined}
          >
            <ClipboardList size={18} /> Робоча черга
          </a>
          <p className="cc-nav-label">ЕКОСИСТЕМА</p>
          <a href="#/clients">
            <Box size={18} /> Warehouse
          </a>
          {[
            { name: "Telegram / Garage", Icon: Send },
            { name: "Sites", Icon: Globe },
            { name: "Billing", Icon: Wallet },
            { name: "Реферальна програма", Icon: Share2 },
          ].map(({ name, Icon }) => (
            <button disabled key={name} title="Інтеграцію не підключено">
              <Icon size={18} />
              {name}
              <small>План</small>
            </button>
          ))}
        </nav>
        <div className="cc-sidebar-bottom">
          <a
            href="#/security"
            aria-current={active === "security" ? "page" : undefined}
          >
            <ShieldCheck size={18} /> Безпека та налаштування
          </a>
          <div className="cc-staff">
            <span className="cc-avatar">
              {staff.username.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong>{staff.username}</strong>
              <small>
                {(
                  {
                    Owner: "Власник",
                    Administrator: "Адміністратор",
                    Manager: "Менеджер",
                    Support: "Підтримка",
                  } as Record<string, string>
                )[staff.role] || staff.role}
              </small>
            </div>
            <button
              disabled={signingOut}
              className="cc-icon-button"
              onClick={() => void signOut()}
              aria-label="Вийти"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>
      {compact && drawer && (
        <button
          className="cc-scrim"
          tabIndex={-1}
          aria-label="Закрити бічну панель"
          onClick={() => setDrawer(false)}
        />
      )}
      <div className="cc-layout-main" ref={content}>
        <header className="cc-topbar">
          <button
            ref={menu}
            className="cc-menu-button cc-icon-button"
            aria-label="Відкрити меню"
            aria-expanded={drawer}
            aria-controls="cc-sidebar-region"
            onClick={() => setDrawer(true)}
          >
            <Menu size={20} />
          </button>
          <div className="cc-breadcrumbs">
            <a href="#/overview">Робочий простір</a>
            <span>/</span>
            <strong>{title}</strong>
          </div>
          <div className="cc-top-actions">
            <div className="cc-theme">
              <MobileThemeSwitch />
            </div>
            <span className="cc-environment">
              {overview.data?.preview
                ? "Demo"
                : status.environment || "Середовище невідоме"}
            </span>
            <button
              onClick={refresh}
              className="cc-refresh"
              aria-label="Оновити"
            >
              <RefreshCw size={16} />
              <span>Оновити</span>
            </button>
          </div>
        </header>
        <main ref={main} id="main" className="cc-main" tabIndex={-1}>
          <Feedback error={error} />
          {overview.data?.preview && (
            <p className="cc-preview-banner" role="status">
              Демонстраційні дані.{" "}
              {overview.data.source_configured
                ? "Warehouse Directory оновлюється автоматично."
                : "Реальне джерело ще не підключено."}
            </p>
          )}
          {route.view !== "clients" && (
            <Freshness source={overview.data?.source} />
          )}
          {route.view === "overview" && (
            <Overview
              overview={overview.data}
              loading={overview.loading}
              error={overview.error}
              retry={refresh}
              revision={revision}
            />
          )}{" "}
          {route.view === "clients" && (
            <Directory
              key={route.query.toString()}
              route={route}
              staff={staff}
              staffOptions={staffOptions}
              staffError={staffList.error}
              revision={revision}
            />
          )}{" "}
          {route.view === "company" && route.id && (
            <CompanyProfile
              key={route.id}
              id={route.id}
              section={route.section || "overview"}
              staff={staff}
              staffOptions={staffOptions}
              staffError={staffList.error}
              revision={revision}
            />
          )}{" "}
          {route.view === "queue" && <WorkQueue revision={revision} />}{" "}
          {route.view === "security" && (
            <>
              <PageHeader
                title="Безпека та налаштування"
                subtitle="Особистий доступ і корпоративне оформлення."
              />
              <SecuritySettings
                logout={logout}
                passwordOnly={status.auth_mode === "password-only"}
                canRotateMfa={staff.role === "Owner"}
              />
            </>
          )}{" "}
          {route.view === "missing" && (
            <>
              <PageHeader title="Сторінку не знайдено" />
              <Empty title="Цей розділ недоступний">
                <a href="#/overview">Повернутися до огляду</a>
              </Empty>
            </>
          )}
        </main>
        <footer className="cc-footer">
          <span>CarPot Global CRM</span>
          <span>Warehouse · час Києва</span>
        </footer>
      </div>
    </div>
  );
}
function App() {
  const [staff, setStaff] = useState<Staff | null>(null),
    [status, setStatus] = useState<Row | null>(null),
    [state, setState] = useState("loading");
  useEffect(() => {
    const reset = () => {
      setStaff(null);
      setState("ready");
    };
    window.addEventListener("control:session-invalid", reset);
    return () => window.removeEventListener("control:session-invalid", reset);
  }, []);
  useEffect(() => {
    api("/status")
      .then((s) => {
        setStatus(s);
        return api("/auth/me")
          .then((s) => {
            setStaff(s);
            setState("ready");
          })
          .catch(() => setState("ready"));
      })
      .catch(() => setState("disabled"));
  }, []);
  return (
    <ThemeProvider>
      <div className="cc-app">
        {state === "loading" ? (
          <main className="cc-login">
            <p role="status">Перевіряємо доступ…</p>
          </main>
        ) : state === "disabled" ? (
          <main className="cc-login">
            <section>
              <h1>Control Center недоступний</h1>
              <p>
                Контур вимкнено або сервіс не відповідає. Дані клієнтів не
                завантажено.
              </p>
            </section>
          </main>
        ) : staff ? (
          <Workspace
            key={staff.id}
            staff={staff}
            status={status || {}}
            logout={() => setStaff(null)}
          />
        ) : (
          <Login onLogin={setStaff} />
        )}
      </div>
    </ThemeProvider>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
