import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  createInterviewSession,
  getInterviewScenarios,
  sendInterviewReply,
  type InterviewEvaluation,
  type InterviewScenario,
  type InterviewSession,
  type InterviewTurn,
  type User,
} from "../api/client";
import PageHeader from "../components/PageHeader";
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

const badgeStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "2px 8px",
  borderRadius: 999,
  background: "#eef1f6",
  color: "#333",
};

function scoreColor(score: number): string {
  if (score >= 80) return "#2e7d32";
  if (score >= 60) return "#f9a825";
  return "#c62828";
}

function TurnBubble({ turn }: { turn: InterviewTurn }) {
  const isCandidate = turn.role === "candidate";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isCandidate ? "flex-end" : "flex-start",
        marginBottom: 8,
      }}
    >
      <div
        style={{
          maxWidth: "85%",
          padding: "10px 12px",
          borderRadius: 12,
          background: isCandidate ? "#dbe9fb" : "#fff",
          border: isCandidate ? "1px solid #b9d2f0" : "1px solid #ddd",
        }}
      >
        <p lang="ja" style={{ margin: 0, fontSize: 17, lineHeight: 1.5 }}>
          {turn.text_ja}
        </p>
        {turn.furigana !== null && turn.furigana !== "" && (
          <p lang="ja" style={{ margin: "4px 0 0", fontSize: 12, color: "#666" }}>
            {turn.furigana}
          </p>
        )}
      </div>
    </div>
  );
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
            height: 8,
            borderRadius: 4,
            background: scoreColor(score),
          }}
        />
      </div>
    </div>
  );
}

function EvaluationCard({
  evaluation,
  onReset,
}: {
  evaluation: InterviewEvaluation;
  onReset: () => void;
}) {
  return (
    <section style={cardStyle}>
      <p style={{ fontSize: 17, fontWeight: 600, margin: "0 0 12px", textAlign: "center" }}>
        {t("itv.result.title")}
      </p>
      <div style={{ textAlign: "center", marginBottom: 16 }}>
        <div style={{ fontSize: 40, fontWeight: 700, color: scoreColor(evaluation.total) }}>
          {evaluation.total}
        </div>
        <div style={{ fontSize: 13, color: "#666" }}>{t("itv.result.total")}</div>
      </div>
      {AXES.map((axis) =>
        axis in evaluation.scores ? (
          <AxisBar key={axis} axis={axis} score={evaluation.scores[axis]} />
        ) : null,
      )}
      {evaluation.summary_id !== null && (
        <p style={{ fontSize: 14, margin: "12px 0 0" }}>{evaluation.summary_id}</p>
      )}
      {evaluation.advice_id !== null && (
        <p style={{ fontSize: 14, margin: "8px 0 0" }}>💡 {evaluation.advice_id}</p>
      )}
      {evaluation.model_answers.length > 0 && (
        <>
          <p style={{ fontSize: 14, fontWeight: 600, margin: "16px 0 8px" }}>
            {t("itv.result.modelAnswers")}
          </p>
          {evaluation.model_answers.map((m) => (
            <div
              key={m.question_ja}
              style={{
                background: "#f4f6f9",
                borderRadius: 8,
                padding: "8px 10px",
                marginBottom: 8,
              }}
            >
              <p lang="ja" style={{ margin: 0, fontSize: 12, color: "#666" }}>
                {m.question_ja}
              </p>
              <p lang="ja" style={{ margin: "4px 0 0", fontSize: 15 }}>
                {m.answer_ja}
              </p>
            </div>
          ))}
        </>
      )}
      <button
        onClick={onReset}
        style={{
          width: "100%",
          padding: 12,
          marginTop: 8,
          fontSize: 16,
          background: "#1a5fb4",
          color: "#fff",
          border: "none",
          borderRadius: 12,
        }}
      >
        {t("itv.again")}
      </button>
    </section>
  );
}

export default function InterviewPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [scenarios, setScenarios] = useState<InterviewScenario[] | null>(null);
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [turns, setTurns] = useState<InterviewTurn[]>([]);
  const [evaluation, setEvaluation] = useState<InterviewEvaluation | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getInterviewScenarios()
      .then(setScenarios)
      .catch(() => setError(t("common.error")));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, evaluation]);

  const scenario =
    session !== null && scenarios !== null
      ? (scenarios.find((s) => s.key === session.scenario) ?? null)
      : null;
  const candidateTurnCount = turns.filter((turn) => turn.role === "candidate").length;
  const lastHint =
    [...turns].reverse().find((turn) => turn.role === "interviewer")?.hint_id ?? null;
  const done = evaluation !== null;

  async function start(key: string) {
    setError(null);
    setSending(true);
    try {
      const created = await createInterviewSession(key);
      setSession(created);
      setTurns(created.turns);
      setEvaluation(created.evaluation);
      setDraft("");
    } catch {
      setError(t("common.error"));
    } finally {
      setSending(false);
    }
  }

  async function send() {
    const text = draft.trim();
    if (session === null || text === "" || sending || done) return;
    setError(null);
    setSending(true);
    try {
      const reply = await sendInterviewReply(session.session_id, text);
      setTurns((prev) => [...prev, reply.candidate_turn, reply.interviewer_turn]);
      setEvaluation(reply.evaluation);
      setDraft("");
    } catch {
      setError(t("itv.error.send"));
    } finally {
      setSending(false);
    }
  }

  function reset() {
    setSession(null);
    setTurns([]);
    setEvaluation(null);
    setDraft("");
    setError(null);
  }

  return (
    <main
      style={{
        maxWidth: 480,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("itv.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0 }}>
        {session === null ? (
          <Link to="/student">{t("itv.back")}</Link>
        ) : (
          <button
            onClick={reset}
            style={{
              padding: 0,
              border: "none",
              background: "none",
              color: "#1a5fb4",
              textDecoration: "underline",
              fontSize: "inherit",
              cursor: "pointer",
            }}
          >
            {t("itv.backToScenarios")}
          </button>
        )}
      </p>

      {session === null ? (
        scenarios === null ? (
          error !== null ? (
            <p role="alert" style={{ color: "#b00020" }}>
              {error}
            </p>
          ) : (
            <p>{t("common.loading")}</p>
          )
        ) : (
          <nav>
            <p style={{ fontSize: 14, color: "#555" }}>{t("itv.choose")}</p>
            {scenarios.map((s) => (
              <button
                key={s.key}
                onClick={() => void start(s.key)}
                disabled={sending}
                style={{ ...cardStyle, display: "block", width: "100%", textAlign: "left" }}
              >
                <div
                  style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}
                >
                  <span style={{ fontSize: 17, fontWeight: 600 }}>{s.title_id}</span>
                  <span style={badgeStyle}>{s.level}</span>
                </div>
                <div lang="ja" style={{ fontSize: 13, color: "#666", marginBottom: 4 }}>
                  {s.title_ja}
                </div>
                <div style={{ fontSize: 14, color: "#555" }}>{s.description_id}</div>
              </button>
            ))}
          </nav>
        )
      ) : (
        <>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 14, fontWeight: 600 }}>
              {scenario?.title_id ?? session.scenario}
            </span>
            <span style={{ fontSize: 13, color: "#666" }}>
              {t("itv.progress", {
                current: Math.min(candidateTurnCount, session.max_candidate_turns),
                total: session.max_candidate_turns,
              })}
            </span>
          </div>

          <section
            style={{
              background: "#f4f6f9",
              borderRadius: 12,
              padding: 12,
              marginBottom: 12,
              minHeight: 200,
            }}
          >
            {turns.map((turn) => (
              <TurnBubble key={turn.seq} turn={turn} />
            ))}
            <div ref={bottomRef} />
          </section>

          {done ? (
            <EvaluationCard evaluation={evaluation} onReset={reset} />
          ) : (
            <section>
              {lastHint !== null && (
                <p style={{ fontSize: 13, color: "#555", margin: "0 0 8px" }}>
                  💡 {lastHint}
                </p>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void send();
                  }}
                  placeholder={t("itv.placeholder")}
                  lang="ja"
                  enterKeyHint="send"
                  disabled={sending}
                  style={{
                    flex: 1,
                    padding: "10px 12px",
                    fontSize: 16,
                    border: "1px solid #ccc",
                    borderRadius: 12,
                  }}
                />
                <button
                  onClick={() => void send()}
                  disabled={sending || draft.trim() === ""}
                  style={{
                    padding: "10px 16px",
                    fontSize: 16,
                    background: sending || draft.trim() === "" ? "#9aa5b1" : "#1a5fb4",
                    color: "#fff",
                    border: "none",
                    borderRadius: 12,
                  }}
                >
                  {sending ? t("itv.sending") : t("itv.send")}
                </button>
              </div>
            </section>
          )}
          {error !== null && (
            <p role="alert" style={{ color: "#b00020" }}>
              {error}
            </p>
          )}
        </>
      )}
    </main>
  );
}
