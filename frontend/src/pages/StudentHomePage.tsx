import { Link } from "react-router-dom";

import type { User } from "../api/client";
import PageHeader from "../components/PageHeader";
import { t } from "../i18n";

export default function StudentHomePage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  return (
    <main
      style={{
        maxWidth: 480,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("student.home.title")} user={user} onLogout={onLogout} />
      <p style={{ fontSize: 18 }}>{t("student.home.welcome", { name: user.name })}</p>
      <nav>
        <Link
          to="/student/pronunciation"
          style={{
            display: "block",
            padding: 16,
            border: "1px solid #ddd",
            borderRadius: 12,
            textDecoration: "none",
            color: "inherit",
            background: "#fff",
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>
            {t("student.home.menu.pronunciation")}
          </div>
          <div style={{ fontSize: 14, color: "#555" }}>
            {t("student.home.menu.pronunciationDesc")}
          </div>
        </Link>
      </nav>
    </main>
  );
}
