import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getReviewQueue, getStudents, type StudentListItem, type User } from "../api/client";
import PageHeader from "../components/PageHeader";
import { scoreColor } from "../components/TrendChart";
import { getLocale, t } from "../i18n";

const cellStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderBottom: "1px solid #ddd",
  textAlign: "left",
  fontSize: 14,
};

const numCellStyle: React.CSSProperties = {
  ...cellStyle,
  textAlign: "right",
  whiteSpace: "nowrap",
};

function formatLastActive(iso: string | null): string {
  if (iso === null) return t("teacher.students.never");
  return new Date(iso).toLocaleDateString(getLocale() === "ja" ? "ja-JP" : "id-ID", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// 数値セル。未計測は "-"、値ありはスコア色で強調する。
function Score({ value, suffix }: { value: number | null; suffix?: string }) {
  if (value === null) return <span style={{ color: "#9aa5b1" }}>-</span>;
  return (
    <span style={{ color: scoreColor(value), fontWeight: 600 }}>
      {value}
      {suffix}
    </span>
  );
}

export default function TeacherStudentsPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [students, setStudents] = useState<StudentListItem[] | null>(null);
  const [queueCount, setQueueCount] = useState<number | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getStudents()
      .then(setStudents)
      .catch(() => setError(true));
    // キュー件数はバッジ表示のみなので、失敗しても一覧表示は妨げない。
    getReviewQueue()
      .then((items) => setQueueCount(items.length))
      .catch(() => setQueueCount(null));
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
      <p style={{ marginTop: 0, display: "flex", gap: 10, flexWrap: "wrap" }}>
        {user.role === "admin" && (
          <Link
            to="/admin/kpi"
            style={{
              display: "inline-block",
              padding: "8px 14px",
              border: "1px solid #1a5fb4",
              borderRadius: 10,
              color: "#1a5fb4",
              textDecoration: "none",
              fontSize: 14,
            }}
          >
            {t("admin.kpi.link")}
          </Link>
        )}
        <Link
          to="/teacher/review"
          style={{
            display: "inline-block",
            padding: "8px 14px",
            border: "1px solid #1a5fb4",
            borderRadius: 10,
            color: "#1a5fb4",
            textDecoration: "none",
            fontSize: 14,
          }}
        >
          {t("teacher.queue.link")}
          {queueCount !== null && queueCount > 0 && (
            <span
              style={{
                marginLeft: 8,
                padding: "1px 8px",
                borderRadius: 999,
                background: "#c62828",
                color: "#fff",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {queueCount}
            </span>
          )}
        </Link>
      </p>
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
                  <th style={cellStyle}>{t("teacher.students.cohort")}</th>
                  <th style={{ ...numCellStyle, fontWeight: 700 }}>
                    {t("teacher.students.pron")}
                  </th>
                  <th style={{ ...numCellStyle, fontWeight: 700 }}>
                    {t("teacher.students.interview")}
                  </th>
                  <th style={{ ...numCellStyle, fontWeight: 700 }}>
                    {t("teacher.students.attendance")}
                  </th>
                  <th style={cellStyle}>{t("teacher.students.lastActive")}</th>
                  <th style={cellStyle}>{t("teacher.students.alert")}</th>
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
                    <td style={cellStyle}>{s.cohort_name ?? "-"}</td>
                    <td style={numCellStyle}>
                      <Score value={s.pron_avg_accuracy} />
                    </td>
                    <td style={numCellStyle}>
                      <Score value={s.interview_latest_total} />
                      {s.interview_sessions > 0 && (
                        <span style={{ color: "#666", fontSize: 12 }}>
                          {" "}
                          / {t("teacher.students.interviewCount", { n: s.interview_sessions })}
                        </span>
                      )}
                    </td>
                    <td style={numCellStyle}>
                      <Score value={s.attendance_rate} suffix="%" />
                    </td>
                    <td style={cellStyle}>{formatLastActive(s.last_active_at)}</td>
                    <td style={cellStyle}>
                      {s.risk_level === "risk" && (
                        <span
                          title={s.risk_flags
                            .map((flag) => t(`teacher.detail.risk.${flag}`))
                            .join(" / ")}
                          style={{
                            fontSize: 12,
                            fontWeight: 600,
                            padding: "2px 10px",
                            borderRadius: 999,
                            background: "#fdecea",
                            color: "#c62828",
                            whiteSpace: "nowrap",
                          }}
                        >
                          ⚠ {t("teacher.detail.riskBadge")}
                        </span>
                      )}
                    </td>
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
