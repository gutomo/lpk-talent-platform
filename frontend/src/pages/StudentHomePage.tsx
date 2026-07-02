import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getStreak, type Streak, type User } from "../api/client";
import PageHeader from "../components/PageHeader";
import { t } from "../i18n";

function MenuCard({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link
      to={to}
      style={{
        display: "block",
        padding: 16,
        border: "1px solid #ddd",
        borderRadius: 12,
        textDecoration: "none",
        color: "inherit",
        background: "#fff",
        marginBottom: 12,
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 14, color: "#555" }}>{desc}</div>
    </Link>
  );
}

export default function StudentHomePage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [streak, setStreak] = useState<Streak | null>(null);

  useEffect(() => {
    getStreak()
      .then(setStreak)
      .catch(() => {
        // streak はホームの補助情報。取得失敗時は表示しないだけにする。
      });
  }, []);

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

      {streak !== null && (
        <section
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "12px 16px",
            borderRadius: 12,
            background: streak.days > 0 ? "#fff3e0" : "#eef1f6",
            border: `1px solid ${streak.days > 0 ? "#ffd9a0" : "#dde3ec"}`,
            marginBottom: 16,
          }}
        >
          <span style={{ fontSize: 28 }} aria-hidden="true">
            🔥
          </span>
          <div>
            <div style={{ fontSize: 17, fontWeight: 600 }}>
              {t("student.home.streak", { n: streak.days })}
            </div>
            <div style={{ fontSize: 13, color: "#555" }}>
              {streak.active_today
                ? t("student.home.streak.doneToday")
                : t("student.home.streak.notYet")}
            </div>
          </div>
        </section>
      )}

      <nav>
        <MenuCard
          to="/student/pronunciation"
          title={t("student.home.menu.pronunciation")}
          desc={t("student.home.menu.pronunciationDesc")}
        />
        <MenuCard
          to="/student/conversation"
          title={t("student.home.menu.conversation")}
          desc={t("student.home.menu.conversationDesc")}
        />
        <MenuCard
          to="/student/interview"
          title={t("student.home.menu.interview")}
          desc={t("student.home.menu.interviewDesc")}
        />
      </nav>
    </main>
  );
}
