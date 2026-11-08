import SearchPartPreview from "./SearchPartPreview";
import {NotesDialog,InspectionDialog} from "./WorkshopDialogs";
import InventoryQuantity from "./InventoryQuantity";
import PlanPartActions from "./PlanPartActions";
import {partRowInteraction} from "./partRowInteraction";
import { workspaceSections } from "./vehiclePartsWorkspace";
import { corporateCategoryGroups } from "./catalogueLabels";
import { sections as categoryIcons } from "./PartsQuickCategories";
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
  view = "operations",
}: {
  vehicle: Row;
  view?: "operations" | "settings";
  source: "base" | "professional" | "catalogue";
  controls: ReactNode;
  onUpdate?: () => Promise<void>;
  onModify?: () => void;
  onOpenPart: (id: string) => void;
  translationKick?: number;
  revision?: string;
  onTranslationConsumed?: () => void;
}) {
  const settings = view === "settings";
  const [previewKey,setPreviewKey]=useState(''),[previewNotes,setPreviewNotes]=useState<Row|null>(null),[previewInspection,setPreviewInspection]=useState<Row|null>(null),[photoRevision,setPhotoRevision]=useState(0);
  useEffect(()=>setPreviewKey(''),[view]);
  const [oemFilter, setOemFilter] = useState(""),
    [articleFilter, setArticleFilter] = useState("");
  const [savedSearch, setSavedSearch] = useState<Row | null>(null);
  const [savedIndex, setSavedIndex] = useState<Record<string, string[]>>({});
  const savedSearchGuard = useRef(false);
  const displayCategory = (r: Row) =>
    corporateCategoryGroups([
      { id: "display", name: r.category, kind: "category" },
    ])[0]?.label || "Потребує уточнення";
  const [page, setPage] = useState(0);
  const [goodsKind, setGoodsKind] = useState("part");
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
        (!goodsKind || (r.kind || "review") === goodsKind) &&
        (!category || displayCategory(r) === category) &&
        (!settings ||
          !oemFilter ||
          r.parts.some((p: Row) => !!p.oem_number) === (oemFilter === "yes")) &&
        (!settings ||
          !articleFilter ||
          r.parts.some((p: Row) => !!p.article_number) ===
            (articleFilter === "yes")) &&
        (!q ||
          [
            r.name,
            r.original,
            ...(settings ? savedIndex[r.key] || [] : []),
            ...(settings
              ? (offers[r.key] || []).flatMap((a: Row) => [
                  a.article_nr,
                  a.brand,
                  a.part_name,
                ])
              : []),
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
        (settings || (state ? r.state === state : r.state !== "sold")) &&
        (settings ||
          !stock ||
          (stock === "yes" && r.received) ||
          (stock === "no" && !r.received)),
    );
  const categoryRows = rows.filter(
    (r) => !goodsKind || (r.kind || "review") === goodsKind,
  );
  const categories = [
      ...workspaceSections.slice(0, 12),
      ...(categoryRows.some((r) => displayCategory(r) === "Потребує уточнення")
        ? ["Потребує уточнення"]
        : []),
    ],
    metrics = data?.progress || {},
    names = data?.translation || {};
  useEffect(() => {
    setExpanded(null);
    setQuote(null);
    setEditing("");
    setPage(0);
  }, [view]);
  async function searchSaved() {
    if (savedSearchGuard.current) return;
    savedSearchGuard.current = true;
    setError("");
    const g = epoch.current,
      targets = rows.filter(
        (r) =>
          r.pt_id &&
          r.receipt?.stored &&
          r.receipt.saved_count > 0 &&
          offers[r.key] === undefined &&
          savedIndex[r.key] === undefined,
      );
    let cursor = 0,
      done = 0;
    const failures: string[] = [];
    setSavedSearch({ done: 0, total: targets.length });
    try {
      await Promise.all(
        Array.from({ length: Math.min(3, targets.length) }, async () => {
          while (cursor < targets.length && g === epoch.current) {
            const row = targets[cursor++];
            try {
              const result = await api(
                "/plan-parts/articles/recover?vehicle_id=" +
                  vehicle.id +
                  "&ktype=" +
                  vehicle.ktype +
                  "&pt_id=" +
                  row.pt_id,
                "POST",
              );
              if (g !== epoch.current) return;
              setSavedIndex((old) => ({
                ...old,
                [row.key]: result.articles.flatMap((a: Row) =>
                  [a.article_nr, a.brand, a.part_name].filter(Boolean),
                ),
              }));
            } catch (e) {
              failures.push((e as Error).message);
            }
            if (g === epoch.current)
              setSavedSearch({ done: ++done, total: targets.length });
          }
        }),
      );
      if (g === epoch.current) {
        if (failures.length)
          setError(
            "Не вдалося відкрити частину збережених варіантів: " + failures[0],
          );
        else setNotice("Збережені варіанти доступні для пошуку.");
      }
    } catch (e) {
      if (g === epoch.current) setError((e as Error).message);
    } finally {
      savedSearchGuard.current = false;
      if (g === epoch.current) setSavedSearch(null);
    }
  }
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
    setSavedIndex({});
    setArticleChoice({});
    setQuote(null);
    setCategory("");
    setQ("");
    setState("");
    setStock("");
    setTranslation(null);
    setEditing("");
    setName("");
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
    setNotice("");
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
    if (source === "catalogue") {
      try {
        const result = await api("/vehicles/" + vehicle.id + "/unified-catalogue/articles?key=" + encodeURIComponent(row.key));
        setOffers((old) => ({...old, [row.key]: result.articles}));
      } catch (e) { setError((e as Error).message); }
      return;
    }
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
      try {
        let p = partFor(row);
        if (row.context_matches === false)
          throw Error(
            "Відкрийте попередній список для цієї складської картки. Модифікація потребує звірки.",
          );
        if (!p && row.parts.length)
          throw Error("Виберіть конкретну складську картку");
        if (!p)
          throw Error(
            "Спочатку додайте деталь на склад у вкладці «Розбір і запчастини».",
          );
        await api(
          source === "catalogue" ? "/vehicles/" + vehicle.id + "/unified-catalogue/article" : "/plan-parts/donor-parts/article/select?vehicle_id=" + vehicle.id,
          "POST",
          {
            ...(source === "catalogue" ? {key: row.key} : {ktype: vehicle.ktype, pt_id: row.pt_id}),
            part_id: p.id,
            art_id: offer.art_id,
            expected_article_number: p.article_number || "",
            expected_article_brand: p.article_brand || "",
          },
        );
        if (g === epoch.current) {
          setExpanded(null);
          setNotice("Артикул і виробника збережено в складській картці.");
        }
      } finally {
        await load(g);
        window.dispatchEvent(new Event("warehouse:inventory-changed"));
      }
    });
  }
  async function assignCatalogueOem(row: Row, offer: Row, number: string) {
    const p = partFor(row);
    if (!p || !window.confirm(`Призначити OEM-крос ${number}? Відповідність VIN не перевірена.`)) return;
    await run(async g => {
      await api("/vehicles/"+vehicle.id+"/unified-catalogue/oem","POST",{key:row.key,part_id:p.id,art_id:offer.art_id,oem_number:number,confirm_cross_reference:true});
      await load(g);
      window.dispatchEvent(new Event("warehouse:inventory-changed"));
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
  async function addToStock(keys: string[]) {
    await run(async (g) => {
      const picked = rows.filter(
        (r) =>
          keys.includes(r.key) &&
          (r.pt_id || source !== "professional") &&
          !["sold", "hidden"].includes(r.state),
      );
      if (picked.length > 1000)
        throw Error(
          "Один пакет — до 1000 позицій. Звузьте вибір за категорією.",
        );
      if (!picked.length)
        throw Error("Немає нових доступних позицій у виборі.");
      try {
        setProgress({ done: 0, total: picked.length });
        if (source !== "professional" && !window.confirm(`Додати на склад по 1 фізичній деталі: ${picked.length} позицій?`)) return;
        const result = await api(
          source !== "professional" ? "/vehicles/" + vehicle.id + "/unified-catalogue/stock" : "/plan-parts/donor-parts/add-batch?vehicle_id=" + vehicle.id,
          "POST",
          {
            ...(source !== "professional" ? {keys: picked.map(r=>r.key), confirm_physical_receipt: true} : {items: picked.map((r) => ({
              ktype: vehicle.ktype,
              pt_id: r.pt_id,
              ukrainian_name: r.name,
            }))}),
          },
        );
        if (g === epoch.current) {
          setProgress({ done: picked.length, total: picked.length });
          setSelected([]);
          setNotice(
            `Додано: ${result.added}. Уже існують: ${result.skipped}. Помилок: 0.${result.review_required ? " Потребують звірки: " + result.review_required + "." : ""}`,
          );
        }
      } finally {
        await load(g);
        window.dispatchEvent(new Event("warehouse:inventory-changed"));
      }
    });
  }
  const canAdd = (_row: Row) => can("inventory.create") && (source === "professional" || can("inventory.adjust_quantity"));
  const actionKeys = selected.length ? selected : [],
    canManage = can("dismantling.manage") && !vehicle.archived;
  if (!data)
    return <p role="status">{error || "Відкриваємо збережений список…"}</p>;
  const previewRow=rows.find(r=>r.key===previewKey),previewStock=previewRow&&(partFor(previewRow)||previewRow.parts[0]);
  const previewPart=previewRow?{...previewStock,name:previewRow.name,original:previewRow.original,...(!previewStock?{catalogue_only:true,plan_status:status[previewRow.state]}:{})}:null;
  const previewSaved=()=>{void load(epoch.current);window.dispatchEvent(new Event('warehouse:inventory-changed'));};
  return (
    <section
      className="wd-board"
      data-view={view}
      aria-label={
        settings ? "Налаштування деталей автомобіля" : "Єдиний план розбору"
      }
    >
      {error && (
        <p className="wd-error" role="alert">
          {error.replace(/plan\.parts/gi, "каталог")}
        </p>
      )}
      {notice && (
        <p className="wd-notice" role="status">
          {notice}
        </p>
      )}
      {!settings && (
        <nav className="wd-categories" aria-label="Категорії CarPot">
          {["", ...categories].map((c) => {
            const Icon =
              categoryIcons.find((s) => s.name === c)?.icon || Package;
            return (
              <button
                key={c || "all"}
                aria-pressed={category === c}
                onClick={() => {
                  setCategory(c);
                  setPage(0);
                }}
              >
                <Icon size={18} />
                <span>{c || "Усі категорії"}</span>
                <b>
                  {c
                    ? categoryRows.filter((r) => displayCategory(r) === c)
                        .length
                    : categoryRows.length}
                </b>
              </button>
            );
          })}
        </nav>
      )}
      <div
        className="wd-actionbar"
        role="group"
        aria-label={settings ? "Вибір для налаштування" : "Дії з вибраними"}
      >
        <strong>Вибрано: {selected.length}</strong>
        {!settings && (
          <>
            <button
              className="wd-primary"
              disabled={
                busy ||
                !selected.some((k) => {
                  const r = rows.find((r) => r.key === k);
                  return (
                    r &&
                    !r.parts.length &&
                    ["planned", "dismantled"].includes(r.state) &&
                    canAdd(r)
                  );
                })
              }
              onClick={() => void addToStock(actionKeys)}
            >
              Додати на склад
            </button>
            <button
              disabled={
                busy ||
                !canManage ||
                !selected.length ||
                selected.some(
                  (k) =>
                    !["planned", "dismantled"].includes(
                      rows.find((r) => r.key === k)?.state,
                    ),
                )
              }
              onClick={() => void annotate(actionKeys, "dismantled")}
            >
              Позначити як демонтовано
            </button>
            <button
              disabled={
                busy ||
                !canManage ||
                !selected.length ||
                selected.some(
                  (k) => rows.find((r) => r.key === k)?.state === "hidden",
                )
              }
              onClick={() => void annotate(actionKeys, "hide")}
            >
              Приховати з плану
            </button>
            {selected.some(
              (k) => rows.find((r) => r.key === k)?.state === "hidden",
            ) && (
              <button
                disabled={busy || !canManage}
                onClick={() =>
                  void annotate(
                    actionKeys.filter(
                      (k) => rows.find((r) => r.key === k)?.state === "hidden",
                    ),
                    "restore",
                  )
                }
              >
                Повернути в план
              </button>
            )}
          </>
        )}
        <button disabled={!selected.length} onClick={() => setSelected([])}>
          Зняти вибір
        </button>
      </div>
      <div className={"wd-layout part-preview-layout"+(!settings&&previewRow?" has-preview":"")}>
        <section className="wd-list">
          <div className="wd-list-heading">
            <h3>
              {category ||
                (goodsKind === "part"
                  ? "Фізичні деталі"
                  : "Позиції каталогу")}{" "}
              ({filtered.length})
            </h3>
            {settings && (
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
            )}
          </div>
          <div className="wd-filters">
            {settings && (
              <>
                <select
                  aria-label="Категорія налаштувань"
                  value={category}
                  onChange={(e) => {
                    setCategory(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="">Усі категорії</option>
                  {categories.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
                <select
                  aria-label="Наявність OEM"
                  value={oemFilter}
                  onChange={(e) => {
                    setOemFilter(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="">OEM: усі</option>
                  <option value="yes">Є OEM</option>
                  <option value="no">Немає OEM</option>
                </select>
                <select
                  aria-label="Наявність артикула"
                  value={articleFilter}
                  onChange={(e) => {
                    setArticleFilter(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="">Артикули: усі</option>
                  <option value="yes">Є артикул</option>
                  <option value="no">Немає артикула</option>
                </select>
                <button
                  disabled={!!savedSearch}
                  onClick={() => void searchSaved()}
                >
                  Пошук у збережених варіантах
                </button>
                {savedSearch && (
                  <small role="status">
                    Завантажено: {savedSearch.done} із {savedSearch.total}
                  </small>
                )}
              </>
            )}
            <select
              aria-label="Тип позицій"
              value={goodsKind}
              onChange={(e) => {
                setGoodsKind(e.target.value);
                setCategory("");
                setPage(0);
              }}
            >
              {[
                ["part", "Фізичні деталі"],
                ["kit", "Ремонтні комплекти"],
                ["consumable", "Витратні матеріали"],
                ["tool", "Інструменти"],
                ["review", "Потребує уточнення"],
                ["", "Усі типи"],
              ].map(([key, label]) => (
                <option key={key} value={key}>
                  {label} (
                  {
                    rows.filter((r) => !key || (r.kind || "review") === key)
                      .length
                  }
                  )
                </option>
              ))}
            </select>
            <label>
              <Search size={17} />
              <input
                aria-label="Пошук деталей плану"
                placeholder={
                  settings ? "Назва, OEM або артикул…" : "Пошук запчастин…"
                }
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </label>
            {!settings && (
              <>
                {" "}
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
              </>
            )}{" "}
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
              <span>{settings ? "Категорія" : "Статус"}</span>
              {settings ? (
                <>
                  <span>OEM номер</span>
                  <span>Артикул / виробник</span>
                </>
              ) : (
                <span>Кількість</span>
              )}
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
                    {...(!settings ? partRowInteraction(()=>setPreviewKey(row.key)) : {})}
                    className={
                      "wd-row" + (chosen.has(row.key) ? " selected" : "") + (previewKey===row.key ? " part-row-active" : "")
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
                      {settings && (
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
                      )}
                    </div>
                    <div>
                      {settings ? (
                        <span>{displayCategory(row)}</span>
                      ) : (
                        <>
                          {" "}
                          <span className={"wd-chip " + row.state}>
                            {status[row.state]}
                          </span>
                          {row.decision_review && (
                            <small>
                              Різні попередні рішення — перевірте назву та стан.
                            </small>
                          )}
                          {row.context_matches === false && (
                            <small>
                              Є у попередньому списку. Відповідність модифікації
                              потребує звірки.
                            </small>
                          )}
                          {row.state === "planned" && (
                            <small>Наявність перевірити</small>
                          )}
                        </>
                      )}
                    </div>
                    {settings ? (
                      <>
                        <div className="wd-oem" data-number-present={!!p?.oem_number}>
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
                            disabled={!p || !can("inventory.edit")}
                            onClick={() => {
                              if (!p) return;
                              setExpanded(row.key);
                              setEditing("oem:" + row.key);
                            }}
                          >
                            Ввести OEM
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
                                      <small>
                                        Попередній вибір — не збережено
                                      </small>
                                    </>
                                  );
                                })()
                              ) : (
                                "Відкрити артикули"
                              )}
                              <small>
                                {count > 0
                                  ? (p?.article_number && !offers[row.key]
                                      ? "Збережені варіанти ("
                                      : "Інші артикули (") +
                                    (offers[row.key]
                                      ? offers[row.key].filter(
                                          (a: Row) =>
                                            a.article_nr !==
                                              p?.article_number ||
                                            a.brand !== p?.article_brand,
                                        ).length
                                      : count) +
                                    ")"
                                  : "Переглянути артикули"}
                              </small>
                            </span>
                            <ChevronDown size={15} />
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="wd-quantity">
                        {row.parts.length ? row.parts.map((stockPart: Row)=><InventoryQuantity key={stockPart.id} part={stockPart} onSaved={()=>void load(epoch.current)} />) : "Не на складі"}
                        {row.parts.length > 1 && (
                          <small>{row.parts.length} картки складу</small>
                        )}
                      </div>
                    )}
                    <div className="wd-row-actions">
                      {!settings && !row.parts.length && (
                        <button
                          disabled={
                            !canAdd(row) ||
                            busy ||
                            ["received", "sold", "hidden", "empty"].includes(
                              row.state,
                            )
                          }
                          onClick={() => void addToStock([row.key])}
                        >
                          <Plus size={14} />
                          Додати 1 шт.
                        </button>
                      )}
                      <PlanPartActions name={row.name} actions={[
                        ...(p ? [{label:"Відкрити картку",run:()=>onOpenPart(p.id)}] : []),
                        ...(!settings && !row.parts.length && canAdd(row) && !busy && !["received","sold","hidden","empty"].includes(row.state) ? [{label:"Додати на склад",run:()=>void addToStock([row.key])}] : []),
                        ...(!settings && p && !p.archived && can("inventory.adjust_quantity") ? [{label:"Змінити кількість",run:()=>window.dispatchEvent(new CustomEvent("warehouse:quantity-edit",{detail:p.id}))}] : []),
                        ...(canManage && !busy && !["sold","hidden","received"].includes(row.state) ? [{label:"Позначити як демонтовано",run:()=>void annotate([row.key],"dismantled")}] : []),
                        ...(p && can("inventory.edit") ? [{label:"Редагувати запчастину",run:()=>onOpenPart(p.id)}] : []),
                        ...(canManage && !busy ? [{label:row.state==="hidden"?"Повернути в план":"Приховати з плану",run:()=>void annotate([row.key],row.state==="hidden"?"restore":"hide")}] : []),
                      ]} />
                    </div>
                  </article>
                  {settings && expanded === row.key && (
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
                      {editing !== row.key && (
                        <>
                          <p className="wd-hint">
                            {source === "catalogue" ? "OEM-кроси показані окремо. Вони не підтверджують відповідність VIN; призначайте перевірений номер у картці." : "Автоматичне отримання OEM недоступне. Введіть номер вручну та перевірте його відповідність автомобілю."}
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
                                          {a.oem_numbers?.length > 0 && <small>OEM-кроси: {a.oem_numbers.join(", ")}</small>}
                                          {source === "catalogue" && p && !p.oem_number && can("inventory.edit") && a.oem_numbers?.map((number:string)=><button key={number} disabled={busy} onClick={()=>void assignCatalogueOem(row,a,number)}>Призначити OEM {number}</button>)}
                                          {Object.entries(
                                            a.characteristics || {},
                                          )
                                            .slice(0, 8)
                                            .map(([k, v]) => (
                                              <small key={k}>
                                                {k}: {String(v)}
                                              </small>
                                            ))}
                                        </span>
                                        <button
                                          disabled={
                                            busy ||
                                            !p ||
                                            row.context_matches === false
                                          }
                                          onClick={() => void assign(row, a)}
                                        >
                                          {p
                                            ? "Призначити та зберегти"
                                            : "Спочатку додайте на склад"}
                                        </button>
                                      </div>
                                    ))}
                                  {offers[row.key].length >
                                    (offerLimits[row.key] || 100) && (
                                    <button
                                      onClick={() =>
                                        setOfferLimits((old) => ({
                                          ...old,
                                          [row.key]:
                                            (old[row.key] || 100) + 100,
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
                                  Щоб призначити номер, спочатку додайте деталь
                                  у вкладці «Розбір і запчастини».
                                </p>
                              )}
                              {row.pt_id ? (
                                <button
                                  disabled={
                                    busy ||
                                    row.context_matches === false ||
                                    who?.role !== "DIRECTOR"
                                  }
                                  onClick={() => void prepareQuote(row)}
                                >
                                  Отримати нові артикули
                                </button>
                              ) : (
                                <p>
                                  {source === "catalogue" ? "Збережені дані власного каталогу — без повторного платного запиту." : "Для підбору артикулів потрібний точний тип каталогу. Схожі назви автоматично не зіставляються."}
                                </p>
                              )}
                            </>
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
        {!settings&&previewRow&&<SearchPartPreview part={previewPart} vehicle={vehicle} category={{name:displayCategory(previewRow)}} canSell={false} onOpen={()=>previewStock&&onOpenPart(previewStock.id)} onSell={()=>{}} onEdit={()=>previewStock&&onOpenPart(previewStock.id)} onSaved={previewSaved} open onClose={()=>setPreviewKey('')} position={Math.max(1,filtered.findIndex(r=>r.key===previewKey)+1)} total={filtered.length} onPrevious={()=>{const i=filtered.findIndex(r=>r.key===previewKey);if(i>0)setPreviewKey(filtered[i-1].key);}} onNext={()=>{const i=filtered.findIndex(r=>r.key===previewKey);if(i>=0&&i+1<filtered.length)setPreviewKey(filtered[i+1].key);}} photoRevision={photoRevision} onPhotoSaved={()=>setPhotoRevision(n=>n+1)} onNotes={previewStock?()=>setPreviewNotes(previewStock):undefined} onInspection={previewStock?()=>setPreviewInspection(previewStock):undefined} contextActions={<>
          {previewRow.parts.length>1&&<label>Складська картка<select aria-label="Картка для швидкого перегляду" value={previewStock?.id||''} onChange={e=>setTarget(old=>({...old,[previewRow.key]:e.target.value}))}>{previewRow.parts.map((card:Row,i:number)=><option key={card.id} value={card.id}>{card.article_number||card.name} · {i+1} · {card.quantity} шт.</option>)}</select></label>}
          {!previewRow.parts.length&&canAdd(previewRow)&&!["sold","hidden","received","empty"].includes(previewRow.state)&&<button disabled={busy} onClick={()=>void addToStock([previewRow.key])}>Додати 1 шт. на склад</button>}
          {canManage&&!["sold","hidden","received"].includes(previewRow.state)&&<button disabled={busy} onClick={()=>void annotate([previewRow.key],"dismantled")}>Позначити як демонтовано</button>}
          {canManage&&<button disabled={busy} onClick={()=>void annotate([previewRow.key],previewRow.state==="hidden"?"restore":"hide")}>{previewRow.state==="hidden"?"Повернути в план":"Приховати з плану"}</button>}
        </>}/>}
      </div>
      {previewNotes&&<NotesDialog part={previewNotes} onClose={()=>setPreviewNotes(null)} onSaved={()=>{setPreviewNotes(null);previewSaved();}}/>}
      {previewInspection&&<InspectionDialog part={previewInspection} onClose={()=>setPreviewInspection(null)} onSaved={()=>{setPreviewInspection(null);previewSaved();}}/>}
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
      {settings && (
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
            Перекласти відсутні назви
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
      )}
    </section>
  );
}
