import {useCan,roleLabel,ADVANCED_PERMISSIONS} from '../permissions';
import { ShieldCheck, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import DismantlingCatalogImport from "../DismantlingCatalogImport";
import { api, type Row } from "../api";

import { Heading, State, useLoad } from "../shared";
export default function Settings({ user }: { user: Row }) {
  const can=useCan();
  const { data, error, loading } = useLoad(() => api("/settings"), []);
  return (
    <>
      <Heading
        eyebrow="РОБОЧИЙ ПРОСТІР"
        title="Налаштування"
        description="Обліковий запис і можливості вашого незалежного складу."
      />
      {can('team.view')&&<Link className="button" to="/team">Команда</Link>}
      <nav className="settings-tools" aria-label="Додаткові розділи">
        {can('catalog.view')&&<Link className="button" to="/catalog">Довідник запчастин</Link>}
        {can('inventory.archive')&&can('inventory.view')&&<Link className="button" to="/archive">Архів</Link>}
        {can('audit.view')&&<Link className="button" to={ADVANCED_PERMISSIONS.every(can)?'/operations':'/analytics'}>Журнал операцій</Link>}
        {ADVANCED_PERMISSIONS.every(can)&&<Link className="button" to="/inventory/advanced">Розширений склад</Link>}
        <p>Операції обмежені призначеними дозволами.</p>
        {can('audit.view')&&<Link className="button" to="/analytics">Аудит</Link>}
        {can('catalog.import')&&<a className="button" href="#catalog-import">Імпорт каталогу</a>}
      </nav>
      {can('catalog.import')&&<section className="panel padded" id="catalog-import"><DismantlingCatalogImport onImported={()=>{}}/></section>}
      <State error={error} loading={loading} />
      <div className="two-column">
        <section className="panel padded">
          <h2>Обліковий запис</h2>
          <dl className="details">
            <div>
              <dt>Ім’я</dt>
              <dd>{user.name}</dd>
            </div>
            <div>
              <dt>Пошта</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Роль</dt>
              <dd>{roleLabel(user.role)}</dd>
            </div>
            <div>
              <dt>Валюта</dt>
              <dd>Українська гривня · UAH</dd>
            </div>
          </dl>
          <div className="notice">
            <ShieldCheck size={19} />
            Дані цього акаунта доступні тільки після авторизації в ньому.
          </div>
        </section>
        <section className="panel padded">
          <h2>Можливості системи</h2>
          <dl className="details">
            <div>
              <dt>Зберігання фото</dt>
              <dd>{data?.photos_enabled ? "Увімкнено" : "Не налаштовано"}</dd>
            </div>
            <div>
              <dt>Каталог категорій</dt>
              <dd>Контрольований імпорт</dd>
            </div>
            <div>
              <dt>CarPot-інтеграція</dt>
              <dd>Незалежний режим</dd>
            </div>
            <div>
              <dt>Історія операцій</dt>
              <dd>Незмінна, без видалення</dd>
            </div>
          </dl>
          {can('catalog.import')&&<Link className="button" to="/catalog"><Upload size={16}/>Керувати каталогом</Link>}
        </section>
      </div>
    </>
  );
}
