import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getSharedCandidates, type CandidateRow, type SharedCandidates } from "../api/client";
import { scoreColor } from "../components/TrendChart";
import { setLocale, t } from "../i18n";

// 企業向け候補者比較テーブル（ログイン不要・日本語のみ）。
// トークンはURL経路のみ。無効（不存在・失効・期限切れ）はAPIが一律404を返す。
// 各行から /company/:token/students/:studentId（個別Passport）へ遷移する。

const cardStyle: React.CSSProperties = {
  border: "1px solid #ddd",
  borderRadius: 12,
  padding: 16,
  marginBottom: 12,
  background: "#fff",
};

// ソート対象の列。値の取り出しだけ列ごとに定義し、比較は共通（null は常に末尾）。
type SortKey =
  | "name"
  | "level"
  | "pron"
  | "interview"
  | "sessions"
  | "attendance"
  | "checklist";

// JLPT帯（推定）を順序に落とす。未知の帯は 0（非null中で最下位）。
const LEVEL_RANK: Record<string, number> = { N4: 3, N5: 2, N5未満: 1 };

function sortValue(row: CandidateRow, key: SortKey): string | number | null {
  if (key === "name") return row.name;
  if (key === "level")
    return row.level_current !== null ? (LEVEL_RANK[row.level_current] ?? 0) : null;
  if (key === "pron") return row.pron_avg_accuracy;
  if (key === "interview") return row.interview_latest_total;
  if (key === "sessions") return row.interview_sessions;
  if (key === "attendance") return row.attendance_rate;
  return row.checklist_done;
}

function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

function Score({ value, suffix }: { value: number | null; suffix?: string }) {
  if (value === null) {
    return <span style={{ color: "#9aa5b1" }}>{t("share.none")}</span>;
  }
  return (
    <span style={{ fontWeight: 600, color: scoreColor(value) }}>
      {value}
      {suffix}
    </span>
  );
}

export default function CompanyCandidatesPage() {
  const params = useParams();
  const token = params.token ?? "";

  const [data, setData] = useState<SharedCandidates | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    // 公開ページは日本語のみ（ログイン状態の locale に依存しない）。
    setLocale("ja");
    if (token === "") {
      setInvalid(true);
      return;
    }
    getSharedCandidates(token)
      .then(setData)
      .catch(() => setInvalid(true));
  }, [token]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(key);
      // 氏名は昇順、スコア類は高い順が既定。
      setSortAsc(key === "name");
    }
  }

  const rows = useMemo(() => {
    const candidates = [...(data?.candidates ?? [])];
    candidates.sort((a, b) => {
      const va = sortValue(a, sortKey);
      const vb = sortValue(b, sortKey);
      if (va === null && vb === null) return a.name.localeCompare(b.name, "ja");
      if (va === null) return 1; // 計測中は昇順・降順どちらでも末尾
      if (vb === null) return -1;
      let cmp: number;
      if (typeof va === "string" && typeof vb === "string") {
        cmp = va.localeCompare(vb, "ja");
      } else {
        cmp = Number(va) - Number(vb);
      }
      if (cmp === 0) return a.name.localeCompare(b.name, "ja");
      return sortAsc ? cmp : -cmp;
    });
    return candidates;
  }, [data, sortKey, sortAsc]);

  const thStyle: React.CSSProperties = {
    padding: "8px 10px",
    fontSize: 12,
    color: "#666",
    textAlign: "left",
    whiteSpace: "nowrap",
    borderBottom: "2px solid #e3e8ef",
  };

  const tdStyle: React.CSSProperties = {
    padding: "10px",
    fontSize: 14,
    whiteSpace: "nowrap",
    borderBottom: "1px solid #eee",
  };

  function SortHeader({ label, k }: { label: string; k: SortKey }) {
    const active = sortKey === k;
    return (
      <th style={thStyle} aria-sort={active ? (sortAsc ? "ascending" : "descending") : "none"}>
        <button
          onClick={() => toggleSort(k)}
          style={{
            border: "none",
            background: "none",
            padding: 0,
            font: "inherit",
            color: active ? "#1a5fb4" : "#666",
            fontWeight: active ? 700 : 500,
            cursor: "pointer",
          }}
        >
          {label} {active ? (sortAsc ? "▲" : "▼") : ""}
        </button>
      </th>
    );
  }

  return (
    <main
      lang="ja"
      style={{
        maxWidth: 1080,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <header style={{ margin: "8px 0 16px" }}>
        <h1 style={{ margin: 0, fontSize: 22, color: "#1a5fb4" }}>
          Talent Passport <span style={{ fontSize: 15 }}>{t("company.subtitle")}</span>
        </h1>
        {data !== null && (
          <p style={{ margin: "6px 0 0", fontSize: 14, color: "#555" }}>
            {data.lpk_name} ・ {t("company.count", { n: data.candidates.length })}
          </p>
        )}
      </header>

      {invalid && (
        <p role="alert" style={{ ...cardStyle, color: "#b00020" }}>
          {t("share.invalid")}
        </p>
      )}
      {!invalid && data === null && <p>{t("common.loading")}</p>}

      {data !== null && (
        <>
          {data.candidates.length === 0 ? (
            <p style={{ ...cardStyle, fontSize: 14, color: "#666" }}>{t("company.empty")}</p>
          ) : (
            <div style={{ ...cardStyle, padding: 0, overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", width: "100%" }}>
                <thead>
                  <tr>
                    <SortHeader label={t("company.col.name")} k="name" />
                    <th style={thStyle}>{t("company.col.cohort")}</th>
                    <SortHeader label={t("company.col.level")} k="level" />
                    <SortHeader label={t("company.col.pron")} k="pron" />
                    <SortHeader label={t("company.col.interview")} k="interview" />
                    <SortHeader label={t("company.col.sessions")} k="sessions" />
                    <SortHeader label={t("company.col.attendance")} k="attendance" />
                    <SortHeader label={t("company.col.checklist")} k="checklist" />
                    <th style={thStyle}>{t("company.col.passport")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.student_id}>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>
                        <Link
                          to={`/company/${token}/students/${c.student_id}`}
                          style={{ color: "#1a5fb4" }}
                        >
                          {c.name}
                        </Link>
                      </td>
                      <td style={{ ...tdStyle, color: "#555", fontSize: 13 }}>
                        {c.cohort ?? "―"}
                        {c.sector !== null && (
                          <span style={{ color: "#9aa5b1" }}>
                            {" "}
                            / {t(`pron.sector.${c.sector}`)}
                          </span>
                        )}
                      </td>
                      <td style={tdStyle}>{c.level_current ?? t("share.none")}</td>
                      <td style={tdStyle}>
                        <Score value={c.pron_avg_accuracy} />
                      </td>
                      <td style={tdStyle}>
                        <Score value={c.interview_latest_total} />
                      </td>
                      <td style={{ ...tdStyle, color: "#555" }}>{c.interview_sessions}</td>
                      <td style={tdStyle}>
                        <Score value={c.attendance_rate} suffix="%" />
                      </td>
                      <td style={tdStyle}>
                        <span
                          style={{
                            fontWeight: 600,
                            color: c.checklist_done === c.checklist_total ? "#2e7d32" : "#555",
                          }}
                        >
                          {c.checklist_done}/{c.checklist_total}
                        </span>
                      </td>
                      <td style={{ ...tdStyle, fontSize: 13, color: "#555" }}>
                        {t("company.version", { n: c.passport_version })} ・{" "}
                        {formatDate(c.generated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p style={{ fontSize: 12, color: "#888", margin: "16px 0 8px" }}>
            {t("share.disclaimer")}
          </p>
          <p style={{ fontSize: 12, color: "#888", margin: "0 0 24px" }}>
            {t("share.expiresAt", { date: formatDate(data.expires_at) })}
          </p>
        </>
      )}
    </main>
  );
}
