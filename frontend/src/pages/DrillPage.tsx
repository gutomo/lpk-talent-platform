import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";

import {
  getDailyQuiz,
  postDrillAnswer,
  type DailyQuiz,
  type QuizAnswerResult,
  type QuizSection,
  type User,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import { t } from "../i18n";

export function sectionLabel(section: QuizSection): string {
  return t(`drill.section.${section}`);
}

// 非公式・試験対策用の表記（実装ルール）。ドリルと模試の両画面で必ず出す。
export function UnofficialNote() {
  return (
    <p
      style={{
        fontSize: 12,
        color: "#666",
        background: "#f4f6f8",
        border: "1px solid #e3e8ef",
        borderRadius: 8,
        padding: "8px 10px",
      }}
    >
      {t("drill.unofficial")}
    </p>
  );
}

export function choiceStyle(state: "idle" | "correct" | "wrong" | "dimmed"): CSSProperties {
  const colors: Record<string, { border: string; background: string }> = {
    idle: { border: "#ccd4de", background: "#fff" },
    correct: { border: "#2e7d32", background: "#e8f5e9" },
    wrong: { border: "#c62828", background: "#ffebee" },
    dimmed: { border: "#e3e8ef", background: "#fafbfc" },
  };
  const { border, background } = colors[state];
  return {
    display: "block",
    width: "100%",
    textAlign: "left",
    padding: "12px 14px",
    marginBottom: 8,
    fontSize: 16,
    borderRadius: 10,
    border: `2px solid ${border}`,
    background,
    color: state === "dimmed" ? "#889" : "inherit",
  };
}

export function PassageBox({ passage }: { passage: string }) {
  return (
    <div
      style={{
        padding: 12,
        marginBottom: 12,
        fontSize: 15,
        lineHeight: 1.8,
        background: "#fffdf5",
        border: "1px solid #eadfb8",
        borderRadius: 10,
        whiteSpace: "pre-wrap",
      }}
    >
      {passage}
    </div>
  );
}

export default function DrillPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [quiz, setQuiz] = useState<DailyQuiz | null>(null);
  const [index, setIndex] = useState(0);
  const [result, setResult] = useState<QuizAnswerResult | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [correctCount, setCorrectCount] = useState(0);
  const [finished, setFinished] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDailyQuiz()
      .then(setQuiz)
      .catch(() => setError(t("drill.error.load")));
  }, []);

  async function answer(choiceIndex: number) {
    if (quiz === null || result !== null || sending) return;
    setSending(true);
    setError(null);
    try {
      const res = await postDrillAnswer(quiz.items[index].item_id, choiceIndex);
      setSelected(choiceIndex);
      setResult(res);
      if (res.is_correct) setCorrectCount((n) => n + 1);
    } catch {
      setError(t("drill.error.answer"));
    } finally {
      setSending(false);
    }
  }

  function next() {
    if (quiz === null) return;
    if (index + 1 >= quiz.items.length) {
      setFinished(true);
      return;
    }
    setIndex(index + 1);
    setResult(null);
    setSelected(null);
  }

  const item = quiz !== null && !finished ? quiz.items[index] : null;

  return (
    <main
      style={{
        maxWidth: 480,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("drill.title")} user={user} onLogout={onLogout} />
      <p>
        <Link to="/student">{t("drill.back")}</Link>
      </p>
      <UnofficialNote />

      {error !== null && <p style={{ color: "#c62828" }}>{error}</p>}
      {quiz === null && error === null && <p>{t("common.loading")}</p>}

      {quiz !== null && quiz.items.length === 0 && <p>{t("drill.empty")}</p>}

      {quiz !== null && quiz.review_count > 0 && !finished && (
        <p style={{ fontSize: 13, color: "#8a6d1a" }}>
          {t("drill.reviewInfo", { n: quiz.review_count })}
        </p>
      )}

      {item !== null && (
        <section>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 8,
              fontSize: 13,
              color: "#556",
            }}
          >
            <strong>
              {t("drill.progress", { current: index + 1, total: quiz?.items.length ?? 0 })}
            </strong>
            <span
              style={{
                padding: "2px 8px",
                borderRadius: 999,
                background: "#eef1f6",
              }}
            >
              {sectionLabel(item.section)} ・ {item.level}
            </span>
            {item.is_review && (
              <span
                style={{
                  padding: "2px 8px",
                  borderRadius: 999,
                  background: "#fff3e0",
                  color: "#8a6d1a",
                }}
              >
                {t("drill.review.badge")}
              </span>
            )}
          </div>

          {item.passage_ja !== null && <PassageBox passage={item.passage_ja} />}
          <p style={{ fontSize: 18, lineHeight: 1.7, marginBottom: 12 }}>{item.question}</p>

          {item.choices.map((choice, i) => {
            let state: "idle" | "correct" | "wrong" | "dimmed" = "idle";
            if (result !== null) {
              if (i === result.correct_index) state = "correct";
              else if (i === selected) state = "wrong";
              else state = "dimmed";
            }
            return (
              <button
                key={i}
                onClick={() => void answer(i)}
                disabled={result !== null || sending}
                style={choiceStyle(state)}
              >
                {choice}
              </button>
            );
          })}

          {result !== null && (
            <div
              style={{
                padding: 12,
                marginTop: 8,
                borderRadius: 10,
                background: result.is_correct ? "#e8f5e9" : "#ffebee",
              }}
            >
              <p style={{ fontWeight: 600, marginBottom: 4 }}>
                {result.is_correct ? t("drill.correct") : t("drill.wrong")}
              </p>
              {!result.is_correct && (
                <p style={{ fontSize: 14, marginBottom: 4 }}>
                  {t("drill.correctAnswer", { answer: item.choices[result.correct_index] })}
                </p>
              )}
              {result.explanation_id !== null && (
                <p style={{ fontSize: 14, color: "#444" }}>{result.explanation_id}</p>
              )}
              <button
                onClick={next}
                style={{
                  marginTop: 8,
                  padding: "10px 16px",
                  fontSize: 16,
                  borderRadius: 8,
                  border: "none",
                  background: "#1a5fb4",
                  color: "#fff",
                }}
              >
                {index + 1 >= (quiz?.items.length ?? 0)
                  ? t("drill.seeResult")
                  : t("drill.next")}
              </button>
            </div>
          )}
        </section>
      )}

      {finished && quiz !== null && (
        <section
          style={{
            padding: 16,
            borderRadius: 12,
            background: "#f4f8ff",
            border: "1px solid #cfe0f5",
            textAlign: "center",
          }}
        >
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>{t("drill.result.title")}</h2>
          <p style={{ fontSize: 32, fontWeight: 700, marginBottom: 8 }}>
            {correctCount} / {quiz.items.length}
          </p>
          <p style={{ fontSize: 14, color: "#556", marginBottom: 12 }}>
            {t("drill.result.note")}
          </p>
          <Link to="/student">{t("drill.home")}</Link>
        </section>
      )}
    </main>
  );
}
