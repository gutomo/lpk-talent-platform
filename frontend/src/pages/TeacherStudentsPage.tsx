import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getStudents, type StudentListItem, type User } from "../api/client";
import PageHeader from "../components/PageHeader";
import { getLocale, t } from "../i18n";

const cellStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderBottom: "1px solid #ddd",
  textAlign: "left",
  fontSize: 14,
};

function formatLastActive(iso: string | null): string {
  if (iso === null) return t("teacher.students.never");
  return new Date(iso).toLocaleDateString(getLocale() === "ja" ? "ja-JP" : "id-ID", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function TeacherStudentsPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [students, setStudents] = useState<StudentListItem[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getStudents()
      .then(setStudents)
      .catch(() => setError(true));
  }, []);

  return (
    <main
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("teacher.students.title")} user={user} onLogout={onLogout} />
      {error && (
        <p role="alert" style={{ color: "#b00020" }}>
          {t("common.error")}
        </p>
      )}
      {!error && students === null && <p>{t("common.loading")}</p>}
      {students !== null && students.length === 0 && <p>{t("teacher.students.empty")}</p>}
      {students !== null && students.length > 0 && (
        <>
          <p style={{ color: "#555" }}>{t("teacher.students.count", { n: students.length })}</p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={cellStyle}>{t("teacher.students.name")}</th>
                  <th style={cellStyle}>{t("teacher.students.email")}</th>
                  <th style={cellStyle}>{t("teacher.students.cohort")}</th>
                  <th style={cellStyle}>{t("teacher.students.lastActive")}</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id}>
                    <td style={cellStyle}>
                      <Link to={`/teacher/students/${s.id}`} style={{ color: "#1a5fb4" }}>
                        {s.name}
                      </Link>
                    </td>
                    <td style={cellStyle}>{s.email}</td>
                    <td style={cellStyle}>{s.cohort_name ?? "-"}</td>
                    <td style={cellStyle}>{formatLastActive(s.last_active_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
