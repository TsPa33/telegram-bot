import { CarFront, Package, ShieldCheck, Warehouse } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Row } from "../api";
import { RecordForm } from "../components";

export default function Auth({ onLogin }: { onLogin: (u: Row) => void }) {
  const [register, setRegister] = useState(false);
  const [registrationAllowed, setRegistrationAllowed] = useState(false);
  useEffect(() => {
    api("/auth/options")
      .then((r) => setRegistrationAllowed(r.registration_enabled))
      .catch(() => setRegistrationAllowed(false));
  }, []);
  return (
    <div className="auth-page">
      <div className="auth-story">
        <Link to="/" className="brand">
          <span className="brand-icon">
            <Warehouse />
          </span>
          <span>
            CarPot<strong>WAREHOUSE</strong>
          </span>
        </Link>
        <div>
          <span className="eyebrow">ПРОСТІР ДЛЯ ВАШОГО БІЗНЕСУ</span>
          <h1>
            Кожна деталь.
            <br />
            Під контролем.
          </h1>
          <p>
            Донори, запчастини та рух залишків — в одному робочому просторі.
          </p>
          <div className="auth-features">
            <span>
              <CarFront />
              Облік донорів
            </span>
            <span>
              <Package />
              Точні залишки
            </span>
            <span>
              <ShieldCheck />
              Історія кожної операції
            </span>
          </div>
        </div>
        <small>Незалежна система управління автомобільним складом</small>
      </div>
      <div className="auth-form">
        <div className="auth-card">
          <span className="eyebrow">CARPOT WAREHOUSE</span>
          <h2>
            {register ? "Створіть свій робочий простір" : "З поверненням"}
          </h2>
          <p>
            {register
              ? "Почніть із чистого складу. Додавайте тільки свої дані."
              : "Увійдіть, щоб продовжити роботу зі складом."}
          </p>
          <RecordForm
            key={String(register)}
            fields={[
              ...(register
                ? [{ key: "name", label: "Ваше ім’я", required: true }]
                : []),
              {
                key: "email",
                label: "Електронна пошта",
                type: "email",
                required: true,
              },
              {
                key: "password",
                label: "Пароль",
                type: "password",
                required: true,
                hint: "Щонайменше 12 символів",
              },
            ]}
            submit={register ? "Створити обліковий запис" : "Увійти"}
            onSave={async (data) => {
              const res = await api(
                register ? "/auth/register" : "/auth/login",
                "POST",
                data,
              );
              onLogin(res.user);
            }}
          />
          {registrationAllowed ? (
            <>
              <div className="auth-switch">
                {register
                  ? "Уже маєте обліковий запис?"
                  : "Ще немає облікового запису?"}{" "}
                <button onClick={() => setRegister(!register)}>
                  {register ? "Увійти" : "Зареєструватися"}
                </button>
              </div>
            </>
          ) : (
            <p className="auth-switch">
              Доступ надає власник робочого простору.
            </p>
          )}
          <div className="auth-security">
            <ShieldCheck size={15} />
            Захищена сесія · Дані відокремлені між акаунтами
          </div>
        </div>
      </div>
    </div>
  );
}
