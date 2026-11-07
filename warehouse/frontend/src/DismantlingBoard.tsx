import {
  Fragment,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, type Row } from "./api";
import { TeamIdentity, useCan } from "./permissions";
import PartCharacteristicsEditor from "./PartCharacteristicsEditor";
import {
  Package,
  Layers,
  Camera,
  Search,
  Pencil,
  ChevronDown,
  Copy,
  Plus,
  Languages,
  Check,
  EyeOff,
  RotateCcw,
} from "lucide-react";
import "./dismantling-board.css";
const status: Record<string, string> = {
  planned: "Заплановано",
  dismantled: "Демонтовано",
  received: "На складі",
  sold: "Продано",
  hidden: "Приховано з плану",
  empty: "Без залишку",
};
export default function DismantlingBoard({
  vehicle,
  source,
  controls,
  onUpdate,
  onModify,
  onOpenPart,
  translationKick = 0,
  revision,
  onTranslationConsumed,
}: {
  vehicle: Row;
  source: "base" | "professional";
  controls: ReactNode;
  onUpdate?: () => Promise<void>;
  onModify?: () => void;
  onOpenPart: (id: string) => void;
  translationKick?: number;
  revision?: string;
  onTranslationConsumed?: () => void;
}) {
  const [page, setPage] = useState(0);
  const [articleChoice, setArticleChoice] = useState<Record<string, number>>(
    {},
  );
  const [offerLimits, setOfferLimits] = useState<Record<string, number>>({});
  const who = useContext(TeamIdentity),
    can = useCan(),
    scope = JSON.stringify([
      who?.id,
      who?.workspace_account_id,
      vehicle.id,
      source,
      vehicle.ktype,
    ]),
    path =
      "/vehicles/" + encodeURIComponent(vehicle.id) + "/dismantling-workspace";
  const [data, setData] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [category, setCategory] = useState(""),
    [q, setQ] = useState(""),
    [state, setState] = useState(""),
    [stock, setStock] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [limit, setLimit] = useState(60),
    [expanded, setExpanded] = useState<string | null>(null),
    [offers, setOffers] = useState<Record<string, Row[]>>({}),
    [loadingOffer, setLoadingOffer] = useState(""),
    [editing, setEditing] = useState(""),
    [name, setName] = useState(""),
    [modifying, setModifying] = useState(false),
    [auto, setAuto] = useState(true),
    [translation, setTranslation] = useState<Row | null>(null),
    [confirmStock, setConfirmStock] = useState<string[] | null>(null),
    [location, setLocation] = useState(""),
    [quote, setQuote] = useState<Row | null>(null),
    [progress, setProgress] = useState<Row | null>(null),
    [target, setTarget] = useState<Record<string, string>>({});
  const epoch = useRef(0),
    writing = useRef(false),
    translating = useRef(false),
    stop = useRef(false),
    kickSeen = useRef(0),
    offerTicket = useRef(0);
  const rows: Row[] = data?.items || [],
    current = rows.find((r) => r.key === expanded),
    chosen = new Set(selected),
    filtered = rows.filter(
      (r) =>
        (!category || r.category === category) &&
        (!q ||
          [
            r.name,
            r.original,
            ...r.parts.flatMap((p: Row) => [
              p.article_number,
              p.article_brand,
              p.oem_number,
            ]),
          ].some((t) =>
            String(t || "")
              .toLocaleLowerCase("uk-UA")
              .includes(q.toLocaleLowerCase("uk-UA")),
          )) &&
        (state ? r.state === state : r.state !== "sold") &&
        (!stock ||
          (stock === "yes" && r.received) ||
          (stock === "no" && !r.received)),
    );
  const categories = [...new Set(rows.map((r) => r.category))],
    metrics = data?.progress || {},
    names = data?.translation || {};
  async function load(g = epoch.current) {
    const r = await api(path + "?source=" + source);
    if (g === epoch.current) setData(r);
    return r;
  }
  useEffect(() => {
    const g = ++epoch.current;
    setData(null);
    setError("");
    setSelected([]);
    setExpanded(null);
    setOffers({});
    setArticleChoice({});
    setQuote(null);
    setCategory("");
    setQ("");
    setState("");
    setStock("");
    setTranslation(null);
    setEditing("");
    setName("");
    setConfirmStock(null);
    setLocation("");
    setTarget({});
    setNotice("");
    setProgress(null);
    setLoadingOffer("");
    offerTicket.current++;
    setOfferLimits({});
    setPage(0);
    setModifying(false);
    stop.current = false;
    try {
      setAuto(localStorage.getItem("warehouse.translation:" + scope) !== "off");
    } catch {}
    load(g).catch((e) => {
      if (g === epoch.current) setError(e.message);
    });
    return () => {
      epoch.current++;
      stop.current = true;
    };
  }, [scope]);
  useEffect(() => {
    if (data) void load().catch((e) => setError(e.message));
  }, [revision]);
  useEffect(() => {
    setPage(0);
  }, [q, category, state, stock]);
  useEffect(() => {
    const refresh = () => {
      void load().catch((e) => setError(e.message));
    };
    window.addEventListener("warehouse:inventory-changed", refresh);
    return () =>
      window.removeEventListener("warehouse:inventory-changed", refresh);
  }, [scope]);
  async function run(fn: (g: number) => Promise<void>) {
    if (writing.current) return;
    writing.current = true;
    setBusy(true);
    setError("");
    stop.current = false;
    const g = epoch.current;
    try {
      await fn(g);
    } catch (e) {
      if (g === epoch.current) setError((e as Error).message);
    } finally {
      writing.current = false;
      setBusy(false);
      if (g === epoch.current) setProgress(null);
    }
  }
  function select(keys: string[], checked: boolean) {
    setSelected((old) =>
      checked
        ? [...new Set([...old, ...keys])]
        : old.filter((k) => !keys.includes(k)),
    );
  }
  async function annotate(keys: string[], action: string, manualName?: string) {
    await run(async (g) => {
      for (let n = 0; n < keys.length; n += 1000) {
        if (g !== epoch.current || stop.current) break;
        await api(path + "/annotations", "POST", {
          source,
          keys: keys.slice(n, n + 1000),
          action,
          ...(manualName ? { name: manualName } : {}),
        });
      }
      await load(g);
      if (g === epoch.current) {
        setEditing("");
        setNotice(
          action === "rename"
            ? "Українську назву збережено"
            : "План оновлено. Складські залишки не змінені.",
        );
      }
    });
  }
  async function translate() {
    if (translating.current || who?.role !== "DIRECTOR") return;
    translating.current = true;
    const g = epoch.current,
      keys = rows
        .filter((r) => !r.translated || r.name_source === "glossary")
        .map((r) => r.key);
    setError("");
    stop.current = false;
    try {
      for (let n = 0; n < keys.length; n += 40) {
        if (stop.current || g !== epoch.current) break;
        setTranslation({ done: n, total: keys.length });
        const r = await api(path + "/translations", "POST", {
          source,
          keys: keys.slice(n, n + 40),
        });
        await load(g);
        if (!r.configured) {
          if (g === epoch.current)
            setNotice(
              "Автоматичний переклад не налаштовано. Доступні словник і ручне виправлення.",
            );
          break;
        }
        if (g === epoch.current)
          setTranslation({
            done: Math.min(n + 40, keys.length),
            total: keys.length,
          });
      }
      if (!keys.length) await load(g);
    } catch (e) {
      if (g === epoch.current) setError((e as Error).message);
    } finally {
      translating.current = false;
      if (g === epoch.current) setTranslation(null);
    }
  }
  useEffect(() => {
    if (
      data &&
      auto &&
      translationKick &&
      translationKick !== kickSeen.current
    ) {
      kickSeen.current = translationKick;
      onTranslationConsumed?.();
      void translate();
    }
  }, [data, translationKick, auto]);
  async function open(row: Row) {
    setExpanded((old) => (old === row.key ? null : row.key));
    setQuote(null);
    setEditing("");
    if (offers[row.key] !== undefined || !row.pt_id) return;
    const g = epoch.current,
      ticket = ++offerTicket.current;
    setLoadingOffer(row.key);
    try {
      const r = await api(
        "/plan-parts/articles/recover?vehicle_id=" +
          vehicle.id +
          "&ktype=" +
          vehicle.ktype +
          "&pt_id=" +
          row.pt_id,
        "POST",
      );
      if (g === epoch.current)
        setOffers((old) => ({ ...old, [row.key]: r.articles }));
    } catch (e) {
      if (
        g === epoch.current &&
        ticket === offerTicket.current &&
        (e as { status?: number }).status !== 409
      )
        setError((e as Error).message);
    } finally {
      if (g === epoch.current && ticket === offerTicket.current)
        setLoadingOffer("");
    }
  }
  function partFor(row: Row) {
    return row.parts.length === 1
      ? row.parts[0]
      : row.parts.find((p: Row) => p.id === target[row.key]);
  }
  async function assign(row: Row, offer: Row) {
    await run(async (g) => {
      let p = partFor(row);
      if (!p && row.parts.length)
        throw Error("Виберіть конкретну складську картку");
      if (!p) {
        const created = await api(
          "/plan-parts/donor-parts/add?vehicle_id=" + vehicle.id,
          "POST",
          { ktype: vehicle.ktype, pt_id: row.pt_id, ukrainian_name: row.name },
        );
        p = await api("/parts/" + created.part_id);
      }
      await api(
        "/plan-parts/donor-parts/article/select?vehicle_id=" + vehicle.id,
        "POST",
        {
          ktype: vehicle.ktype,
          pt_id: row.pt_id,
          part_id: p.id,
          art_id: offer.art_id,
          expected_article_number: p.article_number || "",
          expected_article_brand: p.article_brand || "",
        },
      );
      await load(g);
      if (g === epoch.current) {
        setExpanded(null);
        setNotice("Артикул і виробника збережено в складській картці.");
        window.dispatchEvent(new Event("warehouse:inventory-changed"));
      }
    });
  }
  async function requestArticles(row: Row) {
    await run(async (g) => {
      const key = "warehouse.article:" + scope + ":" + row.key;
      let id = sessionStorage.getItem(key);
      if (!id) {
        id = crypto.randomUUID();
        sessionStorage.setItem(key, id);
      }
      const r = await api(
        "/plan-parts/articles/lookup?vehicle_id=" +
          vehicle.id +
          "&ktype=" +
          vehicle.ktype +
          "&pt_id=" +
          row.pt_id +
          "&request_key=" +
          id +
          "&confirm_paid=true&max_tokens=" +
          quote?.cost +
          (offers[row.key] !== undefined ? "&force_paid=true" : ""),
        "POST",
      );
      sessionStorage.removeItem(key);
      if (g === epoch.current) {
        setOffers((old) => ({ ...old, [row.key]: r.articles }));
        setQuote(null);
        await load(g);
      }
    });
  }
  async function prepareQuote(row: Row) {
    const w = await api("/plan-parts/workspace?vehicle_id=" + vehicle.id);
    setQuote({
      key: row.key,
      cost: w.policy.max_tokens?.articles,
      allowed: w.policy.terms_confirmed,
    });
  }
  async function addToStock() {
    const keys = confirmStock || [];
    setConfirmStock(null);
    await run(async (g) => {
      try {
        for (let n = 0; n < keys.length; n++) {
          if (g !== epoch.current || stop.current) break;
          const row = rows.find((r) => r.key === keys[n]);
          if (!row || row.received || ["sold", "hidden"].includes(row.state))
            continue;
          setProgress({ done: n, total: keys.length });
          let p = partFor(row);
          if (row.parts.length > 1 && !p)
            throw Error(
              "Уточніть конкретну складську картку перед переміщенням",
            );
          if (!p) {
            if (source !== "professional")
              throw Error(
                "Позиція не має складської картки. Сформуйте або оновіть план.",
              );
            const r = await api(
              "/plan-parts/donor-parts/add?vehicle_id=" + vehicle.id,
              "POST",
              {
                ktype: vehicle.ktype,
                pt_id: row.pt_id,
                ukrainian_name: row.name,
              },
            );
            p = await api("/parts/" + r.part_id);
          }
          if (!row.parts.length) {
            let variants = offers[row.key];
            if (variants === undefined) {
              try {
                const saved = await api(
                  "/plan-parts/articles/recover?vehicle_id=" +
                    vehicle.id +
                    "&ktype=" +
                    vehicle.ktype +
                    "&pt_id=" +
                    row.pt_id,
                  "POST",
                );
                variants = saved.articles;
              } catch (e) {
                if ((e as { status?: number }).status !== 409) throw e;
              }
            }
            const chosen =
              variants?.find((a: Row) => a.art_id === articleChoice[row.key]) ||
              variants?.[0];
            if (chosen)
              await api(
                "/plan-parts/donor-parts/article/select?vehicle_id=" +
                  vehicle.id,
                "POST",
                {
                  ktype: vehicle.ktype,
                  pt_id: row.pt_id,
                  part_id: p.id,
                  art_id: chosen.art_id,
                  expected_article_number: p.article_number || "",
                  expected_article_brand: p.article_brand || "",
                },
              );
          }
          if (p.quantity <= 0)
            throw Error(
              "Позиція має нульовий залишок. Уточніть його через картку складу.",
            );
          const intent =
            "warehouse.shelf:" + scope + ":" + p.id + ":" + location;
          let requestKey = sessionStorage.getItem(intent);
          if (!requestKey) {
            requestKey = crypto.randomUUID();
            sessionStorage.setItem(intent, requestKey);
          }
          await api("/parts/" + p.id + "/operations", "POST", {
            type: "transfer",
            quantity: 0,
            location: location.trim() || "Склад (місце не уточнено)",
            physical_location_kind: "on_shelf",
            reason:
              "Явне підтвердження переміщення лота на склад із плану розбору",
            request_key: requestKey,
          });
          sessionStorage.removeItem(intent);
        }
        if (g === epoch.current) {
          setSelected([]);
          setNotice("Склад оновлено. Наявні кількості й ціни збережено.");
        }
      } finally {
        await load(g);
        window.dispatchEvent(new Event("warehouse:inventory-changed"));
      }
    });
  }
  useEffect(() => {
    if (confirmStock)
      document
        .querySelector('.wd-confirm[aria-label="Підтвердження складу"]')
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [confirmStock]);
  useEffect(() => {
    if (error)
      document
        .querySelector(".wd-board .wd-error")
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [error]);
  const canAdd = (row: Row) =>
    row.parts.length ? can("inventory.transfer") : can("inventory.create");
  const actionKeys = selected.length ? selected : [],
    canManage = can("dismantling.manage") && !vehicle.archived;
  if (!data)
    return <p role="status">{error || "Відкриваємо збережений список…"}</p>;
  return (
    <section className="wd-board" aria-label="Єдиний план розбору">
      <section className="wd-progress" aria-label="Стан розбору автомобіля">
        <div>
          <strong>Стан розбору автомобіля</strong>
          <small>
            Продані деталі — у фільтрі «Продано». Збережені записи залишаються
            доступними.
          </small>
        </div>
        {[
          [metrics.planned, "Заплановано", Package],
          [rows.filter((r) => r.state === "sold").length, "Продано", Layers],
          [metrics.with_photo, "З фото", Camera],
        ].map(([n, label, Icon]: any) => (
          <div className="wd-metric" key={label}>
            <Icon size={25} />
            <span>
              <b>{n}</b>
              <small>{label}</small>
            </span>
          </div>
        ))}
      </section>
      <div className="wd-modification">
        <div>
          <small>Модифікація</small>
          <strong>
            {vehicle.engine || "Потребує уточнення"}
            {vehicle.fuel_type ? " · " + vehicle.fuel_type : ""}
          </strong>
        </div>
        <div className="wd-saved">
          <Check size={21} />
          <span>
            <strong>Список запчастин сформовано</strong>
            <small>{rows.length} позицій · Список збережено</small>
          </span>
        </div>
        <button
          onClick={() =>
            void run(async (g) => {
              if (onUpdate) {
                await onUpdate();
                document
                  .querySelector('[aria-label="Попередній аналіз запчастин"]')
                  ?.scrollIntoView({ block: "nearest" });
              } else {
                await api(
                  "/plan-parts/categories/recover?vehicle_id=" +
                    vehicle.id +
                    "&ktype=" +
                    vehicle.ktype,
                  "POST",
                );
                await load(g);
              }
            })
          }
        >
          Оновити список
        </button>
        <button
          onClick={() => (onModify ? onModify() : setModifying(!modifying))}
        >
          Змінити модифікацію
        </button>
      </div>
      {modifying && <div className="wd-source-controls">{controls}</div>}
      {error && (
        <p className="wd-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="wd-notice" role="status">
          {notice}
        </p>
      )}
      <nav className="wd-categories" aria-label="Категорії CarPot">
        <button aria-pressed={!category} onClick={() => setCategory("")}>
          Усі ({rows.length})
        </button>
        {categories.slice(0, 5).map((c) => (
          <button
            key={c}
            aria-pressed={category === c}
            onClick={() => setCategory(c)}
          >
            <Package size={17} />
            {c} ({rows.filter((r) => r.category === c).length})
          </button>
        ))}
        {categories.length > 5 && (
          <details>
            <summary>
              Інші категорії <ChevronDown size={16} />
            </summary>
            <div>
              {categories.slice(5).map((c) => (
                <button
                  key={c}
                  aria-pressed={category === c}
                  onClick={(e) => {
                    setCategory(c);
                    e.currentTarget.closest("details")?.removeAttribute("open");
                  }}
                >
                  {c} ({rows.filter((r) => r.category === c).length})
                </button>
              ))}
            </div>
          </details>
        )}
      </nav>
      <div className="wd-layout">
        <section className="wd-list">
          <div className="wd-list-heading">
            <h3>
              {category || "Усі запчастини"} ({filtered.length})
            </h3>
            <label>
              <input
                type="checkbox"
                checked={auto}
                onChange={(e) => {
                  setAuto(e.target.checked);
                  try {
                    localStorage.setItem(
                      "warehouse.translation:" + scope,
                      e.target.checked ? "on" : "off",
                    );
                  } catch {}
                }}
              />
              Автопереклад назв
            </label>
          </div>
          <div className="wd-filters">
            <label>
              <Search size={17} />
              <input
                aria-label="Пошук деталей плану"
                placeholder="Пошук запчастин, OEM або артикулу…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </label>
            <select
              aria-label="Наявність на складі"
              value={stock}
              onChange={(e) => setStock(e.target.value)}
            >
              <option value="">Склад: усі</option>
              <option value="yes">На складі</option>
              <option value="no">Ще не додано на склад</option>
            </select>
            <select
              aria-label="Стан деталей плану"
              value={state}
              onChange={(e) => setState(e.target.value)}
            >
              <option value="">Стан: усі</option>
              {Object.entries(status).map(([k, v]) => (
                <option key={k} value={k}>
                  {k === "sold" ? "Архів — продані" : v}
                </option>
              ))}
            </select>
          </div>
          <div className="wd-table">
            <div className="wd-row wd-th">
              <input
                aria-label="Вибрати всі відфільтровані позиції"
                type="checkbox"
                checked={
                  filtered.length > 0 &&
                  filtered.every((r) => chosen.has(r.key))
                }
                onChange={(e) =>
                  select(
                    filtered.map((r) => r.key),
                    e.target.checked,
                  )
                }
              />
              <span>Назва запчастини</span>
              <span>Статус</span>
              <span>OEM номер</span>
              <span>Артикул / виробник</span>
              <span>Дії</span>
            </div>
            {filtered.slice(page * 10, page * 10 + 10).map((row) => {
              const p = partFor(row),
                count =
                  row.receipt?.saved_count ??
                  row.receipt?.article_count ??
                  offers[row.key]?.length ??
                  0;
              return (
                <Fragment key={row.key}>
                  <article
                    className={
                      "wd-row" + (chosen.has(row.key) ? " selected" : "")
                    }
                    data-entry-key={row.key}
                    aria-label={
                      row.name + (row.position ? " · " + row.position : "")
                    }
                  >
                    <input
                      type="checkbox"
                      aria-label={"Вибрати " + row.name + " " + row.position}
                      checked={chosen.has(row.key)}
                      onChange={(e) => select([row.key], e.target.checked)}
                    />
                    <div className="wd-name">
                      <Package size={22} />
                      <div>
                        <strong>
                          {row.name}
                          {row.position ? " · " + row.position : ""}
                        </strong>
                        <small>
                          {row.original !== row.name
                            ? row.original
                            : row.category}
                        </small>
                      </div>
                      <button
                        className="wd-icon"
                        aria-label={"Змінити назву " + row.name}
                        disabled={!canManage}
                        onClick={() => {
                          setEditing(row.key);
                          setName(row.name);
                          setExpanded(row.key);
                        }}
                      >
                        <Pencil size={13} />
                      </button>
                    </div>
                    <div>
                      <span className={"wd-chip " + row.state}>
                        {status[row.state]}
                      </span>
                      {row.state === "planned" && (
                        <small>Наявність перевірити</small>
                      )}
                    </div>
                    <div className="wd-oem">
                      {p?.oem_number ? (
                        <button
                          className="wd-code"
                          title="Скопіювати OEM"
                          onClick={() =>
                            void navigator.clipboard
                              ?.writeText(p.oem_number)
                              .catch(() =>
                                setError("Не вдалося скопіювати номер"),
                              )
                          }
                        >
                          {p.oem_number}
                          <Copy size={13} />
                        </button>
                      ) : (
                        <span className="wd-muted">OEM не визначено</span>
                      )}
                      <button
                        className="wd-link"
                        disabled={
                          !can("inventory.edit") ||
                          (!p && !can("inventory.create"))
                        }
                        onClick={() =>
                          void run(async (g) => {
                            if (!p) {
                              if (
                                !window.confirm(
                                  "Створити складську картку: 1 шт., і ввести OEM вручну?",
                                )
                              )
                                return;
                              await api(
                                "/plan-parts/donor-parts/add?vehicle_id=" +
                                  vehicle.id,
                                "POST",
                                {
                                  ktype: vehicle.ktype,
                                  pt_id: row.pt_id,
                                  ukrainian_name: row.name,
                                },
                              );
                              await load(g);
                              window.dispatchEvent(
                                new Event("warehouse:inventory-changed"),
                              );
                            }
                            setExpanded(row.key);
                            setEditing("oem:" + row.key);
                          })
                        }
                      >
                        {p ? "Ввести OEM" : "Додати 1 шт. і ввести OEM"}
                      </button>
                    </div>
                    <div>
                      <button
                        className="wd-article"
                        onClick={() => void open(row)}
                      >
                        <span>
                          {p?.article_number ? (
                            <>
                              <b>{p.article_number}</b> ·{" "}
                              {p.article_brand || "Виробник не вказаний"}
                            </>
                          ) : offers[row.key]?.length ? (
                            (() => {
                              const a =
                                offers[row.key].find(
                                  (a: Row) =>
                                    a.art_id === articleChoice[row.key],
                                ) || offers[row.key][0];
                              return (
                                <>
                                  <b>{a.article_nr}</b> · {a.brand}
                                  <small>Попередній вибір — не збережено</small>
                                </>
                              );
                            })()
                          ) : (
                            "Відкрити артикули"
                          )}
                          <small>
                            {count > 0
                              ? "Збережені артикули (" + count + ")"
                              : "Переглянути артикули"}
                          </small>
                        </span>
                        <ChevronDown size={15} />
                      </button>
                    </div>
                    <div className="wd-row-actions">
                      <button
                        disabled={
                          !canAdd(row) ||
                          busy ||
                          ["received", "sold", "hidden", "empty"].includes(
                            row.state,
                          )
                        }
                        onClick={() => setConfirmStock([row.key])}
                      >
                        <Plus size={14} />
                        На склад
                      </button>
                      {p && (
                        <button
                          className="wd-icon"
                          aria-label={"Картка " + row.name}
                          onClick={() => onOpenPart(p.id)}
                        >
                          •••
                        </button>
                      )}
                    </div>
                  </article>
                  {expanded === row.key && (
                    <div
                      className="wd-inline"
                      aria-label={"Номери " + row.name}
                    >
                      <div className="wd-inline-heading">
                        <strong>{row.name}: OEM та артикули</strong>
                        <button
                          onClick={() => {
                            setExpanded(null);
                            setQuote(null);
                            setEditing("");
                          }}
                        >
                          Згорнути
                        </button>
                      </div>
                      {editing === row.key && (
                        <form
                          onSubmit={(e) => {
                            e.preventDefault();
                            void annotate([row.key], "rename", name);
                          }}
                        >
                          <label>
                            Українська назва
                            <input
                              aria-label="Українська назва деталі"
                              maxLength={200}
                              value={name}
                              onChange={(e) => setName(e.target.value)}
                            />
                          </label>
                          <button disabled={busy}>Зберегти назву</button>
                        </form>
                      )}
                      {row.parts.length > 1 && (
                        <label>
                          Складська картка
                          <select
                            aria-label="Складська картка для артикула"
                            value={target[row.key] || ""}
                            onChange={(e) =>
                              setTarget((old) => ({
                                ...old,
                                [row.key]: e.target.value,
                              }))
                            }
                          >
                            <option value="">Оберіть явно</option>
                            {row.parts.map((part: Row, index: number) => (
                              <option key={part.id} value={part.id}>
                                {index + 1}. {part.name} ·{" "}
                                {part.article_number || "без номера"} ·{" "}
                                {part.quantity} шт.
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                      {editing === "oem:" + row.key && p && (
                        <PartCharacteristicsEditor
                          part={p}
                          kind="oem"
                          onSaved={() => {
                            void load();
                            setEditing("");
                            window.dispatchEvent(
                              new Event("warehouse:inventory-changed"),
                            );
                          }}
                          onClose={() => setEditing("")}
                        />
                      )}
                      <p className="wd-hint">
                        Автоматичне отримання OEM недоступне. Введіть номер
                        вручну та перевірте його відповідність автомобілю.
                      </p>
                      {loadingOffer === row.key ? (
                        <p role="status">
                          Відкриваємо збережені артикули · без токенів…
                        </p>
                      ) : (
                        <>
                          {offers[row.key]?.length ? (
                            <div className="wd-offers">
                              {offers[row.key]
                                .slice(0, offerLimits[row.key] || 100)
                                .map((a) => (
                                  <div key={a.art_id}>
                                    <input
                                      type="radio"
                                      aria-label={
                                        "Вибрати артикул " + a.article_nr
                                      }
                                      name={"article-" + row.key}
                                      checked={
                                        (articleChoice[row.key] ??
                                          offers[row.key][0]?.art_id) ===
                                        a.art_id
                                      }
                                      onChange={() =>
                                        setArticleChoice((v) => ({
                                          ...v,
                                          [row.key]: a.art_id,
                                        }))
                                      }
                                    />
                                    <span>
                                      <b>{a.article_nr}</b> · {a.brand}
                                      <small>
                                        {a.part_name || "Назву не надано"}
                                      </small>
                                      {Object.entries(a.characteristics || {})
                                        .slice(0, 8)
                                        .map(([k, v]) => (
                                          <small key={k}>
                                            {k}: {String(v)}
                                          </small>
                                        ))}
                                    </span>
                                    <button
                                      disabled={
                                        busy || (!p && row.parts.length > 0)
                                      }
                                      onClick={() => void assign(row, a)}
                                    >
                                      {p
                                        ? "Призначити та зберегти"
                                        : "Додати 1 шт. та призначити"}
                                    </button>
                                  </div>
                                ))}
                              {offers[row.key].length >
                                (offerLimits[row.key] || 100) && (
                                <button
                                  onClick={() =>
                                    setOfferLimits((old) => ({
                                      ...old,
                                      [row.key]: (old[row.key] || 100) + 100,
                                    }))
                                  }
                                >
                                  Ще 100 варіантів ·{" "}
                                  {offerLimits[row.key] || 100} із{" "}
                                  {offers[row.key].length}
                                </button>
                              )}
                            </div>
                          ) : (
                            <p>Збережених варіантів поки немає.</p>
                          )}
                          {!p && (
                            <p>
                              Спочатку додайте деталь на склад. Попередній вибір
                              не видається за призначений номер.
                            </p>
                          )}
                          {row.pt_id ? (
                            <button
                              disabled={busy || who?.role !== "DIRECTOR"}
                              onClick={() => void prepareQuote(row)}
                            >
                              Отримати нові артикули
                            </button>
                          ) : (
                            <p>
                              Для підбору артикулів потрібний точний тип
                              Plan.Parts. Схожі назви автоматично не
                              зіставляються.
                            </p>
                          )}
                        </>
                      )}
                      {quote && quote.key === row.key && (
                        <div
                          className="wd-confirm"
                          role="alertdialog"
                          aria-label="Підтвердження отримання артикулів"
                        >
                          <p>
                            Максимальна вартість:{" "}
                            {Number.isInteger(quote.cost)
                              ? quote.cost + " токенів"
                              : "не підтверджена"}
                            . Збережені відповіді повторно не оплачуються.
                          </p>
                          <button
                            disabled={
                              busy ||
                              !quote.allowed ||
                              !Number.isInteger(quote.cost)
                            }
                            onClick={() => void requestArticles(row)}
                          >
                            Підтвердити вартість і отримати
                          </button>
                          <button onClick={() => setQuote(null)}>
                            Скасувати
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
          {filtered.length > 10 && (
            <div className="wd-pagination">
              <button
                disabled={page === 0}
                onClick={() => setPage((n) => n - 1)}
              >
                Попередня
              </button>
              <span>
                {page * 10 + 1}–{Math.min(page * 10 + 10, filtered.length)} із{" "}
                {filtered.length}
              </span>
              <button
                disabled={(page + 1) * 10 >= filtered.length}
                onClick={() => setPage((n) => n + 1)}
              >
                Наступна
              </button>
            </div>
          )}
          {!filtered.length && <p>За цими фільтрами позицій немає.</p>}
        </section>
        <aside className="wd-aside">
          <section>
            <h3>Дії з вибраними</h3>
            <p>Обрано: {selected.length} позицій</p>
            <button
              className="wd-primary"
              disabled={
                !selected.length ||
                busy ||
                !rows.filter((r) => selected.includes(r.key)).every(canAdd)
              }
              onClick={() => setConfirmStock(actionKeys)}
            >
              <Plus size={17} />
              Додати на склад
            </button>
            <button
              disabled={!selected.length || busy || !canManage}
              onClick={() => void annotate(actionKeys, "dismantled")}
            >
              Позначити як демонтовано
            </button>
            <button
              disabled={!selected.length || busy || !canManage}
              onClick={() => void annotate(actionKeys, "hide")}
            >
              <EyeOff size={15} />
              Приховати з плану
            </button>
            <button
              disabled={!selected.length || busy || !canManage}
              onClick={() => void annotate(actionKeys, "restore")}
            >
              <RotateCcw size={15} />
              Повернути у план
            </button>
            <button className="wd-link" onClick={() => setSelected([])}>
              Зняти вибір
            </button>
          </section>
          <section>
            <h3>Статуси запчастин</h3>
            {Object.entries(status).map(([k, v]) => (
              <div className="wd-status-count" key={k}>
                <span className={"wd-dot wd-dot-" + k} />
                <span>{v}</span>
                <b>{rows.filter((r) => r.state === k).length}</b>
              </div>
            ))}
          </section>
        </aside>
      </div>
      {confirmStock && (
        <div
          className="wd-confirm"
          role="alertdialog"
          aria-label="Підтвердження складу"
        >
          <strong>Додати на склад: {confirmStock.length} шт.</strong>
          <p>
            Для кожної нової деталі буде створено одну складську позицію з
            кількістю 1. Наявні позиції не дублюються, їхні ціни та кількість не
            змінюються.
          </p>
          <label>
            Місце на складі (необов’язково)
            <input
              maxLength={120}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </label>
          <button disabled={busy} onClick={() => void addToStock()}>
            Додати на склад
          </button>
          <button onClick={() => setConfirmStock(null)}>Скасувати</button>
        </div>
      )}
      {progress && (
        <p role="status">
          Оброблено {progress.done} із {progress.total}
          <button
            onClick={() => {
              stop.current = true;
            }}
          >
            Зупинити після поточної позиції
          </button>
        </p>
      )}
      <section className="wd-translations" aria-label="Керування назвами">
        <Languages size={30} />
        <div>
          <h3>Керування назвами</h3>
          <small>Українські назви запчастин та оригінали для пошуку.</small>
        </div>
        <span className="wd-chip received">
          Перекладено: {names.translated}
        </span>
        <span className="wd-chip planned">
          Потребують уточнення: {names.pending}
        </span>
        <button
          disabled={!!translation || who?.role !== "DIRECTOR"}
          onClick={() => void translate()}
        >
          Оновити переклад
        </button>
        <button
          disabled={selected.length !== 1 || !canManage}
          onClick={() => {
            const r = rows.find((r) => r.key === selected[0])!;
            setExpanded(r.key);
            setEditing(r.key);
            setName(r.name);
          }}
        >
          Змінити назву
        </button>
        <button
          disabled={!!translation || who?.role !== "DIRECTOR"}
          onClick={() => void translate()}
        >
          Перекласти автоматично
        </button>
        {translation && (
          <span role="status">
            Переклад: {translation.done} із {translation.total}
            <button
              onClick={() => {
                stop.current = true;
              }}
            >
              Зупинити
            </button>
          </span>
        )}
      </section>
    </section>
  );
}
