import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ATTITUDE_KEYS,
  generatePassport,
  getStudentDetail,
  postAttendance,
  postAttitude,
  type AttendanceKind,
  type AttitudeChecklist,
  type StudentDetail,
  type User,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import TrendChart, { scoreColor } from "../components/TrendChart";
import { t } from "../i18n";

// 保存操作の対象セクション。saving / notice / error を1系統で管理する。
type Section = "attendance" | "attitude" | "passport";

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

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 13,
  color: "#555",
  marginBottom: 4,
};

const inputStyle: React.CSSProperties = {
  padding: "8px 10px",
  fontSize: 15,
  border: "1px solid #ccc",
  borderRadius: 8,
  width: "100%",
  boxSizing: "border-box",
};

const buttonStyle: React.CSSProperties = {
  padding: "10px 16px",
  fontSize: 15,
  background: "#1a5fb4",
  color: "#fff",
  border: "none",
  borderRadius: 10,
  cursor: "pointer",
};

// ISO日時の日付部分。教師画面の表示は YYYY-MM-DD で十分。
function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

// ローカル暦日を返す。toISOString() は UTC 日付なので、WIB/JST の朝に前日を
// 既定表示してしまい、upsert が前日の記録を黙って上書きする事故につながる。
function today(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

// 未評価の学生はスライダーを中立値から始める（合格しきい値70に寄せない）。
const ATTITUDE_DEFAULT = 50;

function initialChecklist(detail: StudentDetail): AttitudeChecklist {
  const saved = detail.summary.attitude?.checklist ?? {};
  return Object.fromEntries(
    ATTITUDE_KEYS.map((key) => [key, saved[key] ?? ATTITUDE_DEFAULT]),
  ) as AttitudeChecklist;
}

function SummaryCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ ...cardStyle, flex: "1 1 130px", marginBottom: 0, textAlign: "center" }}>
      <div style={{ fontSize: 12, color: "#666" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: color ?? "#333" }}>{value}</div>
    </div>
  );
}

export default function TeacherStudentDetailPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const params = useParams();
  const studentId = Number(params.studentId);

  const [detail, setDetail] = useState<StudentDetail | null>(null);
  const [loadError, setLoadError] = useState(false);

  // 出席フォーム。
  const [attKind, setAttKind] = useState<AttendanceKind>("monthly");
  const [attDate, setAttDate] = useState(today());
  const [attValue, setAttValue] = useState("100");
  const [attPresent, setAttPresent] = useState(true);
  const [attNote, setAttNote] = useState("");

  // 態度フォーム。最新レビューがあればロード時に prefill する。
  const [checklist, setChecklist] = useState<AttitudeChecklist | null>(null);
  const [attitudeNote, setAttitudeNote] = useState("");

  const [saving, setSaving] = useState<Section | null>(null);
  const [notice, setNotice] = useState<Section | null>(null);
  const [saveError, setSaveError] = useState<Section | null>(null);

  useEffect(() => {
    if (!Number.isInteger(studentId)) {
      setLoadError(true);
      return;
    }
    getStudentDetail(studentId)
      .then((d) => {
        setDetail(d);
        setChecklist(initialChecklist(d));
      })
      .catch(() => setLoadError(true));
  }, [studentId]);

  function beginSave(section: Section) {
    setSaving(section);
    setNotice(null);
    setSaveError(null);
  }

  // 月次のとき値が 0〜100 の整数か。空文字は Number('') === 0 になるため必ず先に弾く。
  // 無効な間は保存ボタンを無効化するので、黙って 0% を保存する事故も無反応も起きない。
  const attValueValid =
    attKind === "daily" ||
    (attValue.trim() !== "" &&
      Number.isInteger(Number(attValue)) &&
      Number(attValue) >= 0 &&
      Number(attValue) <= 100);

  function saveAttendance() {
    if (detail === null || saving !== null || !attValueValid) return;
    const value = attKind === "daily" ? (attPresent ? 100 : 0) : Number(attValue);
    beginSave("attendance");
    postAttendance(detail.id, {
      kind: attKind,
      record_date: attDate,
      value,
      note: attNote.trim() === "" ? null : attNote.trim(),
    })
      .then((d) => {
        setDetail(d);
        setAttNote("");
        setNotice("attendance");
      })
      .catch(() => setSaveError("attendance"))
      .finally(() => setSaving(null));
  }

  function saveAttitude() {
    if (detail === null || checklist === null || saving !== null) return;
    beginSave("attitude");
    postAttitude(detail.id, checklist, attitudeNote.trim() === "" ? null : attitudeNote.trim())
      .then((d) => {
        setDetail(d);
        setAttitudeNote("");
        setNotice("attitude");
      })
      .catch(() => setSaveError("attitude"))
      .finally(() => setSaving(null));
  }

  function generate() {
    if (detail === null || saving !== null) return;
    beginSave("passport");
    generatePassport(detail.id)
      .then((p) => {
        setDetail((prev) =>
          prev === null
            ? prev
            : { ...prev, latest_passport: { version: p.version, created_at: p.created_at } },
        );
        setNotice("passport");
      })
      .catch(() => setSaveError("passport"))
      .finally(() => setSaving(null));
  }

  function sectionStatus(section: Section) {
    if (saveError === section) {
      return (
        <p role="alert" style={{ color: "#b00020", fontSize: 13, margin: "8px 0 0" }}>
          {t("teacher.detail.error.save")}
        </p>
      );
    }
    if (notice === section) {
      return (
        <p style={{ color: "#2e7d32", fontSize: 13, margin: "8px 0 0" }}>
          {t("teacher.detail.saved")}
        </p>
      );
    }
    return null;
  }

  const summary = detail?.summary ?? null;
  const itvTrend = summary?.interview.trend ?? [];

  return (
    <main
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("teacher.detail.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0 }}>
        <Link to="/teacher/students">{t("teacher.detail.back")}</Link>
      </p>

      {loadError && (
        <p role="alert" style={{ color: "#b00020" }}>
          {t("common.error")}
        </p>
      )}
      {!loadError && detail === null && <p>{t("common.loading")}</p>}

      {detail !== null && summary !== null && (
        <>
          <section style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0, fontSize: 20 }}>{detail.name}</h2>
              {summary.risk.level === "risk" && (
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    padding: "2px 10px",
                    borderRadius: 999,
                    background: "#fdecea",
                    color: "#c62828",
                  }}
                >
                  ⚠ {t("teacher.detail.riskBadge")}
                </span>
              )}
            </div>
            <p style={{ margin: "6px 0 0", fontSize: 14, color: "#555" }}>
              {detail.email}
              {detail.cohort_name !== null && <> ・ {detail.cohort_name}</>}
              {detail.sector !== null && <> ・ {t(`pron.sector.${detail.sector}`)}</>}
            </p>
            {summary.risk.flags.length > 0 && (
              <ul style={{ margin: "8px 0 0", paddingLeft: 20, color: "#c62828", fontSize: 13 }}>
                {summary.risk.flags.map((flag) => (
                  <li key={flag}>{t(`teacher.detail.risk.${flag}`)}</li>
                ))}
              </ul>
            )}
          </section>

          <p style={sectionTitleStyle}>{t("teacher.detail.summary.title")}</p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
            <SummaryCard
              label={t("teacher.detail.summary.level")}
              value={summary.japanese_level.current ?? t("teacher.detail.summary.none")}
            />
            <SummaryCard
              label={t("teacher.detail.summary.pron")}
              value={
                summary.pronunciation.avg_accuracy !== null
                  ? String(summary.pronunciation.avg_accuracy)
                  : t("teacher.detail.summary.none")
              }
              color={
                summary.pronunciation.avg_accuracy !== null
                  ? scoreColor(summary.pronunciation.avg_accuracy)
                  : undefined
              }
            />
            <SummaryCard
              label={t("teacher.detail.summary.interview")}
              value={
                summary.interview.latest_total !== null
                  ? String(summary.interview.latest_total)
                  : t("teacher.detail.summary.none")
              }
              color={
                summary.interview.latest_total !== null
                  ? scoreColor(summary.interview.latest_total)
                  : undefined
              }
            />
            <SummaryCard
              label={t("teacher.detail.summary.attendance")}
              value={
                summary.attendance.rate !== null
                  ? `${summary.attendance.rate}%`
                  : t("teacher.detail.summary.none")
              }
              color={
                summary.attendance.rate !== null
                  ? scoreColor(summary.attendance.rate)
                  : undefined
              }
            />
          </div>

          {itvTrend.length >= 2 && (
            <section style={cardStyle}>
              <p style={{ ...sectionTitleStyle, marginBottom: 4 }}>
                {t("teacher.detail.itvTrend.title")}
              </p>
              <TrendChart
                scores={itvTrend.map((p) => p.total)}
                label={t("teacher.detail.itvTrend.title")}
              />
            </section>
          )}

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("teacher.detail.weakWords.title")}</p>
            {summary.pronunciation.weak_words.length === 0 ? (
              <p style={{ fontSize: 14, color: "#666", margin: 0 }}>
                {t("teacher.detail.weakWords.empty")}
              </p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {summary.pronunciation.weak_words.map((w) => (
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
                    <span lang="ja">{w.word}</span>
                    <span style={{ color: "#666", fontSize: 13 }}>
                      {t("teacher.detail.weakWords.count", { n: w.count })} ・{" "}
                      <span style={{ color: scoreColor(w.min_accuracy), fontWeight: 600 }}>
                        {w.min_accuracy}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("teacher.detail.checklist.title")}</p>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {summary.checklist.map((item) => (
                <li
                  key={item.key}
                  style={{ display: "flex", gap: 8, padding: "4px 0", fontSize: 15 }}
                >
                  <span style={{ color: item.done ? "#2e7d32" : "#9aa5b1" }}>
                    {item.done ? "✓" : "・"}
                  </span>
                  <span lang="ja" style={{ color: item.done ? "#333" : "#666" }}>
                    {item.label_ja}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("teacher.detail.attendance.title")}</p>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 120px" }}>
                <label style={labelStyle} htmlFor="att-kind">
                  {t("teacher.detail.attendance.kind")}
                </label>
                <select
                  id="att-kind"
                  value={attKind}
                  onChange={(e) => setAttKind(e.target.value as AttendanceKind)}
                  style={inputStyle}
                >
                  <option value="monthly">{t("teacher.detail.attendance.kind.monthly")}</option>
                  <option value="daily">{t("teacher.detail.attendance.kind.daily")}</option>
                </select>
              </div>
              <div style={{ flex: "1 1 140px" }}>
                <label style={labelStyle} htmlFor="att-date">
                  {t("teacher.detail.attendance.date")}
                </label>
                <input
                  id="att-date"
                  type="date"
                  value={attDate}
                  onChange={(e) => setAttDate(e.target.value)}
                  style={inputStyle}
                />
              </div>
              <div style={{ flex: "1 1 140px" }}>
                {attKind === "monthly" ? (
                  <>
                    <label style={labelStyle} htmlFor="att-value">
                      {t("teacher.detail.attendance.value")}
                    </label>
                    <input
                      id="att-value"
                      type="number"
                      min={0}
                      max={100}
                      value={attValue}
                      onChange={(e) => setAttValue(e.target.value)}
                      style={inputStyle}
                    />
                  </>
                ) : (
                  <>
                    <span style={labelStyle}>{t("teacher.detail.attendance.value")}</span>
                    <div style={{ display: "flex", gap: 12, paddingTop: 6 }}>
                      {[true, false].map((present) => (
                        <label key={String(present)} style={{ fontSize: 15 }}>
                          <input
                            type="radio"
                            name="att-present"
                            checked={attPresent === present}
                            onChange={() => setAttPresent(present)}
                          />{" "}
                          {present
                            ? t("teacher.detail.attendance.present")
                            : t("teacher.detail.attendance.absent")}
                        </label>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
            <div style={{ marginTop: 10 }}>
              <label style={labelStyle} htmlFor="att-note">
                {t("teacher.detail.attendance.note")}
              </label>
              <input
                id="att-note"
                value={attNote}
                onChange={(e) => setAttNote(e.target.value)}
                maxLength={255}
                style={inputStyle}
              />
            </div>
            <button
              onClick={saveAttendance}
              disabled={saving !== null || attDate === "" || !attValueValid}
              style={{ ...buttonStyle, marginTop: 12 }}
            >
              {saving === "attendance"
                ? t("teacher.detail.saving")
                : t("teacher.detail.attendance.save")}
            </button>
            {sectionStatus("attendance")}

            <p style={{ ...sectionTitleStyle, margin: "16px 0 6px" }}>
              {t("teacher.detail.attendance.records")}
            </p>
            {detail.attendance_records.length === 0 ? (
              <p style={{ fontSize: 14, color: "#666", margin: 0 }}>
                {t("teacher.detail.attendance.empty")}
              </p>
            ) : (
              <div style={{ maxHeight: 220, overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                  <tbody>
                    {detail.attendance_records.map((r) => (
                      <tr key={r.id}>
                        <td style={{ padding: "4px 8px 4px 0", whiteSpace: "nowrap" }}>
                          {r.record_date}
                        </td>
                        <td style={{ padding: "4px 8px", color: "#666" }}>
                          {t(`teacher.detail.attendance.kind.${r.kind}`)}
                        </td>
                        <td
                          style={{
                            padding: "4px 8px",
                            fontWeight: 600,
                            color: scoreColor(r.value),
                          }}
                        >
                          {r.value}
                        </td>
                        <td style={{ padding: "4px 0 4px 8px", color: "#666" }}>
                          {r.note ?? ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("teacher.detail.attitude.title")}</p>
            {summary.attitude !== null && (
              <p style={{ fontSize: 13, color: "#666", margin: "0 0 10px" }}>
                {t("teacher.detail.attitude.reviewedAt", {
                  date: summary.attitude.reviewed_at,
                })}
              </p>
            )}
            {checklist !== null &&
              ATTITUDE_KEYS.map((key) => (
                <div key={key} style={{ marginBottom: 10 }}>
                  <div
                    style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}
                  >
                    <label htmlFor={`attitude-${key}`}>
                      {t(`teacher.detail.attitude.item.${key}`)}
                    </label>
                    <span style={{ fontWeight: 600, color: scoreColor(checklist[key]) }}>
                      {checklist[key]}
                    </span>
                  </div>
                  <input
                    id={`attitude-${key}`}
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={checklist[key]}
                    onChange={(e) =>
                      setChecklist((prev) =>
                        prev === null ? prev : { ...prev, [key]: Number(e.target.value) },
                      )
                    }
                    style={{ width: "100%" }}
                  />
                </div>
              ))}
            <div style={{ marginTop: 4 }}>
              <label style={labelStyle} htmlFor="attitude-note">
                {t("teacher.detail.attitude.note")}
              </label>
              <textarea
                id="attitude-note"
                value={attitudeNote}
                onChange={(e) => setAttitudeNote(e.target.value)}
                maxLength={1000}
                rows={2}
                style={{ ...inputStyle, resize: "vertical" }}
              />
            </div>
            <button
              onClick={saveAttitude}
              disabled={saving !== null}
              style={{ ...buttonStyle, marginTop: 12 }}
            >
              {saving === "attitude"
                ? t("teacher.detail.saving")
                : t("teacher.detail.attitude.save")}
            </button>
            {sectionStatus("attitude")}
          </section>

          <section style={cardStyle}>
            <p style={sectionTitleStyle}>{t("teacher.detail.passport.title")}</p>
            <p style={{ fontSize: 14, color: "#555", margin: "0 0 12px" }}>
              {detail.latest_passport === null ? (
                t("teacher.detail.passport.none")
              ) : (
                <>
                  {t("teacher.detail.passport.version", {
                    n: detail.latest_passport.version,
                  })}{" "}
                  ・{" "}
                  {t("teacher.detail.passport.generatedAt", {
                    date: formatDate(detail.latest_passport.created_at),
                  })}
                </>
              )}
            </p>
            <button onClick={generate} disabled={saving !== null} style={buttonStyle}>
              {saving === "passport"
                ? t("teacher.detail.passport.generating")
                : t("teacher.detail.passport.generate")}
            </button>
            {sectionStatus("passport")}
          </section>
        </>
      )}
    </main>
  );
}
