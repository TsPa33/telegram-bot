import {
  Archive as ArchiveIcon,
  ClipboardList,
  Search,
  Upload,
} from "lucide-react";
import { useState } from "react";
import { all, api, labels, type Row } from "../api";
import { Empty, Modal } from "../components";

import { Confirm, Heading, State, useLoad, type Notify } from "../shared";
export default function Catalog({ notify }: { notify: Notify }) {
  const {
    data: rows,
    error,
    loading,
    reload,
  } = useLoad(() => all("/categories"), []);
  const [importing, setImporting] = useState(false),
    [q, setQ] = useState(""),
    [confirm, setConfirm] = useState<Row | null>(null);
  const byId = new Map(rows?.map((r) => [r.id, r]));
  function path(row: Row): string {
    return row.parent_id && byId.has(row.parent_id)
      ? path(byId.get(row.parent_id)!) + " / " + row.name
      : row.name;
  }
  const filtered = rows
    ?.filter((r) => path(r).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => path(a).localeCompare(path(b), "uk"));
  return (
    <>
      <Heading
        eyebrow="СТРУКТУРА НОМЕНКЛАТУРИ"
        title="Каталог запчастин"
        description="Категорії, підкатегорії та стандартні деталі для чеклістів."
      >
        <button className="secondary" onClick={() => setImporting(true)}>
          <Upload size={17} />
          Імпорт категорій
        </button>
      </Heading>
      <div className="notice">
        <ClipboardList size={20} />
        <div>
          <b>Каталог наповнюється лише з вашого джерела</b>
          <p>
            Вихідний файл AdvL_Nes_Tree_Raw.txt не постачається. Завантажте
            перевірену таксономію у форматі UTF-8 JSON. Імпорт не створює
            фізичних залишків.
          </p>
        </div>
      </div>
      <div className="toolbar">
        <label className="search">
          <Search size={17} />
          <input
            placeholder="Пошук в ієрархії…"
            aria-label="Пошук категорій"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <span className="muted">{rows?.length || 0} елементів</span>
      </div>
      <State error={error} loading={loading} />
      <section className="panel">
        {filtered?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Категорія / повний шлях</th>
                  <th>Тип</th>
                  <th>Стабільний ключ</th>
                  <th>Джерело</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <b>{c.name}</b>
                      <small>{path(c)}</small>
                    </td>
                    <td>
                      <span className="pill">{labels[c.kind]}</span>
                    </td>
                    <td>
                      <code>{c.external_key}</code>
                    </td>
                    <td>{c.source}</td>
                    <td>
                      <button
                        aria-label={`Архівувати ${c.name}`}
                        className="icon-button"
                        onClick={() => setConfirm(c)}
                      >
                        <ArchiveIcon size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !loading && (
            <Empty title="Додайте структуру каталогу">
              Імпортуйте категорії, щоб автоматично готувати чеклісти донорів.
              Запчастини також можна додавати вручну.
            </Empty>
          )
        )}
      </section>
      {importing && (
        <Modal
          title="Контрольований імпорт категорій"
          onClose={() => setImporting(false)}
        >
          <ImportCategories
            onDone={() => {
              setImporting(false);
              reload();
              notify("Категорії імпортовано");
            }}
          />
        </Modal>
      )}
      {confirm && (
        <Confirm
          destructive
          title="Архівувати категорію?"
          text="Категорія та її дочірні елементи не братимуть участі в нових чеклістах. Історичні посилання зберігаються."
          onClose={() => setConfirm(null)}
          onConfirm={async () => {
            await api("/archive/categories/" + confirm.id, "POST");
            setConfirm(null);
            reload();
          }}
        />
      )}
    </>
  );
}
function ImportCategories({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function upload(dry: boolean) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api("/categories/import-file?dry_run=" + dry, "POST", fd);
      if (dry) setPreview(r);
      else onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <p>
        UTF-8 JSON до 4 МБ. Кожен вузол має власний <code>key</code>,{" "}
        <code>parent_key</code>, <code>name</code> і <code>kind</code>:
        category, subcategory або part. Поле source визначає джерело.
      </p>
      <p className="muted">
        Повторний імпорт тих самих ключів безпечний. Зміна їхніх назв або
        зв’язків відхиляється. Однакові назви під різними батьками дозволені.
      </p>
      <label className="upload-box">
        <Upload />
        <b>Оберіть JSON-файл</b>
        <input
          aria-label="JSON-файл категорій"
          type="file"
          accept=".json,application/json"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
            setPreview(null);
            setError("");
          }}
        />
        {file?.name}
      </label>
      {preview && (
        <div className="notice">
          Перевірено: {preview.total}. Нових: {preview.created}. Існує:{" "}
          {preview.existing}.
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="modal-actions">
        <button disabled={!file || busy} onClick={() => upload(true)}>
          Перевірити файл
        </button>
        <button
          className="primary"
          disabled={!preview || busy}
          onClick={() => upload(false)}
        >
          {busy ? "Обробка…" : "Підтвердити імпорт"}
        </button>
      </div>
    </>
  );
}
