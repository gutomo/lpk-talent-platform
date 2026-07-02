import id from "./id.json";
import ja from "./ja.json";

export type Locale = "id" | "ja";

const dictionaries: Record<Locale, Record<string, string>> = { id, ja };

// Student UI defaults to Bahasa Indonesia; teacher/admin views use ja (see CLAUDE.md).
let currentLocale: Locale = "id";

export function setLocale(locale: Locale): void {
  currentLocale = locale;
}

export function getLocale(): Locale {
  return currentLocale;
}

export function t(key: string, params?: Record<string, string | number>): string {
  let text = dictionaries[currentLocale][key] ?? key;
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replace(`{${name}}`, String(value));
    }
  }
  return text;
}
