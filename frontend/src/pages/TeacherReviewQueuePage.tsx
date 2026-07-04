import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { completeReview, getReviewQueue, type ReviewQueueItem, type User } from "../api/client";
import PageHeader from "../components/PageHeader";
import { scoreColor } from "../components/TrendChart";
import { t } from "../i18n";

const cellStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderBottom: "1px solid #ddd",
  textAlign: "left",
  fontSize: 14,
};

// ISO日時の日付部分。キューの表示は YYYY-MM-DD で十分。
function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

export default function TeacherReviewQueuePage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [items, setItems] = useState<ReviewQueueItem[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  // 確認操作中の evaluation_id。二重送信防止と行単位のボタン表示に使う。
  const [completing, setCompleting] = useState<number | null>(null);
  const [actionError, setActionError] = useState(false);

  useEffect(() => {
    getReviewQueue()
      .then(setItems)
      .catch(() => setLoadError(true));
  }, []);

  function complete(item: ReviewQueueItem) {
    if (completing !== null) return;
    setCompleting(item.evaluation_id);
    setActionError(false);
    completeReview(item.evaluation_id)
      .then(() => {
        setItems((prev) =>
          prev === null ? prev : prev.filter((i) => i.evaluation_id !== item.evaluation_id),
        );
      })
      .catch(() => setActionError(true))
      .finally(() => setCompleting(null));
  }

  return (
    <main
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("teacher.queue.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0 }}>
        <Link to="/teacher/students">{t("teacher.detail.back")}</Link>
      </p>
      <p style={{ color: "#555", fontSize: 14 }}>{t("teacher.queue.desc")}</p>

      {loadError && (
        <p role="alert" style={{ color: "#b00020" }}>
          {t("common.error")}
        </p>
      )}
      {actionError && (
        <p role="alert" style={{ color: "#b00020" }}>
          {t("teacher.queue.error")}
        </p>
      )}
      {!loadError && items === null && <p>{t("common.loading")}</p>}
      {items !== null && items.length === 0 && <p>{t("teacher.queue.empty")}</p>}
      {items !== null && items.length > 0 && (
        <>
          <p style={{ color: "#555" }}>{t("teacher.queue.count", { n: items.length })}</p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={cellStyle}>{t("teacher.queue.student")}</th>
                  <th style={cellStyle}>{t("teacher.queue.scenario")}</th>
                  <th style={cellStyle}>{t("teacher.queue.mode")}</th>
                  <th style={{ ...cellStyle, textAlign: "right" }}>{t("teacher.queue.total")}</th>
                  <th style={cellStyle}>{t("teacher.queue.submittedAt")}</th>
                  <th style={{ ...cellStyle, textAlign: "right" }}>
                    {t("teacher.queue.waiting")}
                  </th>
                  <th style={cellStyle} />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.evaluation_id}>
                    <td style={cellStyle}>
                      <Link
                        to={`/teacher/students/${item.student_id}`}
                        style={{ color: "#1a5fb4" }}
                      >
                        {item.student_name}
                      </Link>
                    </td>
                    <td style={cellStyle} lang="ja">
                      {item.title_ja ?? item.scenario}
                    </td>
                    <td style={cellStyle}>{t(`itv.mode.${item.mode}`)}</td>
                    <td
                      style={{
                        ...cellStyle,
                        textAlign: "right",
                        fontWeight: 600,
                        color: scoreColor(item.total),
                      }}
                    >
                      {item.total}
                    </td>
                    <td style={{ ...cellStyle, whiteSpace: "nowrap" }}>
                      {formatDate(item.created_at)}
                    </td>
                    <td
                      style={{
                        ...cellStyle,
                        textAlign: "right",
                        // 3日以上の滞留は赤字で目立たせる（KPIの参考値）。
                        color: item.waiting_days >= 3 ? "#c62828" : "#333",
                        fontWeight: item.waiting_days >= 3 ? 600 : 400,
                      }}
                    >
                      {t("teacher.queue.waitingDays", { n: item.waiting_days })}
                    </td>
                    <td style={{ ...cellStyle, whiteSpace: "nowrap" }}>
                      <Link
                        to={`/teacher/students/${item.student_id}/interviews/${item.session_id}`}
                        style={{ color: "#1a5fb4", marginRight: 12 }}
                      >
                        {t("teacher.queue.open")}
                      </Link>
                      <button
                        onClick={() => complete(item)}
                        disabled={completing !== null}
                        style={{
                          padding: "6px 10px",
                          fontSize: 13,
                          background: "#fff",
                          color: "#1a5fb4",
                          border: "1px solid #1a5fb4",
                          borderRadius: 8,
                          cursor: "pointer",
                        }}
                      >
                        {completing === item.evaluation_id
                          ? t("teacher.queue.completing")
                          : t("teacher.queue.complete")}
                      </button>
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
