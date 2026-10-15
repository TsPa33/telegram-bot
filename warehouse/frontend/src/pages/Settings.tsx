import { ShieldCheck, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type Row } from "../api";

import { Heading, State, useLoad } from "../shared";
export default function Settings({ user }: { user: Row }) {
  const { data, error, loading } = useLoad(() => api("/settings"), []);
  return (
    <>
      <Heading
        eyebrow="РОБОЧИЙ ПРОСТІР"
        title="Налаштування"
        description="Обліковий запис і можливості вашого незалежного складу."
      />
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
              <dd>Власник</dd>
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
          <Link className="button" to="/catalog">
            <Upload size={16} />
            Керувати каталогом
          </Link>
        </section>
      </div>
    </>
  );
}
