import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getSharedCandidatePassport,
  getSharedPassport,
  sharedCandidatePdfUrl,
  sharedPdfUrl,
  type SharedPassport,
} from "../api/client";
import TrendChart, { scoreColor } from "../components/TrendChart";
import { setLocale, t } from "../i18n";

// 企業向け共有ビュー（ログイン不要）。CLAUDE.md の方針どおり日本語のみで表示する。
// トークンはURL経路のみ。無効（不存在・失効・期限切れ）はAPIが一律404を返す。
// 2ルート共用：/share/:token（学生別リンク）と
// /company/:token/students/:studentId（組織単位リンク経由の個別閲覧・常に最新版）。

const cardStyle: React.CSSProperties = {
  border: "1px solid #ddd",
  borderRadius: 12,
  padding: 16,
  marginBottom: 12,
  background: "#fff",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  margin: "0 0 10px",
};

function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ ...cardStyle, flex: "1 1 130px", marginBottom: 0, textAlign: "center" }}>
      <div style={{ fontSize: 12, color: "#666" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: color ?? "#333" }}>{value}</div>
    </div>
  );
}

export default function SharePassportPage() {
  const params = useParams();
  const token = params.token ?? "";
  const studentId = params.studentId !== undefined ? Number(params.studentId) : null;

  const [passport, setPassport] = useState<SharedPassport | null>(null);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    // 公開ページは日本語のみ（学生ログインの locale 状態に依存しない）。
    setLocale("ja");
    if (token === "" || (studentId !== null && !Number.isInteger(studentId))) {
      setInvalid(true);
      return;
    }
    (studentId !== null
      ? getSharedCandidatePassport(token, studentId)
      : getSharedPassport(token)
    )
      .then(setPassport)
      .catch(() => setInvalid(true));
  }, [token, studentId]);

  const snap = passport?.snapshot ?? null;
  const itvTrend = snap?.interview.trend ?? [];
  const mockTrend = snap?.japanese_level.trend ?? [];

  return (
    <main
      lang="ja"
      style={{
        maxWidth: 800,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <header style={{ margin: "8px 0 16px" }}>
        <h1 style={{ margin: 0, fontSize: 22, color: "#1a5fb4" }}>
          Talent Passport <span style={{ fontSize: 15 }}>{t("share.subtitle")}</span>
        </h1>
        {studentId !== null && (
          <p style={{ margin: "8px 0 0", fontSize: 14 }}>
            <Link to={`/company/${token}`} style={{ color: "#1a5fb4" }}>
              {t("company.back")}
            </Link>
          </p>
        )}
      </header>

      {invalid && (
        <p role="alert" style={{ ...cardStyle, color: "#b00020" }}>
          {t("share.invalid")}
        </p>
      )}
      {!invalid && passport === null && <p>{t("common.loading")}</p>}

      {passport !== null && snap !== null && (
        <>
          <section style={cardStyle}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              <h2 style={{ margin: 0, fontSize: 20 }}>{snap.student.name}</h2>
              <span style={{ fontSize: 13, color: "#555" }}>
                {t("share.version", { n: passport.version })} ・{" "}
                {t("share.generatedAt", { date: formatDate(passport.created_at) })}
              </span>
            </div>
            <p style={{ margin: "6px 0 0", fontSize: 14, color: "#555" }}>
              {snap.student.cohort !== null && <>{snap.student.cohort} ・ </>}
              {snap.student.sector !== null && (
                <>
                  {t("share.sector")}: {t(`pron.sector.${snap.student.sector}`)}
                </>
              )}
            </p>
            <p style={{ margin: "10px 0 0" }}>
              <a
                href={
                  studentId !== null
                    ? sharedCandidatePdfUrl(token, studentId)
                    : sharedPdfUrl(token)
                }
                style={{
                  display: "inline-block",
                  padding: "10px 16px",
                  fontSize: 15,
                  background: "#1a5fb4",
                  color: "#fff",
                  borderRadius: 10,
                  textDecoration: "none",
                }}
              >
                {t("share.pdf")}
              </a>
            </p>
          </section>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
            <StatCard
              label={t("share.level")}
              value={snap.japanese_level.current ?? t("share.none")}
            />
            <StatCard
              label={t("share.pron")}
              value={
                snap.pronunciation.avg_accuracy !== null
                  ? String(snap.pronunciation.avg_accuracy)
                  : t("share.none")
              }
              color={
                snap.pronunciation.avg_accuracy !== null
                  ? scoreColor(snap.pronunciation.avg_accuracy)
                  : undefined
              }
            />
            <StatCard
              label={t("share.interview")}
              value={
                snap.interview.latest_total !== null
                  ? String(snap.interview.latest_total)
                  : t("share.none")
              }
              color={
                snap.interview.latest_total !== null
                  ? scoreColor(snap.interview.latest_total)
                  : undefined
              }
            />
            <StatCard
              label={t("share.attendance")}
              value={snap.attendance.rate !== null ? `${snap.attendance.rate}%` : t("share.none")}
              color={snap.attendance.rate !== null ? scoreColor(snap.attendance.rate) : undefined}
            />
          </div>

          {(mockTrend.length >= 2 || itvTrend.length >= 2) && (
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {mockTrend.length >= 2 && (
                <section style={{ ...cardStyle, flex: "1 1 260px" }}>
                  <p style={sectionTitleStyle}>{t("share.mockTrend.title")}</p>
                  <TrendChart
                    scores={mockTrend.map((p) => p.score)}
                    label={t("share.mockTrend.title")}
                  />
                </section>
              )}
              {itvTrend.length >= 2 && (
                <section style={{ ...cardStyle, flex: "1 1 260px" }}>
                  <p style={sectionTitleStyle}>{t("share.itvTrend.title")}</p>
                  <TrendChart
                    scores={itvTrend.map((p) => p.total)}
                    label={t("share.itvTrend.title")}
                  />
                </section>
              )}
            </div>
          )}

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("share.weakWords.title")}</p>
            {snap.pronunciation.weak_words.length === 0 ? (
              <p style={{ fontSize: 14, color: "#666", margin: 0 }}>
                {t("share.weakWords.empty")}
              </p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {snap.pronunciation.weak_words.map((w) => (
                  <li
                    key={w.word}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "6px 0",
                      borderBottom: "1px solid #eee",
                      fontSize: 15,
                    }}
                  >
                    <span>{w.word}</span>
                    <span style={{ color: "#666", fontSize: 13 }}>
                      {t("share.weakWords.detail", { min: w.min_accuracy, n: w.count })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p style={{ fontSize: 14, color: "#555", margin: "10px 0 0" }}>
              {t("share.conversation", { n: snap.conversation.completed })}
            </p>
          </section>

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("share.attitude.title")}</p>
            {snap.attitude === null ? (
              <p style={{ fontSize: 14, color: "#666", margin: 0 }}>
                {t("share.attitude.empty")}
              </p>
            ) : (
              <>
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {Object.entries(snap.attitude.checklist).map(([key, value]) => (
                    <li
                      key={key}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        padding: "4px 0",
                        fontSize: 15,
                      }}
                    >
                      <span>{t(`teacher.detail.attitude.item.${key}`)}</span>
                      <span style={{ fontWeight: 600, color: scoreColor(value ?? 0) }}>
                        {value}
                      </span>
                    </li>
                  ))}
                </ul>
                {snap.attitude.note !== null && (
                  <p
                    style={{
                      fontSize: 14,
                      color: "#555",
                      background: "#f7f7f7",
                      borderLeft: "3px solid #ccc",
                      padding: "6px 10px",
                      margin: "10px 0 0",
                    }}
                  >
                    {snap.attitude.note}
                  </p>
                )}
                <p style={{ fontSize: 12, color: "#888", margin: "8px 0 0" }}>
                  {t("share.attitude.reviewedAt", { date: snap.attitude.reviewed_at })}
                </p>
              </>
            )}
          </section>

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("share.checklist.title")}</p>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {snap.checklist.map((item) => (
                <li
                  key={item.key}
                  style={{ display: "flex", gap: 8, padding: "4px 0", fontSize: 15 }}
                >
                  <span style={{ color: item.done ? "#2e7d32" : "#9aa5b1" }}>
                    {item.done ? `○ ${t("share.checklist.done")}` : `― ${t("share.checklist.notDone")}`}
                  </span>
                  <span style={{ color: item.done ? "#333" : "#666" }}>{item.label_ja}</span>
                </li>
              ))}
            </ul>
          </section>

          {snap.interview.transcript_excerpt.length > 0 && (
            <section style={cardStyle}>
              <p style={sectionTitleStyle}>{t("share.transcript.title")}</p>
              {snap.interview.transcript_excerpt.map((line, i) => (
                <p
                  key={i}
                  style={{
                    fontSize: 14,
                    color: "#444",
                    background: "#f7f7f7",
                    borderLeft: "3px solid #ccc",
                    padding: "6px 10px",
                    margin: "6px 0",
                  }}
                >
                  「{line}」
                </p>
              ))}
            </section>
          )}

          <p style={{ fontSize: 12, color: "#888", margin: "16px 0 8px" }}>
            {t("share.disclaimer")}
          </p>
          <p style={{ fontSize: 12, color: "#888", margin: "0 0 24px" }}>
            {t("share.expiresAt", { date: formatDate(passport.expires_at) })}
          </p>
        </>
      )}
    </main>
  );
}
