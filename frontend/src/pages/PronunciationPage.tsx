import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  ApiError,
  assessPronunciation,
  getPronunciationItems,
  getWeakWords,
  type Assessment,
  type PronunciationItem,
  type User,
  type WeakWordAgg,
  type WordScore,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import { t } from "../i18n";

// Azure REST short audio は30秒上限。余裕を持って自動停止する。
const MAX_RECORD_SEC = 28;

// バックエンド WEAK_WORD_THRESHOLD=70 と同じ閾値で色分けする。
const WEAK_THRESHOLD = 70;
const GOOD_THRESHOLD = 85;

const palette = {
  good: { bg: "#d7efdb", fg: "#1b5e20" },
  ok: { bg: "#fdf0c5", fg: "#7a5900" },
  weak: { bg: "#fbd9d9", fg: "#8a0f1c" },
};

function wordColor(w: WordScore): { bg: string; fg: string } {
  if (w.error_type !== "None" || w.accuracy < WEAK_THRESHOLD) return palette.weak;
  if (w.accuracy < GOOD_THRESHOLD) return palette.ok;
  return palette.good;
}

const cardStyle: React.CSSProperties = {
  border: "1px solid #ddd",
  borderRadius: 12,
  padding: 16,
  marginBottom: 16,
  background: "#fff",
};

const badgeStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "2px 8px",
  borderRadius: 999,
  background: "#eef1f6",
  color: "#333",
};

type Phase = "idle" | "recording" | "assessing";

export default function PronunciationPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [items, setItems] = useState<PronunciationItem[] | null>(null);
  const [index, setIndex] = useState(0);
  const [weakWords, setWeakWords] = useState<WeakWordAgg[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<Assessment | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    getPronunciationItems()
      .then(setItems)
      .catch(() => setError(t("common.error")));
    getWeakWords()
      .then(setWeakWords)
      .catch(() => {
        // 弱点語はページの主目的ではないため、取得失敗は黙って空のままにする。
      });
    return () => {
      stopTimer();
      const rec = recorderRef.current;
      if (rec !== null && rec.state !== "inactive") rec.stop();
      recorderRef.current = null;
    };
  }, []);

  function stopTimer() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function changeItem(delta: number) {
    if (items === null || items.length === 0) return;
    setIndex((i) => (i + delta + items.length) % items.length);
    setResult(null);
    setError(null);
  }

  async function startRecording() {
    setError(null);
    setResult(null);
    if (typeof MediaRecorder === "undefined") {
      setError(t("pron.error.mic"));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Android Chrome は audio/webm;codecs=opus。Safari 系は audio/mp4 に落ちる
      // （サーバの ffmpeg がコンテナを自動判定するのでどちらでも良い）。
      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((m) =>
        MediaRecorder.isTypeSupported(m),
      );
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        void assess(blob);
      };
      recorderRef.current = recorder;
      recorder.start();
      setElapsed(0);
      setPhase("recording");
      const startedAt = Date.now();
      timerRef.current = window.setInterval(() => {
        const sec = Math.floor((Date.now() - startedAt) / 1000);
        setElapsed(sec);
        if (sec >= MAX_RECORD_SEC) stopRecording();
      }, 250);
    } catch {
      setError(t("pron.error.mic"));
    }
  }

  function stopRecording() {
    stopTimer();
    const rec = recorderRef.current;
    if (rec !== null && rec.state !== "inactive") rec.stop();
    recorderRef.current = null;
  }

  async function assess(blob: Blob) {
    if (items === null || items.length === 0) return;
    setPhase("assessing");
    try {
      const assessment = await assessPronunciation(items[index].id, blob);
      setResult(assessment);
      // 弱点語リストの自動更新。失敗しても結果表示は維持する。
      getWeakWords()
        .then(setWeakWords)
        .catch(() => undefined);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.message.startsWith("no_speech")) {
        setError(t("pron.error.noSpeech"));
      } else {
        setError(t("pron.error.assess"));
      }
    } finally {
      setPhase("idle");
    }
  }

  const item = items !== null && items.length > 0 ? items[index] : null;

  return (
    <main
      style={{
        maxWidth: 480,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("pron.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0 }}>
        <Link to="/student">{t("pron.back")}</Link>
      </p>

      {items === null ? (
        <p>{t("common.loading")}</p>
      ) : item === null ? (
        <p>{t("pron.empty")}</p>
      ) : (
        <>
          <section style={cardStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 8,
              }}
            >
              <button
                onClick={() => changeItem(-1)}
                disabled={phase !== "idle"}
                aria-label={t("pron.prev")}
                style={{ padding: "6px 14px" }}
              >
                ←
              </button>
              <span style={{ fontSize: 13, color: "#666" }}>
                {t("pron.counter", { current: index + 1, total: items.length })}
              </span>
              <button
                onClick={() => changeItem(1)}
                disabled={phase !== "idle"}
                aria-label={t("pron.next")}
                style={{ padding: "6px 14px" }}
              >
                →
              </button>
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <span style={badgeStyle}>{t(`pron.sector.${item.sector}`)}</span>
              <span style={badgeStyle}>{item.level}</span>
            </div>
            <p lang="ja" style={{ fontSize: 24, lineHeight: 1.5, margin: "0 0 4px" }}>
              {item.text_ja}
            </p>
            {item.furigana !== null && (
              <p lang="ja" style={{ fontSize: 14, color: "#666", margin: "0 0 8px" }}>
                {item.furigana}
              </p>
            )}
            {item.gloss_id !== null && (
              <p style={{ fontSize: 14, color: "#444", fontStyle: "italic", margin: 0 }}>
                {item.gloss_id}
              </p>
            )}
          </section>

          <section style={{ textAlign: "center", marginBottom: 16 }}>
            {phase === "recording" ? (
              <button
                onClick={stopRecording}
                style={{
                  width: "100%",
                  padding: 16,
                  fontSize: 18,
                  background: "#b00020",
                  color: "#fff",
                  border: "none",
                  borderRadius: 12,
                }}
              >
                {t("pron.record.stop")}
              </button>
            ) : (
              <button
                onClick={() => void startRecording()}
                disabled={phase === "assessing"}
                style={{
                  width: "100%",
                  padding: 16,
                  fontSize: 18,
                  background: phase === "assessing" ? "#9aa5b1" : "#1a5fb4",
                  color: "#fff",
                  border: "none",
                  borderRadius: 12,
                }}
              >
                {phase === "assessing" ? t("pron.record.assessing") : t("pron.record.start")}
              </button>
            )}
            {phase === "recording" && (
              <p style={{ color: "#b00020", marginBottom: 0 }}>
                {t("pron.record.recording", { sec: elapsed })}
              </p>
            )}
            {error !== null && (
              <p role="alert" style={{ color: "#b00020", marginBottom: 0 }}>
                {error}
              </p>
            )}
          </section>

          {result !== null && (
            <section style={cardStyle}>
              <div style={{ textAlign: "center", marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: "#666" }}>{t("pron.result.overall")}</div>
                <div style={{ fontSize: 44, fontWeight: 700 }}>{result.pron}</div>
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-around",
                  marginBottom: 16,
                  textAlign: "center",
                }}
              >
                {(
                  [
                    ["pron.result.accuracy", result.accuracy],
                    ["pron.result.fluency", result.fluency],
                    ["pron.result.completeness", result.completeness],
                  ] as const
                ).map(([key, value]) => (
                  <div key={key}>
                    <div style={{ fontSize: 12, color: "#666" }}>{t(key)}</div>
                    <div style={{ fontSize: 22, fontWeight: 600 }}>{value}</div>
                  </div>
                ))}
              </div>

              <div style={{ fontSize: 13, color: "#666", marginBottom: 6 }}>
                {t("pron.result.words")}
              </div>
              <div lang="ja" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                {result.words.map((w, i) => {
                  const color = wordColor(w);
                  return (
                    <span
                      key={`${w.word}-${i}`}
                      title={String(w.accuracy)}
                      style={{
                        padding: "4px 8px",
                        borderRadius: 8,
                        fontSize: 18,
                        background: color.bg,
                        color: color.fg,
                      }}
                    >
                      {w.word}
                      <small style={{ marginLeft: 4, fontSize: 11 }}>{w.accuracy}</small>
                    </span>
                  );
                })}
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: 12, marginBottom: 12 }}>
                {(
                  [
                    ["pron.legend.good", palette.good],
                    ["pron.legend.ok", palette.ok],
                    ["pron.legend.weak", palette.weak],
                  ] as const
                ).map(([key, color]) => (
                  <span key={key} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <span
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: 3,
                        background: color.bg,
                        border: `1px solid ${color.fg}`,
                        display: "inline-block",
                      }}
                    />
                    {t(key)}
                  </span>
                ))}
              </div>

              {result.recognized_text !== "" && (
                <p style={{ fontSize: 13, color: "#666", margin: 0 }}>
                  {t("pron.result.recognized")}:{" "}
                  <span lang="ja" style={{ color: "#333" }}>
                    {result.recognized_text}
                  </span>
                </p>
              )}
            </section>
          )}

          <section style={cardStyle}>
            <h2 style={{ fontSize: 16, marginTop: 0 }}>{t("pron.weak.title")}</h2>
            {weakWords.length === 0 ? (
              <p style={{ color: "#666", margin: 0 }}>{t("pron.weak.empty")}</p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {weakWords.map((w) => (
                  <li
                    key={w.word}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "6px 0",
                      borderBottom: "1px solid #eee",
                    }}
                  >
                    <span lang="ja" style={{ fontSize: 17 }}>
                      {w.word}
                    </span>
                    <span style={{ color: "#666", fontSize: 14 }}>
                      <strong style={{ color: palette.weak.fg, marginRight: 8 }}>
                        {w.accuracy}
                      </strong>
                      {t("pron.weak.count", { n: w.count })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
