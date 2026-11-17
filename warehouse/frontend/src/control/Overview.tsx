import { ArrowRight, Wallet } from "lucide-react";
import { date, type Row } from "./api";
import { profileHref, periodCount } from "./model";
import {
  Empty,
  Feedback,
  PageHeader,
  Panel,
  useLoad,
  useRevision,
} from "./shared";
import { TaskSummary } from "./Tasks";
export default function Overview({
  overview,
  loading,
  error,
  retry,
  revision,
}: {
  overview: Row | null;
  loading: boolean;
  error: string;
  retry: () => void;
  revision: number;
}) {
  const [localRevision, refresh] = useRevision(),
    companies = useLoad<Row>(
      "/companies?limit=5&sort=name",
      revision + localRevision,
    ),
    tasks = useLoad<Row[]>("/tasks", revision + localRevision);
  const metrics = [
    ["Усього клієнтів", overview?.workspaces, "У межах вашого доступу"],
    [
      "Тарифний період чинний",
      periodCount(overview, ["ACTIVE", "TRIAL", "GRACE"]),
      "Включно з trial та пільговим періодом",
    ],
    ["Нові за 30 днів", overview?.new_30d, "За датою реєстрації"],
    [
      "Період завершено",
      periodCount(overview, ["EXPIRED"]),
      "Тарифний стан, а не підтвердження несплати",
    ],
  ];
  return (
    <>
      <PageHeader
        title="Огляд клієнтів"
        subtitle="Тарифний контекст і наступні дії команди."
        action={
          <a className="cc-button" href="#/clients">
            Усі клієнти <ArrowRight size={16} />
          </a>
        }
      />
      <Feedback loading={loading} error={error} retry={retry} />
      <div className="cc-metrics">
        {metrics.map(([label, value, caption]) => (
          <article className="cc-metric" key={String(label)}>
            <span>{label}</span>
            <strong>{value == null ? "Немає даних" : value}</strong>
            <small>{caption}</small>
          </article>
        ))}
      </div>
      <div className="cc-two-col">
        <Panel
          title="Бізнес-активність"
          subtitle="Час останньої складської операції · вибірка до 5 компаній"
          action={<a href="#/clients">Каталог →</a>}
        >
          <Feedback
            loading={companies.loading}
            error={companies.error}
            retry={refresh}
          />
          {companies.data &&
            (companies.data.items.length ? (
              companies.data.items.map((c: Row) => (
                <a
                  className="cc-activity-row"
                  href={profileHref(c.id, "activity")}
                  key={c.id}
                >
                  <div>
                    <strong>{c.display_name}</strong>
                    <small>
                      {c.business_activity_coverage ===
                      "warehouse stock operations only"
                        ? "Складські операції Warehouse"
                        : "Покриття активності неповне"}
                    </small>
                  </div>
                  <time>{date(c.business_activity_at)}</time>
                </a>
              ))
            ) : (
              <Empty title="У доступній вибірці немає компаній" />
            ))}
        </Panel>
        <Panel
          title="Фокус команди"
          subtitle="Відкриті завдання з доступної вибірки до 100 записів"
          action={<a href="#/queue">Черга →</a>}
        >
          <Feedback
            loading={tasks.loading}
            error={tasks.error}
            retry={refresh}
          />
          {tasks.data && <TaskSummary tasks={tasks.data} />}
        </Panel>
      </div>
      <div className="cc-finance-note">
        <Wallet size={20} />
        <div>
          <strong>Платні підписки та доходи</strong>
          <p>
            Загальні фінансові показники недоступні без перевіреного джерела та
            узгодженої методології. Чинний тарифний період не є підтвердженням
            платежу.
          </p>
        </div>
      </div>
      <Panel title="Потребують перевірки">
        <div className="cc-panel-body cc-actions">
          <a className="cc-button" href="#/clients?status=EXPIRED">
            Завершені періоди
          </a>
          <a className="cc-button" href="#/clients?status=UNKNOWN">
            Недостатньо даних
          </a>
          <a className="cc-button" href="#/clients?linking=conflict">
            Конфлікти зв’язків
          </a>
          <a className="cc-button" href="#/queue">
            Завдання команди
          </a>
        </div>
      </Panel>
    </>
  );
}
