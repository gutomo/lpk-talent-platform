import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  createConversationSession,
  getScenarios,
  sendConversationReply,
  type ConversationSession,
  type ConversationTurn,
  type Scenario,
  type User,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import { t } from "../i18n";

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

function TurnBubble({ turn }: { turn: ConversationTurn }) {
  const isStudent = turn.role === "student";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isStudent ? "flex-end" : "flex-start",
        marginBottom: 8,
      }}
    >
      <div
        style={{
          maxWidth: "85%",
          padding: "10px 12px",
          borderRadius: 12,
          background: isStudent ? "#dbe9fb" : "#fff",
          border: isStudent ? "1px solid #b9d2f0" : "1px solid #ddd",
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

export default function ConversationPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [session, setSession] = useState<ConversationSession | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [done, setDone] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getScenarios()
      .then(setScenarios)
      .catch(() => setError(t("common.error")));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns]);

  const scenario =
    session !== null && scenarios !== null
      ? (scenarios.find((s) => s.key === session.scenario) ?? null)
      : null;
  const studentTurnCount = turns.filter((turn) => turn.role === "student").length;
  const lastHint = [...turns].reverse().find((turn) => turn.role === "partner")?.hint_id ?? null;

  async function start(key: string) {
    setError(null);
    setSending(true);
    try {
      const created = await createConversationSession(key);
      setSession(created);
      setTurns(created.turns);
      setDone(created.done);
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
      const reply = await sendConversationReply(session.session_id, text);
      setTurns((prev) => [...prev, reply.student_turn, reply.partner_turn]);
      setDone(reply.done);
      setDraft("");
    } catch {
      setError(t("conv.error.send"));
    } finally {
      setSending(false);
    }
  }

  function reset() {
    setSession(null);
    setTurns([]);
    setDone(false);
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
      <PageHeader title={t("conv.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0 }}>
        {session === null ? (
          <Link to="/student">{t("conv.back")}</Link>
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
            {t("conv.backToScenarios")}
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
            <p style={{ fontSize: 14, color: "#555" }}>{t("conv.choose")}</p>
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
              {t("conv.progress", {
                current: Math.min(studentTurnCount, session.max_student_turns),
                total: session.max_student_turns,
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
            <section style={{ ...cardStyle, textAlign: "center" }}>
              <p style={{ fontSize: 17, fontWeight: 600, margin: "0 0 12px" }}>
                {t("conv.done")}
              </p>
              <button
                onClick={reset}
                style={{
                  width: "100%",
                  padding: 12,
                  fontSize: 16,
                  background: "#1a5fb4",
                  color: "#fff",
                  border: "none",
                  borderRadius: 12,
                }}
              >
                {t("conv.again")}
              </button>
            </section>
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
                  placeholder={t("conv.placeholder")}
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
                  {sending ? t("conv.sending") : t("conv.send")}
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
