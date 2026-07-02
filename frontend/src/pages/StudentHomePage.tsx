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
      <p style={{ color: "#555" }}>{t("student.home.placeholder")}</p>
    </main>
  );
}
