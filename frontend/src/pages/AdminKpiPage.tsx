import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getAdminKpi, type AdminKpi, type WeeklyPoint, type User } from "../api/client";
import PageHeader from "../components/PageHeader";
import TrendChart, { scoreColor } from "../components/TrendChart";
import { t } from "../i18n";

const cardStyle: React.CSSProperties = {
  border: "1px solid #ddd",
  borderRadius: 12,
  padding: 16,
  background: "#fff",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  margin: "16px 0 10px",
};

// MM/DD 表記。週次チャートの軸ラベル用。
function shortDate(iso: string): string {
  return `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
}

function StatCard({
  label,
  value,
  detail,
  color,
}: {
  label: string;
  value: string;
  detail?: string;
  color?: string;
}) {
  return (
    <div style={{ ...cardStyle, flex: "1 1 150px", textAlign: "center" }}>
      <div style={{ fontSize: 12, color: "#666" }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color ?? "#333" }}>{value}</div>
      {detail !== undefined && (
        <div style={{ fontSize: 11, color: "#9aa5b1", marginTop: 4 }}>{detail}</div>
      )}
    </div>
  );
}

// 週次の単一系列バーチャート。0起点固定、棒間2px、最終週のみ直接ラベル、
// 各棒に <title>（ネイティブツールチップ）。系列は1本なので凡例は置かない。
function WeeklyBars({
  points,
  values,
  label,
}: {
  points: WeeklyPoint[];
  values: number[];
  label: string;
}) {
  const W = 300;
  const H = 120;
  const padX = 8;
  const padTop = 16;
  const padBottom = 18;
  const n = values.length;
  const max = Math.max(...values, 1);
  const gap = 2;
  const barW = (W - padX * 2 - gap * (n - 1)) / n;
  const plotH = H - padTop - padBottom;
  const y = (v: number) => padTop + (1 - v / max) * plotH;
  const last = values[n - 1];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={label}
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      <line
        x1={padX}
        y1={H - padBottom}
        x2={W - padX}
        y2={H - padBottom}
        stroke="#e3e8ef"
        strokeWidth={1}
      />
      {values.map((v, i) => {
        const x = padX + i * (barW + gap);
        return (
          <rect
            key={points[i].week_start}
            x={x}
            y={y(v)}
            width={barW}
            height={Math.max(H - padBottom - y(v), v > 0 ? 2 : 0)}
            rx={2}
            fill="#1a5fb4"
          >
            <title>{`${shortDate(points[i].week_start)}: ${v}`}</title>
          </rect>
        );
      })}
      <text
        x={padX + (n - 1) * (barW + gap) + barW / 2}
        y={y(last) - 5}
        fontSize={11}
        fontWeight={600}
        fill="#1a5fb4"
        textAnchor="middle"
      >
        {last}
      </text>
      <text x={padX} y={H - 5} fontSize={9} fill="#9aa5b1">
        {shortDate(points[0].week_start)}
      </text>
      <text x={W - padX} y={H - 5} fontSize={9} fill="#9aa5b1" textAnchor="end">
        {shortDate(points[n - 1].week_start)}
      </text>
    </svg>
  );
}

export default function AdminKpiPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [kpi, setKpi] = useState<AdminKpi | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getAdminKpi()
      .then(setKpi)
      .catch(() => setError(true));
  }, []);

  const none = t("admin.kpi.none");
  const cards = kpi?.kpi_cards ?? null;
  const mockTrend = (kpi?.weekly ?? [])
    .map((w) => w.mock_avg)
    .filter((v): v is number => v !== null);

  return (
    <main
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("admin.kpi.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Link to="/teacher/students">{t("admin.kpi.toStudents")}</Link>
        <Link to="/teacher/review">{t("teacher.queue.link")}</Link>
      </p>

      {error && (
        <p role="alert" style={{ color: "#b00020" }}>
          {t("common.error")}
        </p>
      )}
      {!error && kpi === null && <p>{t("common.loading")}</p>}

      {kpi !== null && cards !== null && (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <StatCard label={t("admin.kpi.students")} value={String(kpi.students)} />
            <StatCard
              label={t("admin.kpi.risk")}
              value={String(kpi.risk_students.length)}
              color={kpi.risk_students.length > 0 ? "#c62828" : "#2e7d32"}
            />
            <StatCard
              label={t("admin.kpi.n4Rate")}
              value={`${kpi.n4_rate}%`}
              color={scoreColor(kpi.n4_rate)}
            />
            <StatCard
              label={t("admin.kpi.mockAvg")}
              value={kpi.mock_avg !== null ? String(kpi.mock_avg) : none}
              color={kpi.mock_avg !== null ? scoreColor(kpi.mock_avg) : undefined}
            />
            <StatCard
              label={t("admin.kpi.attendanceAvg")}
              value={kpi.attendance_avg !== null ? `${kpi.attendance_avg}%` : none}
              color={kpi.attendance_avg !== null ? scoreColor(kpi.attendance_avg) : undefined}
            />
          </div>

          <p style={sectionTitleStyle}>{t("admin.kpi.pocTitle")}</p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <StatCard
              label={t("admin.kpi.aiUsage")}
              value={`${cards.ai_usage_rate}%`}
              detail={t("admin.kpi.aiUsageDetail", { n: cards.ai_usage_students })}
              color={scoreColor(cards.ai_usage_rate)}
            />
            <StatCard
              label={t("admin.kpi.itvCount")}
              value={t("admin.kpi.itvCountValue", { n: cards.interview_avg_sessions })}
              detail={t("admin.kpi.itvCountDetail", { n: cards.interview_target_met })}
            />
            <StatCard
              label={t("admin.kpi.itvImprove")}
              value={
                cards.interview_improvement_pct !== null
                  ? `${cards.interview_improvement_pct >= 0 ? "+" : ""}${cards.interview_improvement_pct}%`
                  : none
              }
              detail={t("admin.kpi.itvImproveDetail")}
              color={
                cards.interview_improvement_pct !== null
                  ? cards.interview_improvement_pct >= 10
                    ? "#2e7d32"
                    : cards.interview_improvement_pct >= 0
                      ? "#f9a825"
                      : "#c62828"
                  : undefined
              }
            />
            <StatCard
              label={t("admin.kpi.mockTrendCard")}
              value={
                cards.mock_early_avg !== null && cards.mock_recent_avg !== null
                  ? `${cards.mock_early_avg} → ${cards.mock_recent_avg}`
                  : none
              }
              detail={t("admin.kpi.mockTrendDetail")}
            />
            <StatCard
              label={t("admin.kpi.reviewQueue")}
              value={t("admin.kpi.reviewQueueValue", { n: cards.review_pending })}
              detail={
                cards.review_avg_waiting_days !== null
                  ? t("admin.kpi.reviewQueueDetail", { d: cards.review_avg_waiting_days })
                  : undefined
              }
              color={cards.review_pending > 0 ? "#f9a825" : "#2e7d32"}
            />
          </div>

          <p style={sectionTitleStyle}>{t("admin.kpi.weeklyTitle")}</p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div style={{ ...cardStyle, flex: "1 1 280px" }}>
              <p style={{ fontSize: 13, color: "#666", margin: "0 0 6px" }}>
                {t("admin.kpi.weeklyEvents")}
              </p>
              <WeeklyBars
                points={kpi.weekly}
                values={kpi.weekly.map((w) => w.events)}
                label={t("admin.kpi.weeklyEvents")}
              />
            </div>
            <div style={{ ...cardStyle, flex: "1 1 280px" }}>
              <p style={{ fontSize: 13, color: "#666", margin: "0 0 6px" }}>
                {t("admin.kpi.weeklyActive")}
              </p>
              <WeeklyBars
                points={kpi.weekly}
                values={kpi.weekly.map((w) => w.active_students)}
                label={t("admin.kpi.weeklyActive")}
              />
            </div>
            {mockTrend.length >= 2 && (
              <div style={{ ...cardStyle, flex: "1 1 280px" }}>
                <p style={{ fontSize: 13, color: "#666", margin: "0 0 6px" }}>
                  {t("admin.kpi.weeklyMock")}
                </p>
                <TrendChart scores={mockTrend} label={t("admin.kpi.weeklyMock")} />
              </div>
            )}
          </div>

          <p style={sectionTitleStyle}>{t("admin.kpi.riskList")}</p>
          <div style={cardStyle}>
            {kpi.risk_students.length === 0 ? (
              <p style={{ fontSize: 14, color: "#666", margin: 0 }}>
                {t("admin.kpi.riskEmpty")}
              </p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {kpi.risk_students.map((s) => (
                  <li
                    key={s.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: 8,
                      padding: "8px 0",
                      borderBottom: "1px solid #eee",
                      fontSize: 14,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: "2px 10px",
                        borderRadius: 999,
                        background: "#fdecea",
                        color: "#c62828",
                        whiteSpace: "nowrap",
                      }}
                    >
                      ⚠ {t("teacher.detail.riskBadge")}
                    </span>
                    <Link to={`/teacher/students/${s.id}`} style={{ color: "#1a5fb4" }}>
                      {s.name}
                    </Link>
                    <span style={{ color: "#666", fontSize: 13 }}>
                      {s.flags.map((flag) => t(`teacher.detail.risk.${flag}`)).join(" / ")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </main>
  );
}
