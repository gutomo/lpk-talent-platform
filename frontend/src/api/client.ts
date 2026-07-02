const BASE = "/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    throw new ApiError(res.status, `${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// multipart 送信。Content-Type はブラウザが boundary 付きで設定するため指定しない。
// エラー時は FastAPI の detail（例: "no_speech: ..."）を message に載せる。
async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = "";
    try {
      detail = String(((await res.json()) as { detail?: unknown }).detail ?? "");
    } catch {
      // JSON でないエラー本文は無視する。
    }
    throw new ApiError(res.status, detail || `POST ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export type Role = "student" | "teacher" | "admin";

export interface User {
  id: number;
  org_id: number;
  name: string;
  email: string;
  role: Role;
  locale: "id" | "ja";
}

export interface StudentListItem {
  id: number;
  name: string;
  email: string;
  cohort_name: string | null;
  last_active_at: string | null;
}

export function getHealth(): Promise<{ status: string }> {
  return get<{ status: string }>("/health");
}

export function login(email: string, password: string): Promise<User> {
  return post<User>("/auth/login", { email, password });
}

export function logout(): Promise<void> {
  return post<void>("/auth/logout");
}

export function getMe(): Promise<User> {
  return get<User>("/auth/me");
}

export function getStudents(): Promise<StudentListItem[]> {
  return get<StudentListItem[]>("/students");
}

export type Sector = "kaigo" | "food_manufacturing" | "restaurant" | "general";

export interface PronunciationItem {
  id: number;
  sector: Sector;
  text_ja: string;
  furigana: string | null;
  gloss_id: string | null;
  level: string;
}

export interface WordScore {
  word: string;
  accuracy: number;
  error_type: string;
  phonemes: { phoneme: string; accuracy: number }[];
}

export interface WeakWord {
  word: string;
  accuracy: number;
}

export interface WeakWordAgg {
  word: string;
  accuracy: number;
  count: number;
}

export interface Assessment {
  attempt_id: number;
  item_id: number;
  provider: string;
  accuracy: number;
  fluency: number;
  completeness: number;
  pron: number;
  recognized_text: string;
  words: WordScore[];
  weak_words: WeakWord[];
}

export function getPronunciationItems(): Promise<PronunciationItem[]> {
  return get<PronunciationItem[]>("/speech/items");
}

export function getWeakWords(): Promise<WeakWordAgg[]> {
  return get<WeakWordAgg[]>("/speech/weak-words");
}

export function assessPronunciation(itemId: number, audio: Blob): Promise<Assessment> {
  const form = new FormData();
  form.append("item_id", String(itemId));
  form.append("audio", audio, "recording.webm");
  return postForm<Assessment>("/speech/assess", form);
}
