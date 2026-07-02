import type { User } from "../api/client";
import { t } from "../i18n";

export default function PageHeader({
  title,
  user,
  onLogout,
}: {
  title: string;
  user: User;
  onLogout: () => void;
}) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        flexWrap: "wrap",
        marginBottom: 16,
      }}
    >
      <div>
        <div style={{ fontSize: 12, color: "#666" }}>{t("app.title")}</div>
        <h1 style={{ margin: 0, fontSize: 22 }}>{title}</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 14, color: "#333" }}>{user.name}</span>
        <button onClick={onLogout} style={{ padding: "6px 12px" }}>
          {t("common.logout")}
        </button>
      </div>
    </header>
  );
}
