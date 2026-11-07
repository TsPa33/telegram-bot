import DismantlingBoard from "./DismantlingBoard";
import { Modal } from "./components";
import { PartDetail } from "./pages/Inventory";
import type { ReactNode } from "react";
import { useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Row } from "./api";
import { TeamIdentity } from "./permissions";
import PartCharacteristicsEditor from "./PartCharacteristicsEditor";
import {
  Boxes,
  Cog,
  ArrowLeftRight,
  Car,
  Shield,
  Lightbulb,
  Snowflake,
  Zap,
  Wrench,
  Check,
  Database,
  Search,
  Package,
  Tag,
  CheckCircle2,
  Info,
  Layers,
  Armchair,
  Disc,
  CircleDot,
  RotateCcw,
} from "lucide-react";
import {
  workspacePartName,
  workspaceSections,
  sectionOf,
  filterWorkspace,
  changeWorkspaceSelection,
  priceQuote,
} from "./vehiclePartsWorkspace";
import "./vehicle-parts-workspace.css";
const icons = [
  Cog,
  ArrowLeftRight,
  Car,
  CircleDot,
  Disc,
  Car,
  Armchair,
  Zap,
  Lightbulb,
  Snowflake,
  Shield,
  Wrench,
  Info,
];
const root = "/plan-parts",
  query = (v: unknown) => encodeURIComponent(String(v));
export default function PlanPartsDonorAnalysis({
  vehicle,
  onSaved,
  onLoaded,
  onCatalogueReady,
  setupOnly = false,
}: {
  vehicle: Row;
  onSaved: (row: Row) => void;
  sourceSelector?: ReactNode;
  onLoaded?: (row: Row) => void;
  onCatalogueReady?: () => void;
  setupOnly?: boolean;
}) {
  const [translationKick, setTranslationKick] = useState(0);
  const [detail, setDetail] = useState<Row | null>(null);
  const [boardRevision, setBoardRevision] = useState(0);
  const legacyLayout = false;
  const who = useContext(TeamIdentity),
    scope = JSON.stringify([who?.id, vehicle.id, vehicle.ktype]),
    epoch = useRef(0),
    lock = useRef(false),
    stop = useRef(false);
  const [workspace, setWorkspace] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [section, setSection] = useState("all"),
    [q, setQ] = useState(""),
    [stockFilter, setStockFilter] = useState("all"),
    [dataFilter, setDataFilter] = useState("all"),
    [oemFilter, setOemFilter] = useState("all"),
    [selected, setSelected] = useState<number[]>([]),
    [limit, setLimit] = useState(60);
  const [active, setActive] = useState<number | null>(null),
    [offers, setOffers] = useState<Record<number, Row[]>>({}),
    [offerSelection, setOfferSelection] = useState<number | null>(null),
    [confirmAssign, setConfirmAssign] = useState(false),
    [manualOem, setManualOem] = useState(false);
  const [quote, setQuote] = useState<Row | null>(null),
    [confirmStock, setConfirmStock] = useState(false),
    [progress, setProgress] = useState<Row | null>(null),
    [tech, setTech] = useState(false),
    [matches, setMatches] = useState<Row[]>([]),
    [picked, setPicked] = useState(Number(vehicle.ktype) || 0),
    [nameDraft, setNameDraft] = useState<Record<number, string>>({});
  const path = root + "/workspace?vehicle_id=" + query(vehicle.id);
  const [targetPartId, setTargetPartId] = useState("");
  const [loading, setLoading] = useState(true),
    [offerLimit, setOfferLimit] = useState(100);
  const [offerLoading, setOfferLoading] = useState<number | null>(null);
  const offerTicket = useRef(0);
  const managerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    setOfferLimit(100);
    if (active !== null)
      managerRef.current?.scrollIntoView({
        block: "nearest",
        behavior: "instant",
      });
  }, [active]);
  async function load(generation = epoch.current, receivedCatalogue = false) {
    const r = await api(path);
    if (generation === epoch.current) {
      setWorkspace(r);
      setBoardRevision((n) => n + 1);
      if (receivedCatalogue) {
        setTranslationKick((n) => n + 1);
        onCatalogueReady?.();
      }
      onLoaded?.(r);
      if (r.saved_modifications?.length) setMatches(r.saved_modifications);
    }
    return r;
  }
  useEffect(() => {
    const g = ++epoch.current;
    setWorkspace(null);
    setTranslationKick(0);
    setDetail(null);
    setOffers({});
    offerTicket.current++;
    setOfferLoading(null);
    setNameDraft({});
    setTargetPartId("");
    setManualOem(false);
    setSelected([]);
    setActive(null);
    setQuote(null);
    setConfirmAssign(false);
    setConfirmStock(false);
    setMatches([]);
    setPicked(Number(vehicle.ktype) || 0);
    setSection("all");
    setQ("");
    setNotice("");
    setError("");
    setLoading(true);
    setTech(!vehicle.ktype);
    load(g)
      .catch((e) => {
        if (g === epoch.current) setError(e.message);
      })
      .finally(() => {
        if (g === epoch.current) setLoading(false);
      });
    return () => {
      epoch.current++;
      stop.current = true;
    };
  }, [scope]);
  useEffect(() => {
    setLimit(60);
  }, [section, q, stockFilter, dataFilter, oemFilter]);
  const categories: Row[] = workspace?.categories || [],
    parts = useMemo(
      () =>
        new Map<number, Row>(
          (workspace?.parts || []).map((p: Row) => [p.pt_id, p]),
        ),
      [workspace],
    ),
    receipts = useMemo(
      () =>
        new Map<number, Row>(
          (workspace?.receipts || []).map((r: Row) => [r.pt_id, r]),
        ),
      [workspace],
    );
  const localized = (r: Row) => workspacePartName(r, nameDraft[r.pt_id]);
  const filtered = filterWorkspace(
      categories,
      { section, q, stock: stockFilter, data: dataFilter, oem: oemFilter },
      parts,
      receipts,
      offers,
    ),
    selectedSet = new Set(selected),
    newSelected = categories.filter(
      (r) => selectedSet.has(r.pt_id) && !parts.has(r.pt_id),
    );
  const current = categories.find((r) => r.pt_id === active),
    currentChoices: Row[] = (workspace?.parts || []).filter(
      (p: Row) => p.pt_id === active,
    ),
    currentPart =
      currentChoices.length === 1
        ? currentChoices[0]
        : currentChoices.find((p) => p.id === targetPartId),
    currentOffers = active ? offers[active] || [] : [],
    chosen = currentOffers.find((r) => r.art_id === offerSelection),
    policy = workspace?.policy || {},
    activeLabel = current ? localized(current) : "";
  async function run(fn: (g: number) => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    stop.current = false;
    setBusy(true);
    setError("");
    const g = epoch.current;
    try {
      await fn(g);
    } catch (e) {
      if (g === epoch.current) setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
      if (g === epoch.current) {
        setProgress(null);
      }
    }
  }
  async function refresh(g: number) {
    await load(g);
    if (g !== epoch.current) return;
    window.dispatchEvent(new Event("warehouse:inventory-changed"));
    const donor = await api("/vehicles/" + query(vehicle.id));
    if (g === epoch.current) onSaved(donor);
  }
  async function recover(pt: number, g: number) {
    const r = await api(
      root +
        "/articles/recover?vehicle_id=" +
        query(vehicle.id) +
        "&ktype=" +
        vehicle.ktype +
        "&pt_id=" +
        pt,
      "POST",
    );
    if (g === epoch.current) {
      setOffers((old) => ({ ...old, [pt]: r.articles }));
      await load(g);
    }
    return r;
  }
  function open(r: Row) {
    setQuote(null);
    setActive(r.pt_id);
    setTargetPartId("");
    setOfferSelection(null);
    setConfirmAssign(false);
    setManualOem(false);
    setNotice("");
    setError("");
    const ticket = ++offerTicket.current,
      g = epoch.current;
    if (Object.prototype.hasOwnProperty.call(offers, r.pt_id)) {
      setOfferLoading(null);
      return;
    }
    setOfferLoading(r.pt_id);
    void recover(r.pt_id, g)
      .catch((e) => {
        if (g !== epoch.current || ticket !== offerTicket.current) return;
        if (receipts.has(r.pt_id) || (e as { status?: number }).status !== 409)
          setError((e as Error).message);
        if (receipts.has(r.pt_id))
          setNotice(
            "Попередні дані потребують перевірки. Нової оплати не було.",
          );
      })
      .finally(() => {
        if (g === epoch.current && ticket === offerTicket.current)
          setOfferLoading(null);
      });
  }
  function prepareArticles() {
    if (!current) return;
    setConfirmAssign(false);
    setQuote({
      resource: "articles",
      ids: [current.pt_id],
      cost: policy.max_tokens?.articles,
      force: Boolean(
        receipts.has(current.pt_id) ||
          Object.prototype.hasOwnProperty.call(offers, current.pt_id),
      ),
    });
  }
  async function startCatalogue() {
    if (!vehicle.ktype) {
      setTech(true);
      return;
    }
    await run(async (g) => {
      try {
        await api(
          root +
            "/categories/recover?vehicle_id=" +
            query(vehicle.id) +
            "&ktype=" +
            vehicle.ktype,
          "POST",
        );
        await load(g, true);
        if (g === epoch.current)
          setNotice("Дані отримані раніше. Список збережено.");
      } catch (e) {
        if (g !== epoch.current) return;
        if ((e as { status?: number }).status === 409) prepare("categories");
        else throw e;
      }
    });
  }
  async function saveName() {
    if (!current) return;
    const row = { ...current },
      name = localized(row).trim();
    if (
      !/[А-Яа-яІіЇїЄєҐґ]/.test(name) ||
      name === "Потрібно уточнити українську назву"
    ) {
      setError("Вкажіть українську назву деталі");
      return;
    }
    await run(async (g) => {
      await api(
        "/vehicles/" +
          query(vehicle.id) +
          "/plan-parts-checklist/" +
          row.checklist_id,
        "PATCH",
        { name_uk: name },
      );
      await load(g);
      if (g === epoch.current)
        setNotice(
          "Українську назву збережено. Оригінал залишається доступним для пошуку.",
        );
    });
  }
  function prepare(resource: string) {
    setQuote({ resource, ids: [], cost: policy.max_tokens?.[resource] });
  }
  async function pay() {
    const intent = quote;
    if (!intent) return;
    await run(async (g) => {
      const ids = intent.resource === "articles" ? intent.ids : [0],
        unit = intent.cost;
      if (!priceQuote(unit, ids.length).known || !policy.terms_confirmed)
        throw Error("Тариф або умови збереження API не підтверджені");
      setQuote(null);
      for (let i = 0; i < ids.length; i++) {
        if (g !== epoch.current || stop.current) break;
        setProgress({
          done: i,
          total: ids.length,
          label: "Отримання даних API",
        });
        const pt = ids[i];
        const key =
          "carpot-provider-intent:" + scope + ":" + intent.resource + ":" + pt;
        let requestKey = sessionStorage.getItem(key);
        if (!requestKey) {
          requestKey = crypto.randomUUID();
          sessionStorage.setItem(key, requestKey);
        }
        const suffix =
          intent.resource === "articles"
            ? "/articles/lookup?ktype=" + vehicle.ktype + "&pt_id=" + pt
            : intent.resource === "categories"
              ? "/categories/lookup?ktype=" + vehicle.ktype
              : "/vehicle-matches/lookup?unused=0";
        const r = await api(
          root +
            suffix +
            "&vehicle_id=" +
            query(vehicle.id) +
            "&request_key=" +
            requestKey +
            "&confirm_paid=true&max_tokens=" +
            unit +
            (intent.force ? "&force_paid=true" : ""),
          "POST",
        );
        sessionStorage.removeItem(key);
        if (g !== epoch.current) return;
        if (intent.resource === "articles")
          setOffers((old) => ({ ...old, [pt]: r.articles }));
        else if (intent.resource === "ktype") setMatches(r.matches);
        await load(g, intent.resource === "categories");
        setProgress({
          done: i + 1,
          total: ids.length,
          label: "Дані API збережено",
        });
      }
      if (g === epoch.current)
        setNotice(
          "Отримані дані збережено. Повторний перегляд не викликає провайдера.",
        );
    });
  }
  async function add() {
    const pending = newSelected.filter(
      (r) =>
        /[А-Яа-яІіЇїЄєҐґ]/.test(localized(r)) &&
        localized(r) !== "Потрібно уточнити українську назву",
    );
    if (pending.length !== newSelected.length) {
      setError("Уточніть українські назви перед додаванням");
      return;
    }
    setConfirmStock(false);
    await run(async (g) => {
      let done = 0;
      try {
        for (let i = 0; i < pending.length; i += 20) {
          if (g !== epoch.current || stop.current) break;
          const subset = pending.slice(i, i + 20);
          setProgress({
            done,
            total: pending.length,
            label: "Додавання на склад",
          });
          const r = await api(
            root + "/donor-parts/add-batch?vehicle_id=" + query(vehicle.id),
            "POST",
            {
              items: subset.map((r) => ({
                ktype: vehicle.ktype,
                pt_id: r.pt_id,
                ukrainian_name: localized(r),
              })),
            },
          );
          done += r.results.filter((x: Row) => x.ok).length;
          if (r.results.some((x: Row) => !x.ok))
            throw Error(
              "Частину позицій не додано. Перевірте фактичний склад перед повтором.",
            );
        }
        if (g === epoch.current) {
          setSelected([]);
          setNotice(
            "Оброблено " +
              done +
              " позицій. Повторне додавання не створює надходжень.",
          );
        }
      } finally {
        if (g === epoch.current) await refresh(g);
      }
    });
  }
  async function assign() {
    if (!currentPart || !chosen || !current) return;
    const target = { ...currentPart },
      offer = { ...chosen },
      pt = current.pt_id;
    await run(async (g) => {
      await api(
        root + "/donor-parts/article/select?vehicle_id=" + query(vehicle.id),
        "POST",
        {
          ktype: vehicle.ktype,
          pt_id: pt,
          art_id: offer.art_id,
          part_id: target.id,
          expected_article_number: target.article_number || "",
          expected_article_brand: target.article_brand || "",
        },
      );
      await refresh(g);
      if (g === epoch.current) {
        setConfirmAssign(false);
        setNotice(
          "Артикул і виробника записано до конкретної складської позиції.",
        );
      }
    });
  }
  const counts = workspace?.summary || {},
    sectionCounts = new Map(
      workspaceSections.map((s) => [
        s,
        categories.filter((c) => sectionOf(c) === s).length,
      ]),
    );
  const paidConfirmation = quote && (
    <div
      role="alertdialog"
      aria-label="Підтвердження витрати токенів"
      className="vp-confirm"
    >
      <strong>
        {quote.resource === "ktype"
          ? "Пошук модифікації"
          : quote.resource === "categories"
            ? "Розібрати авто на запчастини"
            : "Отримати артикули"}
      </strong>
      {priceQuote(
        quote.cost,
        quote.resource === "articles" ? quote.ids.length : 1,
      ).known ? (
        <>
          <p>
            {quote.resource === "articles"
              ? `Вибрано типів: ${quote.ids.length}. `
              : ""}
            Максимальна вартість:{" "}
            <b>
              {
                priceQuote(
                  quote.cost,
                  quote.resource === "articles" ? quote.ids.length : 1,
                ).max
              }{" "}
              токенів
            </b>
            .
          </p>
          <p>
            Якщо результат уже збережено, повторна оплата не потрібна. Токени
            витрачаються лише за нову успішну відповідь Plan.Parts.
          </p>
        </>
      ) : (
        <p>
          Вартість запиту тимчасово недоступна. Платний запит не запускається
          без відомого тарифу.
        </p>
      )}
      {!policy.terms_confirmed && (
        <p>
          Отримання нових даних тимчасово недоступне. Збережені дані можна
          переглядати.
        </p>
      )}
      <button
        disabled={
          busy ||
          !policy.terms_confirmed ||
          !priceQuote(
            quote.cost,
            quote.resource === "articles" ? quote.ids.length : 1,
          ).known
        }
        onClick={() => void pay()}
      >
        Підтвердити та отримати
      </button>
      <button className="secondary" onClick={() => setQuote(null)}>
        Скасувати
      </button>
    </div>
  );
  return (
    <section className="vp-workspace" aria-label="Розбір і запчастини">
      <div className="vp-topline">
        <div>
          <h3>Розбір і запчастини</h3>
          <p>
            Plan.Parts · {vehicle.manufacturer} {vehicle.model} · {vehicle.year}{" "}
            · Донор №{vehicle.number || "—"}
          </p>
        </div>
        <button
          type="button"
          className="secondary"
          aria-expanded={tech}
          onClick={() => setTech(!tech)}
        >
          {vehicle.ktype ? "Змінити модифікацію" : "Вибрати модифікацію"}
        </button>
      </div>

      {loading && <p role="status">Відкриваємо список…</p>}
      {error && (
        <p role="alert" className="vp-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="vp-notice">
          {notice}
        </p>
      )}
      {legacyLayout && categories.length > 0 && (
        <>
          <p role="status">Список збережено · {categories.length} деталей</p>
          <div className="vp-kpis" aria-label="Показники збережених даних">
            <span>
              <Boxes size={15} />
              <b>{counts.types ?? "—"}</b> Збережені типи запчастин
            </span>
            <span>
              <Layers size={15} />
              <b>{counts.saved_variants ?? "—"}</b> Збережені варіанти артикулів
            </span>
            <span>
              <Tag size={15} />
              <b>{counts.oem_assigned ?? "—"}</b> Позиції з OEM
            </span>
            <span>
              <Database size={15} />
              <b>{counts.article_assigned ?? "—"}</b> Позиції з призначеними
              артикулами
            </span>
            <span>
              <RotateCcw size={15} />
              <b>{counts.needs_recovery ?? "—"}</b> Типи, які потребують
              відновлення
            </span>
          </div>

          {(workspace?.responses || []).some(
            (r: Row) => r.metadata_json?.completeness === "partial",
          ) && (
            <p role="status" className="vp-notice">
              Отриманий список може бути неповним: збережені записи не
              підтверджують повноту каталогу. Нові сторінки автоматично не
              запитуються.
            </p>
          )}
        </>
      )}

      {!loading && categories.length === 0 && (
        <section className="vp-start" aria-label="Почати розбір автомобіля">
          <h3>Розбір автомобіля на запчастини</h3>
          <p>
            {vehicle.ktype
              ? "Модифікацію вибрано. Створіть перелік запчастин."
              : "Виберіть двигун і модифікацію, після чого сформуйте список запчастин."}
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (vehicle.ktype) void startCatalogue();
              else {
                setTech(true);
                prepare("ktype");
              }
            }}
          >
            {vehicle.ktype
              ? "Розібрати авто на запчастини"
              : "1. Вибрати модифікацію"}
          </button>
        </section>
      )}
      {(workspace?.saved_plan_ktypes || [])
        .filter((k: number) => k !== Number(vehicle.ktype))
        .map((k: number) => (
          <button
            key={k}
            onClick={() =>
              void run(async (g) => {
                if (
                  !window.confirm(
                    "Відкрити раніше збережений список? Поточні дані залишаться збереженими.",
                  )
                )
                  return;
                await api(
                  root +
                    "/vehicle-modification/select?vehicle_id=" +
                    query(vehicle.id),
                  "POST",
                  { ktype: k, confirm_change: true },
                );
                if (g === epoch.current)
                  onSaved(await api("/vehicles/" + query(vehicle.id)));
              })
            }
          >
            Відкрити попередній збережений список
          </button>
        ))}
      {(tech || !vehicle.ktype) && (
        <div className="vp-technical">
          {!vehicle.ktype && <p role="status">Потрібно вибрати модифікацію</p>}
          <p>
            VIN: {vehicle.vin || "не додано"}. Сумісність фізичної деталі
            перевіряється окремо.
          </p>
          <button disabled={busy} onClick={() => prepare("ktype")}>
            Знайти модифікацію
          </button>
          {matches.length > 0 && (
            <select
              aria-label="Кандидати модифікації"
              value={picked}
              onChange={(e) => setPicked(Number(e.target.value))}
            >
              <option value={0}>Оберіть явно</option>
              {matches.map((m) => (
                <option key={m.ktype} value={m.ktype}>
                  {m.modification}
                </option>
              ))}
            </select>
          )}
          <button
            disabled={!picked || busy || picked === Number(vehicle.ktype)}
            onClick={() =>
              run(async (g) => {
                if (
                  vehicle.ktype &&
                  !window.confirm(
                    "Модифікація зміниться. Попередній список, артикули та склад збережуться окремо. Продовжити?",
                  )
                )
                  return;
                await api(
                  root +
                    "/vehicle-modification/select?vehicle_id=" +
                    query(vehicle.id),
                  "POST",
                  { ktype: picked, confirm_change: true },
                );
                const donor = await api("/vehicles/" + query(vehicle.id));
                if (g === epoch.current) onSaved(donor);
              })
            }
          >
            Вибрати модифікацію
          </button>
          {categories.length > 0 && (
            <button
              disabled={busy || !vehicle.ktype}
              onClick={() => void startCatalogue()}
            >
              Оновити список запчастин
            </button>
          )}
          <details>
            <summary>Технічні деталі</summary>
            <p>K-Type: {vehicle.ktype || "не вибрано"}</p>{" "}
            <input
              aria-label="K-Type модифікації"
              type="number"
              min="1"
              value={picked || ""}
              onChange={(e) => setPicked(Number(e.target.value))}
            />
            <p>{policy.oem_reason}</p>
            <p>Збережені списки можна відкрити повторно.</p>
          </details>
        </div>
      )}
      {quote?.resource !== "articles" && paidConfirmation}
      {categories.length > 0 && (
        <DismantlingBoard
          vehicle={vehicle}
          source="professional"
          controls={null}
          onModify={() => setTech((v) => !v)}
          onUpdate={startCatalogue}
          revision={String(boardRevision)}
          translationKick={translationKick}
          onTranslationConsumed={() => setTranslationKick(0)}
          onOpenPart={async (id) => {
            try {
              setDetail(await api("/parts/" + id));
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        />
      )}
      {detail && (
        <Modal
          className="r1-part-dialog"
          title={detail.name}
          onClose={() => setDetail(null)}
        >
          <PartDetail
            part={detail}
            onSaved={(r) => {
              setDetail(r);
              setBoardRevision((n) => n + 1);
              window.dispatchEvent(new Event("warehouse:inventory-changed"));
            }}
            onChanged={() => {
              void api("/parts/" + detail.id).then(setDetail);
              setBoardRevision((n) => n + 1);
              window.dispatchEvent(new Event("warehouse:inventory-changed"));
            }}
          />
        </Modal>
      )}
      {legacyLayout && categories.length > 0 && (
        <div className="vp-layout">
          <div className="vp-main">
            <section className="vp-categories" aria-label="Категорії CarPot">
              <h3>2. Категорії CarPot</h3>
              <p>
                Фільтрують лише основний список деталей. Токени не витрачаються.
              </p>
              <div className="vp-category-grid">
                <button
                  aria-pressed={section === "all"}
                  onClick={() => setSection("all")}
                >
                  <Boxes size={20} />
                  <span>Усі категорії</span>
                  <b>{categories.length}</b>
                </button>
                {workspaceSections.map((s, i) => {
                  const Icon = icons[i];
                  return (
                    <button
                      key={s}
                      aria-pressed={section === s}
                      onClick={() => setSection(s)}
                    >
                      <Icon size={20} />
                      <span>{s}</span>
                      <b>{sectionCounts.get(s)}</b>
                    </button>
                  );
                })}
              </div>
            </section>
            <section className="vp-list">
              <h3>
                3. Запчастини категорії: {section === "all" ? "Усі" : section} (
                {filtered.length})
              </h3>
              <div className="vp-toolbar">
                <button
                  onClick={() =>
                    setSelected((old) =>
                      changeWorkspaceSelection(
                        old,
                        filtered.map((r) => r.pt_id),
                        true,
                      ),
                    )
                  }
                >
                  Вибрати всі ({filtered.length})
                </button>
                <button onClick={() => setSelected([])}>Зняти вибір</button>
                <button
                  disabled={busy || !newSelected.length}
                  onClick={() => setConfirmStock(true)}
                >
                  <Package size={15} /> Додати вибрані ({newSelected.length})
                </button>
              </div>
              <div className="vp-filters">
                <label>
                  <Search size={15} />
                  <input
                    aria-label="Пошук деталей автомобіля"
                    placeholder="Назва, артикул, виробник або OEM…"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                  />
                </label>
                <select
                  aria-label="Статус складу"
                  value={stockFilter}
                  onChange={(e) => setStockFilter(e.target.value)}
                >
                  <option value="all">Склад: усі</option>
                  <option value="stored">Уже додано</option>
                  <option value="new">Нові</option>
                </select>
                <select
                  aria-label="Наявність збережених даних"
                  value={dataFilter}
                  onChange={(e) => setDataFilter(e.target.value)}
                >
                  <option value="all">Дані: усі</option>
                  <option value="saved">Збережено</option>
                  <option value="missing">Без збережених артикулів</option>
                  <option value="uncertain">Невизначені</option>
                </select>
                <select
                  aria-label="Наявність OEM"
                  value={oemFilter}
                  onChange={(e) => setOemFilter(e.target.value)}
                >
                  <option value="all">OEM: усі</option>
                  <option value="yes">Є номер</option>
                  <option value="no">Немає номера</option>
                </select>
              </div>
              <div className="vp-table">
                <div className="vp-row vp-table-head">
                  <span />
                  <span>Назва запчастини</span>
                  <span>Категорія</span>
                  <span>Стан на складі</span>
                  <span>Артикул / виробник</span>
                  <span>OEM номер</span>
                  <span>Дії</span>
                </div>
                {filtered.slice(0, limit).map((r) => {
                  const p = parts.get(r.pt_id),
                    receipt = receipts.get(r.pt_id);
                  return (
                    <div
                      key={r.pt_id}
                      className={
                        "vp-row" + (active === r.pt_id ? " active" : "")
                      }
                    >
                      <input
                        aria-label={"Вибрати " + localized(r)}
                        type="checkbox"
                        checked={selectedSet.has(r.pt_id)}
                        onChange={(e) =>
                          setSelected((old) =>
                            changeWorkspaceSelection(
                              old,
                              [r.pt_id],
                              e.target.checked,
                            ),
                          )
                        }
                      />
                      <button className="vp-name" onClick={() => open(r)}>
                        <strong>{localized(r)}</strong>
                        <small>{r.name}</small>
                      </button>
                      <span className="vp-category-label">{sectionOf(r)}</span>
                      <span>
                        <b className={"vp-chip " + (p ? "stored" : "new")}>
                          {p
                            ? p.quantity > 0
                              ? "Уже на складі"
                              : "Картка без залишку"
                            : "Нова позиція"}
                        </b>
                        <small>
                          {p
                            ? p.quantity + " шт."
                            : receipt?.status === "uncertain"
                              ? "Запит невизначений"
                              : r.classification?.section
                                ? "Наявність перевірити"
                                : "Категорію уточнити"}
                        </small>
                      </span>
                      <span>
                        <b>{p?.article_number || "—"}</b>
                        <small>
                          {p?.article_brand ||
                            (receipt?.stored
                              ? "Варіанти збережені"
                              : "Артикул не призначено")}
                        </small>
                      </span>
                      <span>
                        {p?.oem_number || "—"}
                        <small>
                          {p?.oem_number
                            ? "Джерело — у картці"
                            : "Немає підтверджених даних"}
                        </small>
                      </span>
                      <button onClick={() => open(r)}>Артикули та OEM</button>
                    </div>
                  );
                })}
                {!loading && filtered.length === 0 && (
                  <p className="vp-empty">
                    {categories.length
                      ? "За цими фільтрами деталей немає."
                      : "Список ще не сформовано. Виберіть модифікацію та джерело."}
                  </p>
                )}
              </div>
              {filtered.length > limit && (
                <button
                  className="vp-more"
                  onClick={() => setLimit((n) => n + 60)}
                >
                  Показати ще 60 · {Math.min(limit, filtered.length)} із{" "}
                  {filtered.length}
                </button>
              )}
            </section>
          </div>
          <aside className="vp-actions">
            <h3>Дії</h3>
            <dl>
              <div>
                <dt>Обрано</dt>
                <dd>{selected.length} типів</dd>
              </div>
              <div>
                <dt>Нових вибраних</dt>
                <dd>{newSelected.length}</dd>
              </div>
              <div>
                <dt>Уже на складі</dt>
                <dd>{parts.size}</dd>
              </div>
              <div>
                <dt>Джерело</dt>
                <dd>Plan.Parts</dd>
              </div>
            </dl>
            <button
              disabled={busy || !newSelected.length}
              onClick={() => setConfirmStock(true)}
            >
              ＋ Додати вибрані на склад
            </button>
            <Link to={"/inventory?vehicle_id=" + query(vehicle.id)}>
              Відкрити склад
            </Link>
            <small>
              Складські операції виконуються тільки після підтвердження. API не
              визначає фізичну кількість деталей.
            </small>
          </aside>
        </div>
      )}
      {progress && (
        <div className="vp-progress" role="status">
          <strong>
            {progress.label}: {progress.done} із {progress.total}
          </strong>
          <progress value={progress.done} max={progress.total} />
          <button
            onClick={() => {
              stop.current = true;
            }}
          >
            Зупинити після поточного запиту
          </button>
        </div>
      )}
      {confirmStock && (
        <div
          className="vp-confirm"
          role="alertdialog"
          aria-label="Підтвердження додавання на склад"
        >
          <strong>Додати {newSelected.length} нових типів?</strong>
          <p>
            Ви підтверджуєте по 1 фізичній деталі. Це не кількість із API.
            Наявні залишки не змінюються; повторний виклик не створює дублікати.
          </p>
          <button disabled={busy} onClick={() => void add()}>
            Підтвердити додавання
          </button>
          <button className="secondary" onClick={() => setConfirmStock(false)}>
            Скасувати
          </button>
        </div>
      )}
      {current && (
        <section
          ref={managerRef}
          className="vp-manager"
          aria-label="Артикули та OEM"
        >
          <header>
            <Layers size={19} />
            <h3>Менеджер артикулів та OEM</h3>
            <span>
              Обрана запчастина:{" "}
              <b>{activeLabel || "виберіть рядок у таблиці"}</b>
            </span>
            <button
              className="secondary"
              onClick={() => {
                setQuote(null);
                setConfirmAssign(false);
                setActive(null);
                offerTicket.current++;
                setOfferLoading(null);
              }}
            >
              Закрити панель
            </button>
          </header>
          {current ? (
            <div className="vp-manager-body">
              <div>
                <h4>Артикули виробників</h4>
                <p>
                  Донор №{vehicle.number || "—"} · {vehicle.manufacturer}{" "}
                  {vehicle.model} ·{" "}
                  {currentPart
                    ? "Складська картка " + currentPart.name
                    : "Позиція ще не на складі"}
                </p>
                {currentChoices.length > 1 && (
                  <label>
                    Уточніть складську позицію
                    <select
                      aria-label="Складська позиція для номера"
                      value={targetPartId}
                      onChange={(e) => {
                        setTargetPartId(e.target.value);
                        setConfirmAssign(false);
                        setManualOem(false);
                      }}
                    >
                      <option value="">Оберіть картку явно</option>
                      {currentChoices.map((p, i) => (
                        <option key={p.id} value={p.id}>
                          {i + 1}. {p.name} ·{" "}
                          {p.article_number || "без артикула"} · {p.quantity}{" "}
                          шт.
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {offerLoading === current.pt_id && (
                  <p role="status">
                    Відкриваємо збережені артикули · 0 токенів…
                  </p>
                )}
                {Object.prototype.hasOwnProperty.call(
                  offers,
                  current.pt_id,
                ) && (
                  <p role="status">
                    Збережено {currentOffers.length} варіантів артикулів ·
                    перегляд без токенів.
                  </p>
                )}
                {currentOffers.length ? (
                  <div className="vp-offer-list">
                    {currentOffers.slice(0, offerLimit).map((a) => (
                      <label className="vp-offer" key={a.art_id}>
                        <input
                          type="radio"
                          name="workspace-offer"
                          checked={offerSelection === a.art_id}
                          disabled={busy}
                          onChange={() => {
                            setOfferSelection(a.art_id);
                            setConfirmAssign(false);
                          }}
                        />
                        <span>
                          <b>
                            {a.article_nr} · {a.brand}
                          </b>
                          <small>
                            {a.part_name || "Назву джерело не вказало"} ·
                            Plan.Parts · збережено
                          </small>
                          {Object.keys(a.characteristics || {}).length > 0 && (
                            <small>
                              {Object.entries(a.characteristics).map(
                                ([name, value]) => (
                                  <span key={name} style={{ display: "block" }}>
                                    {name}: {String(value)}
                                  </span>
                                ),
                              )}
                              Дані джерела не підтверджують сумісність із VIN.
                            </small>
                          )}
                        </span>
                      </label>
                    ))}
                    {currentOffers.length > offerLimit && (
                      <button onClick={() => setOfferLimit((n) => n + 100)}>
                        Ще 100 варіантів · {offerLimit} із{" "}
                        {currentOffers.length}
                      </button>
                    )}
                  </div>
                ) : offerLoading === current.pt_id ? null : (
                  <p>
                    {Object.prototype.hasOwnProperty.call(offers, current.pt_id)
                      ? "Збережена відповідь порожня: пропозицій не знайдено"
                      : receipts.get(current.pt_id)?.received_at
                        ? "Отримано раніше — дані потребують відновлення"
                        : "Збережених варіантів поки немає"}
                  </p>
                )}
                {offerLoading !== current.pt_id && (
                  <button
                    disabled={
                      busy ||
                      policy.max_tokens?.articles == null ||
                      !policy.terms_confirmed
                    }
                    onClick={prepareArticles}
                  >
                    {Object.prototype.hasOwnProperty.call(
                      offers,
                      current.pt_id,
                    ) || receipts.has(current.pt_id)
                      ? "Отримати нові артикули"
                      : "Отримати артикули"}{" "}
                    ·{" "}
                    {priceQuote(policy.max_tokens?.articles, 1).known
                      ? "до " + policy.max_tokens.articles + " токенів"
                      : "вартість не підтверджена"}
                  </button>
                )}
                {quote?.resource === "articles" && paidConfirmation}
                {(!policy.terms_confirmed ||
                  policy.max_tokens?.articles == null) && (
                  <p>
                    Нові запити вимкнені: тариф або умови збереження не
                    підтверджені. Збережені артикули доступні без оплати.
                  </p>
                )}
                {receipts.has(current.pt_id) &&
                  !Object.prototype.hasOwnProperty.call(
                    offers,
                    current.pt_id,
                  ) &&
                  offerLoading !== current.pt_id && (
                    <button disabled={busy} onClick={() => open(current)}>
                      Повторити відкриття збережених · 0 токенів
                    </button>
                  )}
              </div>
              <div>
                <h4>OEM автовиробника</h4>
                <strong>
                  {currentPart?.oem_number || "Немає підтверджених даних"}
                </strong>
                <p>
                  {currentPart?.oem_provenance?.source === "manual"
                    ? "Підтверджено вручну. Це окреме поле від aftermarket."
                    : policy.oem_reason ||
                      "Метод отримання OEM не підтверджено."}
                </p>
                <button
                  disabled={!currentPart || busy}
                  onClick={() => setManualOem(!manualOem)}
                >
                  Підтвердити OEM вручну
                </button>
                {manualOem && currentPart && (
                  <PartCharacteristicsEditor
                    part={currentPart}
                    kind="oem"
                    onSaved={() => {
                      setManualOem(false);
                      void run(refresh);
                    }}
                    onClose={() => setManualOem(false)}
                  />
                )}
              </div>
              <div className="vp-manager-actions">
                <label>
                  Українська назва
                  <input
                    maxLength={200}
                    value={localized(current)}
                    onChange={(e) =>
                      setNameDraft((old) => ({
                        ...old,
                        [current.pt_id]: e.target.value,
                      }))
                    }
                  />
                </label>
                <button
                  disabled={busy || !current?.checklist_id}
                  onClick={() => void saveName()}
                >
                  Зберегти українську назву
                </button>
                <button
                  disabled={
                    !currentPart ||
                    !chosen ||
                    busy ||
                    offerLoading === current.pt_id
                  }
                  onClick={() => setConfirmAssign(true)}
                >
                  Призначити артикул
                </button>
                {confirmAssign && chosen && (
                  <div role="alertdialog" aria-label="Підтвердження артикула">
                    <p>
                      Записати {chosen.article_nr} · {chosen.brand} у «
                      {currentPart?.name}», донор №{vehicle.number || "—"}? OEM
                      і залишок не змінюються.
                    </p>
                    <button disabled={busy} onClick={() => void assign()}>
                      Підтвердити запис номера
                    </button>
                    <button
                      className="secondary"
                      onClick={() => setConfirmAssign(false)}
                    >
                      Скасувати
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <p className="vp-empty">
              Виберіть запчастину в таблиці, щоб переглянути й призначити
              номери.
            </p>
          )}
          <footer>
            <span>Зміни запчастин зберігаються автоматично.</span>
          </footer>
        </section>
      )}
    </section>
  );
}
