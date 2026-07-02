import { useEffect, useState } from "react";

import { getHealth } from "./api/client";
import { t } from "./i18n";

export default function App() {
  const [status, setStatus] = useState<string>("...");

  useEffect(() => {
    getHealth()
      .then((r) => setStatus(r.status))
      .catch(() => setStatus("error"));
  }, []);

  return (
    <main
      style={{
        maxWidth: 480,
        margin: "0 auto",
        padding: 16,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1>{t("app.title")}</h1>
      <p>{t("app.tagline")}</p>
      <p>
        API: <strong>{status}</strong>
      </p>
    </main>
  );
}
