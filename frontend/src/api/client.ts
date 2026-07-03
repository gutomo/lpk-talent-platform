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

export interface Scenario {
  key: string;
  title_ja: string;
  title_id: string;
  description_id: string;
  level: string;
  max_student_turns: number;
}

export type ConversationRole = "partner" | "student";

export interface ConversationTurn {
  seq: number;
  role: ConversationRole;
  text_ja: string;
  furigana: string | null;
  hint_id: string | null;
}

export interface ConversationSession {
  session_id: number;
  scenario: string;
  status: "in_progress" | "completed" | "abandoned";
  max_student_turns: number;
  turns: ConversationTurn[];
  done: boolean;
}

export interface ConversationReply {
  student_turn: ConversationTurn;
  partner_turn: ConversationTurn;
  done: boolean;
}

export type InterviewRole = "interviewer" | "candidate";

export interface InterviewScenario {
  key: string;
  title_ja: string;
  title_id: string;
  description_id: string;
  level: string;
  sector: Sector;
  max_candidate_turns: number;
}

export interface InterviewTurn {
  seq: number;
  role: InterviewRole;
  text_ja: string;
  furigana: string | null;
  hint_id: string | null;
}

export interface InterviewModelAnswer {
  question_ja: string;
  answer_ja: string;
}

export interface InterviewEvaluation {
  rubric_version: string;
  scores: Record<string, number>;
  total: number;
  summary_id: string | null;
  summary_ja: string | null;
  advice_id: string | null;
  model_answers: InterviewModelAnswer[];
}

export interface InterviewSession {
  session_id: number;
  scenario: string;
  status: "in_progress" | "completed" | "abandoned";
  mode: "text" | "voice";
  max_candidate_turns: number;
  turns: InterviewTurn[];
  done: boolean;
  evaluation: InterviewEvaluation | null;
}

export interface InterviewReply {
  candidate_turn: InterviewTurn;
  interviewer_turn: InterviewTurn;
  done: boolean;
  evaluation: InterviewEvaluation | null;
}

export interface InterviewHistoryItem {
  session_id: number;
  scenario: string;
  title_id: string | null;
  title_ja: string | null;
  sector: Sector;
  mode: "text" | "voice";
  total: number;
  created_at: string;
}

export interface Streak {
  days: number;
  active_today: boolean;
}

export function getScenarios(): Promise<Scenario[]> {
  return get<Scenario[]>("/conversation/scenarios");
}

export function createConversationSession(scenario: string): Promise<ConversationSession> {
  return post<ConversationSession>("/conversation/sessions", { scenario });
}

export function sendConversationReply(
  sessionId: number,
  textJa: string,
): Promise<ConversationReply> {
  return post<ConversationReply>(`/conversation/sessions/${sessionId}/reply`, {
    text_ja: textJa,
  });
}

export function getStreak(): Promise<Streak> {
  return get<Streak>("/me/streak");
}

export function getInterviewScenarios(): Promise<InterviewScenario[]> {
  return get<InterviewScenario[]>("/interview/scenarios");
}

export function createInterviewSession(
  scenario: string,
  mode: "text" | "voice" = "text",
): Promise<InterviewSession> {
  return post<InterviewSession>("/interview/sessions", { scenario, mode });
}

export function sendInterviewReply(sessionId: number, textJa: string): Promise<InterviewReply> {
  return post<InterviewReply>(`/interview/sessions/${sessionId}/reply`, { text_ja: textJa });
}

// 音声モードの返信。録音（WebM/Opus 等）を送り、STT の認識テキストは candidate_turn.text_ja に入る。
export function sendInterviewVoiceReply(
  sessionId: number,
  audio: Blob,
): Promise<InterviewReply> {
  const form = new FormData();
  form.append("audio", audio, "recording.webm");
  return postForm<InterviewReply>(`/interview/sessions/${sessionId}/reply/voice`, form);
}

// 面接官ターンの合成音声。stub モードはサーバ音声なし(204)で null を返す（呼び出し側で browser TTS）。
export async function getInterviewTurnAudio(
  sessionId: number,
  seq: number,
): Promise<Blob | null> {
  const res = await fetch(`${BASE}/interview/sessions/${sessionId}/turns/${seq}/audio`);
  if (res.status === 204) return null;
  if (!res.ok) {
    throw new ApiError(res.status, `GET turn audio failed: ${res.status}`);
  }
  return await res.blob();
}

export function getInterviewHistory(): Promise<InterviewHistoryItem[]> {
  return get<InterviewHistoryItem[]>("/interview/history");
}

export function getInterviewSession(sessionId: number): Promise<InterviewSession> {
  return get<InterviewSession>(`/interview/sessions/${sessionId}`);
}
