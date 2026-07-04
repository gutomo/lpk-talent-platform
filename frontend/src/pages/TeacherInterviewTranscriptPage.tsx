import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  completeReview,
  getInterviewTranscript,
  type InterviewTranscript,
  type User,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import { scoreColor } from "../components/TrendChart";
import { t } from "../i18n";

// 表示順は rubric の定義順（backend/app/prompts/interview_v1.py）に合わせる。
const AXES = ["japanese", "consistency", "keigo", "hourensou", "clarity"] as const;

const cardStyle: React.CSSProperties = {
  border: "1px solid #ddd",
  borderRadius: 12,
  padding: 16,
  marginBottom: 12,
  background: "#fff",
};

// ISO日時の日付部分。教師画面の表示は YYYY-MM-DD で十分。
function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

function AxisBar({ axis, score }: { axis: string; score: number }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span>{t(`itv.axis.${axis}`)}</span>
        <span style={{ fontWeight: 600, color: scoreColor(score) }}>{score}</span>
      </div>
      <div style={{ height: 8, borderRadius: 4, background: "#eef1f6" }}>
        <div
          style={{
            width: `${score}%`,
            height: "100%",
            borderRadius: 4,
            background: scoreColor(score),
          }}
        />
      </div>
    </div>
  );
}

export default function TeacherInterviewTranscriptPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const params = useParams();
  const studentId = Number(params.studentId);
  const sessionId = Number(params.sessionId);

  const [transcript, setTranscript] = useState<InterviewTranscript | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [marking, setMarking] = useState(false);
  const [markError, setMarkError] = useState(false);

  useEffect(() => {
    if (!Number.isInteger(studentId) || !Number.isInteger(sessionId)) {
      setLoadError(true);
      return;
    }
    getInterviewTranscript(studentId, sessionId)
      .then(setTranscript)
      .catch(() => setLoadError(true));
  }, [studentId, sessionId]);

  function markReviewed() {
    if (transcript === null || transcript.evaluation === null || marking) return;
    setMarking(true);
    setMarkError(false);
    completeReview(transcript.evaluation.evaluation_id)
      .then((done) =>
        setTranscript((prev) =>
          prev === null || prev.evaluation === null
            ? prev
            : {
                ...prev,
                evaluation: {
                  ...prev.evaluation,
                  reviewed_at: done.reviewed_at,
                  // 自分が確認したので reviewer は操作中のユーザー。
                  reviewer_name: user.name,
                },
              },
        ),
      )
      .catch(() => setMarkError(true))
      .finally(() => setMarking(false));
  }

  const evaluation = transcript?.evaluation ?? null;

  return (
    <main
      style={{
        maxWidth: 720,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("teacher.transcript.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Link to="/teacher/review">{t("teacher.transcript.backToQueue")}</Link>
        {Number.isInteger(studentId) && (
          <Link to={`/teacher/students/${studentId}`}>
            {t("teacher.transcript.backToStudent")}
          </Link>
        )}
      </p>

      {loadError && (
        <p role="alert" style={{ color: "#b00020" }}>
          {t("common.error")}
        </p>
      )}
      {!loadError && transcript === null && <p>{t("common.loading")}</p>}

      {transcript !== null && (
        <>
          <section style={cardStyle}>
            <h2 style={{ margin: 0, fontSize: 20 }}>{transcript.student_name}</h2>
            <p style={{ margin: "6px 0 0", fontSize: 14, color: "#555" }} lang="ja">
              {transcript.title_ja ?? transcript.scenario} ・ {t(`itv.mode.${transcript.mode}`)}{" "}
              ・ {formatDate(transcript.created_at)}
            </p>
          </section>

          {evaluation !== null && (
            <section style={cardStyle}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: 8,
                  marginBottom: 10,
                }}
              >
                <p style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>
                  {t("teacher.transcript.evaluation")}
                </p>
                {evaluation.reviewed_at === null ? (
                  <button
                    onClick={markReviewed}
                    disabled={marking}
                    style={{
                      padding: "8px 14px",
                      fontSize: 14,
                      background: "#1a5fb4",
                      color: "#fff",
                      border: "none",
                      borderRadius: 10,
                      cursor: "pointer",
                    }}
                  >
                    {marking
                      ? t("teacher.transcript.marking")
                      : t("teacher.transcript.markReviewed")}
                  </button>
                ) : (
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#2e7d32" }}>
                    ✓{" "}
                    {evaluation.reviewer_name !== null
                      ? t("teacher.transcript.reviewed", {
                          name: evaluation.reviewer_name,
                          date: formatDate(evaluation.reviewed_at),
                        })
                      : t("teacher.transcript.reviewedNoName", {
                          date: formatDate(evaluation.reviewed_at),
                        })}
                  </span>
                )}
              </div>
              {markError && (
                <p role="alert" style={{ color: "#b00020", fontSize: 13, margin: "0 0 8px" }}>
                  {t("teacher.queue.error")}
                </p>
              )}
              <div style={{ textAlign: "center", marginBottom: 12 }}>
                <div
                  style={{
                    fontSize: 40,
                    fontWeight: 700,
                    color: scoreColor(evaluation.total),
                  }}
                >
                  {evaluation.total}
                </div>
                <div style={{ fontSize: 13, color: "#666" }}>
                  {t("teacher.transcript.total")}
                </div>
              </div>
              {AXES.map((axis) =>
                axis in evaluation.scores ? (
                  <AxisBar key={axis} axis={axis} score={evaluation.scores[axis]} />
                ) : null,
              )}
              {evaluation.summary_ja !== null && (
                <p style={{ fontSize: 14, margin: "12px 0 0" }} lang="ja">
                  {evaluation.summary_ja}
                </p>
              )}
              {evaluation.summary_id !== null && (
                <p style={{ fontSize: 13, color: "#666", margin: "8px 0 0" }}>
                  {evaluation.summary_id}
                </p>
              )}
              <p style={{ fontSize: 11, color: "#9aa5b1", margin: "12px 0 0" }}>
                rubric: {evaluation.rubric_version}
              </p>
            </section>
          )}

          <section style={cardStyle}>
            <p style={{ fontSize: 15, fontWeight: 600, margin: "0 0 10px" }}>
              {t("teacher.transcript.turns")}
            </p>
            {transcript.turns.map((turn) => (
              <div
                key={turn.seq}
                style={{
                  display: "flex",
                  justifyContent: turn.role === "candidate" ? "flex-end" : "flex-start",
                  marginBottom: 8,
                }}
              >
                <div
                  style={{
                    maxWidth: "85%",
                    padding: "8px 12px",
                    borderRadius: 12,
                    fontSize: 14,
                    lineHeight: 1.6,
                    background: turn.role === "candidate" ? "#e3edf9" : "#f2f4f7",
                    color: "#333",
                  }}
                  lang="ja"
                >
                  {turn.text_ja}
                </div>
              </div>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
