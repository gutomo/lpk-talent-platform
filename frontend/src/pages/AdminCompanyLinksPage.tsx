import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  companyShareUrl,
  createCompanyLink,
  getCompanyLinks,
  revokeCompanyLink,
  type CompanyShareLink,
  type User,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import { t } from "../i18n";

// 企業向け組織単位共有リンクの発行・失効（admin = LPK経営者専用）。
// トークン1本で全候補者の比較テーブルを開放するため、発行・失効はこの画面に集約する。

const cardStyle: React.CSSProperties = {
  border: "1px solid #ddd",
  borderRadius: 12,
  padding: 16,
  marginBottom: 12,
  background: "#fff",
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

const smallButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  padding: "6px 10px",
  fontSize: 13,
  background: "#fff",
  color: "#1a5fb4",
  border: "1px solid #1a5fb4",
};

function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

export default function AdminCompanyLinksPage({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [links, setLinks] = useState<CompanyShareLink[] | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  useEffect(() => {
    getCompanyLinks()
      .then(setLinks)
      .catch(() => setError(true));
  }, []);

  async function create() {
    setBusy(true);
    try {
      const link = await createCompanyLink();
      setLinks((prev) => [link, ...(prev ?? [])]);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(linkId: number) {
    setBusy(true);
    try {
      const updated = await revokeCompanyLink(linkId);
      setLinks((prev) =>
        prev === null ? prev : prev.map((l) => (l.id === updated.id ? updated : l)),
      );
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function copyLink(link: CompanyShareLink) {
    try {
      await navigator.clipboard.writeText(companyShareUrl(link.token));
      setCopiedId(link.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // クリップボード不可の環境ではURL表示のみで運用する。
    }
  }

  function status(link: CompanyShareLink): string {
    if (link.revoked) return t("admin.links.status.revoked");
    if (!link.active) return t("admin.links.status.expired");
    return t("admin.links.status.active", { date: formatDate(link.expires_at) });
  }

  return (
    <main
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <PageHeader title={t("admin.links.title")} user={user} onLogout={onLogout} />
      <p style={{ marginTop: 0, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Link to="/admin/kpi">{t("admin.links.toKpi")}</Link>
        <Link to="/teacher/students">{t("admin.kpi.toStudents")}</Link>
      </p>

      {error && (
        <p role="alert" style={{ color: "#b00020" }}>
          {t("common.error")}
        </p>
      )}

      <section style={cardStyle}>
        <p style={{ fontSize: 13, color: "#666", margin: "0 0 12px" }}>
          {t("admin.links.hint")}
        </p>
        <button onClick={create} disabled={busy} style={buttonStyle}>
          {busy ? t("admin.links.creating") : t("admin.links.create")}
        </button>

        {links !== null && links.length === 0 && (
          <p style={{ fontSize: 14, color: "#666", margin: "12px 0 0" }}>
            {t("admin.links.empty")}
          </p>
        )}
        {links !== null && links.length > 0 && (
          <ul style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
            {links.map((link) => (
              <li
                key={link.id}
                style={{
                  borderTop: "1px solid #eee",
                  padding: "10px 0",
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: link.active ? "#2e7d32" : "#9aa5b1",
                    whiteSpace: "nowrap",
                  }}
                >
                  {status(link)}
                </span>
                <span style={{ fontSize: 13, color: "#666", whiteSpace: "nowrap" }}>
                  {t("admin.links.createdAt", { date: formatDate(link.created_at) })} ・{" "}
                  {t("admin.links.views", { n: link.views })}
                  {link.last_viewed_at !== null && (
                    <>
                      {" "}
                      ・{" "}
                      {t("admin.links.lastViewed", { date: formatDate(link.last_viewed_at) })}
                    </>
                  )}
                </span>
                <span
                  style={{
                    fontSize: 12,
                    color: "#999",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    maxWidth: 180,
                    whiteSpace: "nowrap",
                  }}
                >
                  /company/{link.token}
                </span>
                <span style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
                  {link.active && (
                    <>
                      <button onClick={() => copyLink(link)} style={smallButtonStyle}>
                        {copiedId === link.id
                          ? t("admin.links.copied")
                          : t("admin.links.copy")}
                      </button>
                      <a
                        href={companyShareUrl(link.token)}
                        target="_blank"
                        rel="noreferrer"
                        style={{ ...smallButtonStyle, textDecoration: "none" }}
                      >
                        {t("admin.links.open")}
                      </a>
                      <button
                        onClick={() => revoke(link.id)}
                        disabled={busy}
                        style={{
                          ...smallButtonStyle,
                          color: "#c62828",
                          border: "1px solid #c62828",
                        }}
                      >
                        {t("admin.links.revoke")}
                      </button>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
