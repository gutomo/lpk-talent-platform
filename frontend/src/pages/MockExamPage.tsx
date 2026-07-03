import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  getMockExam,
  getMockHistory,
  getMockListeningAudio,
  submitMockExam,
  type MockExam,
  type MockHistoryItem,
  type MockResult,
  type QuizItem,
  type User,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import TrendChart from "../components/TrendChart";
import { t } from "../i18n";
import { choiceStyle, PassageBox, sectionLabel, UnofficialNote } from "./DrillPage";

type Phase = "start" | "exam" | "submitting" | "result";

export default function MockExamPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("start");
  const [history, setHistory] = useState<MockHistoryItem[] | null>(null);
  const [exam, setExam] = useState<MockExam | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<{ item_id: number; selected_index: number }[]>([]);
  const [result, setResult] = useState<MockResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    getMockHistory()
      .then(setHistory)
      .catch(() => {
        // 履歴はスタート画面の補助情報。取得失敗時は表示しないだけにする。
      });
  }, []);

  // アンマウント時に再生を確実に止める。
  useEffect(() => {
    return () => {
      stopPlayback();
      if (audioUrlRef.current !== null) URL.revokeObjectURL(audioUrlRef.current);
    };
  }, []);

  function stopPlayback() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (audioRef.current !== null) audioRef.current.pause();
  }

  // サーバ音声(Neural TTS)が無い(stub)ときのフォールバック。ブラウザ内蔵の ja-JP 音声で読み上げる。
  function browserSpeak(textJa: string) {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(textJa);
    utterance.lang = "ja-JP";
    window.speechSynthesis.speak(utterance);
  }

  // 聴解の音源を再生する。サーバ音声があればそれを、無ければ browser TTS。
  async function playListening(item: QuizItem) {
    stopPlayback();
    const fallback = item.script_ja ?? "";
    try {
      const blob = await getMockListeningAudio(item.item_id);
      if (blob !== null) {
        if (audioUrlRef.current !== null) URL.revokeObjectURL(audioUrlRef.current);
        const url = URL.createObjectURL(blob);
        audioUrlRef.current = url;
        const audio = audioRef.current ?? new Audio();
        audioRef.current = audio;
        audio.src = url;
        await audio.play().catch(() => browserSpeak(fallback));
        return;
      }
    } catch {
      // サーバ音声の取得に失敗しても読み上げは続ける。
    }
    if (fallback) browserSpeak(fallback);
  }

  async function start() {
    setError(null);
    try {
      const data = await getMockExam();
      setExam(data);
      setIndex(0);
      setAnswers([]);
      setResult(null);
      setPhase("exam");
    } catch {
      setError(t("mock.error.load"));
    }
  }

  async function choose(choiceIndex: number) {
    if (exam === null || phase !== "exam") return;
    stopPlayback();
    const item = exam.items[index];
    const nextAnswers = [...answers, { item_id: item.item_id, selected_index: choiceIndex }];
    setAnswers(nextAnswers);
    if (index + 1 < exam.items.length) {
      setIndex(index + 1);
      return;
    }
    // 最終問題に答えたらまとめて採点・保存する。
    setPhase("submitting");
    setError(null);
    try {
      const res = await submitMockExam(nextAnswers);
      setResult(res);
      setPhase("result");
      getMockHistory()
        .then(setHistory)
        .catch(() => {});
    } catch {
      setError(t("mock.error.submit"));
      setPhase("exam");
      setAnswers(nextAnswers.slice(0, -1));
    }
  }

  const item = exam !== null && phase === "exam" ? exam.items[index] : null;
  const scores = (history ?? []).map((h) => h.score);
  const wrongResults =
    result !== null && exam !== null
      ? result.results
          .map((r) => ({ r, item: exam.items.find((i) => i.item_id === r.item_id) }))
          .filter((x): x is { r: (typeof result.results)[number]; item: QuizItem } =>
            x.item !== undefined && !x.r.is_correct,
          )
      : [];

  return (
    <main
      style={{
        maxWidth: 480,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("mock.title")} user={user} onLogout={onLogout} />
      <p>
        <Link to="/student">{t("drill.back")}</Link>
      </p>
      <UnofficialNote />
      {error !== null && <p style={{ color: "#c62828" }}>{error}</p>}

      {phase === "start" && (
        <section>
          <p style={{ fontSize: 15, lineHeight: 1.6 }}>{t("mock.desc")}</p>
          {scores.length >= 2 && (
            <section style={{ margin: "12px 0" }}>
              <h2 style={{ fontSize: 15, marginBottom: 4 }}>{t("mock.trend.title")}</h2>
              <TrendChart scores={scores} label={t("mock.trend.title")} />
            </section>
          )}
          <button
            onClick={() => void start()}
            style={{
              width: "100%",
              padding: "14px 16px",
              fontSize: 17,
              fontWeight: 600,
              borderRadius: 10,
              border: "none",
              background: "#1a5fb4",
              color: "#fff",
            }}
          >
            {t("mock.start")}
          </button>
        </section>
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
              {t("mock.progress", { current: index + 1, total: exam?.items.length ?? 0 })}
            </strong>
            <span style={{ padding: "2px 8px", borderRadius: 999, background: "#eef1f6" }}>
              {sectionLabel(item.section)} ・ {item.level}
            </span>
          </div>

          {item.passage_ja !== null && <PassageBox passage={item.passage_ja} />}
          {item.section === "listening" && (
            <div style={{ marginBottom: 12 }}>
              <button
                onClick={() => void playListening(item)}
                style={{
                  padding: "10px 16px",
                  fontSize: 16,
                  borderRadius: 8,
                  border: "1px solid #1a5fb4",
                  background: "#f4f8ff",
                  color: "#1a5fb4",
                }}
              >
                🔊 {t("mock.listening.play")}
              </button>
              <p style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                {t("mock.listening.hint")}
              </p>
            </div>
          )}
          <p style={{ fontSize: 18, lineHeight: 1.7, marginBottom: 12 }}>{item.question}</p>
          {item.choices.map((choice, i) => (
            <button key={i} onClick={() => void choose(i)} style={choiceStyle("idle")}>
              {choice}
            </button>
          ))}
        </section>
      )}

      {phase === "submitting" && <p>{t("mock.submitting")}</p>}

      {phase === "result" && result !== null && (
        <section>
          <div
            style={{
              padding: 16,
              borderRadius: 12,
              background: "#f4f8ff",
              border: "1px solid #cfe0f5",
              textAlign: "center",
              marginBottom: 16,
            }}
          >
            <h2 style={{ fontSize: 18, marginBottom: 8 }}>{t("mock.result.title")}</h2>
            <p style={{ fontSize: 40, fontWeight: 700, marginBottom: 4 }}>{result.score}</p>
            <p style={{ fontSize: 14, color: "#556", marginBottom: 4 }}>
              {t("mock.result.correct", {
                correct: result.num_correct,
                total: result.num_questions,
              })}
            </p>
            {result.band !== null && (
              <p style={{ fontSize: 14, color: "#556" }}>
                {t("mock.result.band", { band: result.band })}
              </p>
            )}
          </div>

          {scores.length >= 2 && (
            <section style={{ marginBottom: 16 }}>
              <h2 style={{ fontSize: 15, marginBottom: 4 }}>{t("mock.trend.title")}</h2>
              <TrendChart scores={scores} label={t("mock.trend.title")} />
            </section>
          )}

          {wrongResults.length > 0 && (
            <section style={{ marginBottom: 16 }}>
              <h2 style={{ fontSize: 15, marginBottom: 8 }}>{t("mock.wrong.title")}</h2>
              {wrongResults.map(({ r, item: wrongItem }) => (
                <div
                  key={r.item_id}
                  style={{
                    padding: 10,
                    marginBottom: 8,
                    borderRadius: 10,
                    border: "1px solid #f0c7c7",
                    background: "#fff8f8",
                    fontSize: 14,
                  }}
                >
                  <p style={{ marginBottom: 4 }}>{wrongItem.question}</p>
                  <p style={{ color: "#2e7d32", marginBottom: 4 }}>
                    {t("drill.correctAnswer", {
                      answer: wrongItem.choices[r.correct_index],
                    })}
                  </p>
                  {r.explanation_id !== null && (
                    <p style={{ color: "#555" }}>{r.explanation_id}</p>
                  )}
                </div>
              ))}
            </section>
          )}

          <button
            onClick={() => {
              setPhase("start");
              setExam(null);
            }}
            style={{
              width: "100%",
              padding: "12px 16px",
              fontSize: 16,
              borderRadius: 10,
              border: "1px solid #1a5fb4",
              background: "#fff",
              color: "#1a5fb4",
              marginBottom: 8,
            }}
          >
            {t("mock.again")}
          </button>
          <p style={{ textAlign: "center" }}>
            <Link to="/student">{t("drill.home")}</Link>
          </p>
        </section>
      )}
    </main>
  );
}
