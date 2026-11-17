import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertCircle, Box, Clock3 } from "lucide-react";
import { api, date, states, coverageName, type Row } from "./api";
import { periodStatus } from "./model";
export function useLoad<T>(path: string | null, revision = 0) {
  const [state, setState] = useState<{
    key: string | null;
    data: T | null;
    error: string;
    loading: boolean;
  }>({ key: path, data: null, error: "", loading: Boolean(path) });
  useEffect(() => {
    let live = true;
    if (!path) {
      setState({ key: null, data: null, error: "", loading: false });
      return;
    }
    setState({ key: path, data: null, error: "", loading: true });
    api(path)
      .then((data) => {
        if (live) setState({ key: path, data, error: "", loading: false });
      })
      .catch((e) => {
        if (live)
          setState({
            key: path,
            data: null,
            error: e.message || "Не вдалося завантажити дані",
            loading: false,
          });
      });
    return () => {
      live = false;
    };
  }, [path, revision]);
  // Never display a previous company/page while a new request is waiting for effects.
  return state.key === path
    ? state
    : { key: path, data: null, error: "", loading: Boolean(path) };
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={"cc-pill " + tone}>{children}</span>;
}
export function PeriodBadge({ company }: { company: Row }) {
  const status = periodStatus(company);
  return (
    <Badge
      tone={
        ["ACTIVE", "TRIAL"].includes(status)
          ? "good"
          : status === "GRACE"
            ? "warn"
            : status === "EXPIRED"
              ? "danger"
              : "neutral"
      }
    >
      {states[status] || "Стан невідомий"}
    </Badge>
  );
}
export function ProductBadge() {
  return (
    <Badge>
      <Box size={13} /> Warehouse
    </Badge>
  );
}
export function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={"cc-panel " + className}>
      <header className="cc-panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}
export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="cc-page-head">
      <div>
        <small className="cc-eyebrow">CARPOT / РОБОТА З КЛІЄНТАМИ</small>
        <h1 tabIndex={-1}>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action && <div className="cc-actions">{action}</div>}
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="cc-empty">
      <Clock3 size={24} />
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}
export function Feedback({
  loading,
  error,
  retry,
}: {
  loading?: boolean;
  error?: string;
  retry?: () => void;
}) {
  return (
    <>
      {loading && (
        <p className="cc-loading" role="status">
          Завантажуємо дані…
        </p>
      )}
      {error && (
        <div className="cc-error" role="alert">
          <AlertCircle size={17} />
          <span>{error}</span>
          {retry && <button onClick={retry}>Спробувати ще</button>}
        </div>
      )}
    </>
  );
}
export function Freshness({ source }: { source: Row | undefined }) {
  if (!source) return null;
  return (
    <p className={"cc-source " + source.state} role="status">
      <span className="cc-source-dot" />
      {source.state === "fresh"
        ? "Джерело оновлено"
        : source.state === "stale"
          ? "Дані застаріли"
          : "Джерело недоступне"}{" "}
      · {coverageName[source.coverage] || "Неповне покриття"} ·{" "}
      {date(source.last_success)} · час Києва
    </p>
  );
}
export function useRevision() {
  const [revision, setRevision] = useState(0);
  return [revision, useCallback(() => setRevision((n) => n + 1), [])] as const;
}
export function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const el = ref.current;
    if (!open || !el) return;
    const launcher = document.activeElement as HTMLElement | null;
    el.showModal();
    const cancel = (e: Event) => {
      e.preventDefault();
      closeRef.current();
    };
    el.addEventListener("cancel", cancel);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      el.removeEventListener("cancel", cancel);
      el.close();
      document.body.style.overflow = previous;
      if (launcher?.isConnected) launcher.focus();
    };
  }, [open]);
  return ref;
}
