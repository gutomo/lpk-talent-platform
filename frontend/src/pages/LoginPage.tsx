import { useState } from "react";

import { ApiError, login, type User } from "../api/client";
import { getLocale, setLocale, t, type Locale } from "../i18n";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: 10,
  fontSize: 16,
  boxSizing: "border-box",
};

export default function LoginPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // t() reads module state; this mirror only forces a re-render on toggle.
  const [, setLocaleState] = useState<Locale>(getLocale());

  function toggleLocale() {
    const next: Locale = getLocale() === "id" ? "ja" : "id";
    setLocale(next);
    setLocaleState(next);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      onLogin(user);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(t("login.error.invalid"));
      } else {
        setError(t("login.error.network"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 400,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div style={{ textAlign: "right", marginBottom: 8 }}>
        <button onClick={toggleLocale} style={{ padding: "4px 10px" }}>
          {t("login.switchLocale")}
        </button>
      </div>
      <h1 style={{ fontSize: 24 }}>{t("app.title")}</h1>
      <p style={{ color: "#555" }}>{t("app.tagline")}</p>
      <form onSubmit={handleSubmit}>
        <label style={{ display: "block", marginBottom: 12 }}>
          {t("login.email")}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            style={inputStyle}
          />
        </label>
        <label style={{ display: "block", marginBottom: 12 }}>
          {t("login.password")}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            style={inputStyle}
          />
        </label>
        {error !== null && (
          <p role="alert" style={{ color: "#b00020" }}>
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          style={{ width: "100%", padding: 12, fontSize: 16 }}
        >
          {submitting ? t("login.submitting") : t("login.submit")}
        </button>
      </form>
    </main>
  );
}
