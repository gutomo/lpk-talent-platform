// スコア推移の折れ線グラフ（0〜100固定軸）。外部ライブラリを使わず inline SVG で描く。
// scores は時系列昇順（古い→新しい）。2件以上のときだけ呼ぶ。
// 学生の面接ページと教師の学生詳細ページで共有する。

export function scoreColor(score: number): string {
  if (score >= 80) return "#2e7d32";
  if (score >= 60) return "#f9a825";
  return "#c62828";
}

export default function TrendChart({ scores, label }: { scores: number[]; label: string }) {
  const W = 300;
  const H = 120;
  const padX = 22;
  const padY = 14;
  const n = scores.length;
  const x = (i: number) => padX + (i * (W - padX * 2)) / (n - 1);
  const y = (v: number) => padY + (1 - v / 100) * (H - padY * 2);
  const points = scores.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const last = scores[n - 1];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={label}
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      {[0, 50, 100].map((g) => (
        <g key={g}>
          <line x1={padX} y1={y(g)} x2={W - padX} y2={y(g)} stroke="#e3e8ef" strokeWidth={1} />
          <text x={0} y={y(g) + 3} fontSize={9} fill="#9aa5b1">
            {g}
          </text>
        </g>
      ))}
      <polyline points={points} fill="none" stroke="#1a5fb4" strokeWidth={2} />
      {scores.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={3.5} fill={scoreColor(v)} />
      ))}
      <text
        x={x(n - 1)}
        y={y(last) - 7}
        fontSize={11}
        fontWeight={600}
        fill={scoreColor(last)}
        textAnchor="end"
      >
        {last}
      </text>
    </svg>
  );
}
