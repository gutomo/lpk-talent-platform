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

export type RiskLevel = "none" | "risk";

export interface StudentListItem {
  id: number;
  name: string;
  email: string;
  cohort_name: string | null;
  last_active_at: string | null;
  // クラス一覧の進捗・アラート列（backend の dashboard.class_overview 集計）。
  attendance_rate: number | null;
  interview_sessions: number;
  interview_latest_total: number | null;
  pron_avg_accuracy: number | null;
  risk_level: RiskLevel;
  risk_flags: string[];
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

export type AttendanceKind = "daily" | "monthly";

export interface AttendanceRecord {
  id: number;
  kind: AttendanceKind;
  record_date: string;
  value: number;
  note: string | null;
}

export interface PassportBrief {
  version: number;
  created_at: string;
}

// backend/app/services/records.py の ATTITUDE_ITEMS と同一キー・同一順。
export const ATTITUDE_KEYS = [
  "hourensou",
  "punctuality",
  "dormitory",
  "manner",
  "teamwork",
] as const;

export type AttitudeKey = (typeof ATTITUDE_KEYS)[number];

export type AttitudeChecklist = Record<AttitudeKey, number>;

export interface SnapshotStudent {
  name: string;
  cohort: string | null;
  sector: Sector | null;
}

// Passport snapshot（passport-v1）のうち詳細ページ・共有ビューが読む部分だけを型に起こす。
export interface StudentSummary {
  snapshot_version: string;
  generated_at: string;
  student: SnapshotStudent;
  japanese_level: {
    current: string | null;
    trend: { date: string; score: number }[];
  };
  pronunciation: {
    attempts: number;
    avg_accuracy: number | null;
    weak_words: { word: string; count: number; min_accuracy: number }[];
  };
  conversation: { completed: number };
  interview: {
    sessions: number;
    latest_total: number | null;
    avg_total: number | null;
    trend: { date: string; total: number }[];
    transcript_excerpt: string[];
  };
  attendance: { rate: number | null; records: number };
  attitude: {
    checklist: Partial<AttitudeChecklist>;
    note: string | null;
    reviewed_at: string;
  } | null;
  checklist: { key: string; label_ja: string; done: boolean }[];
  risk: { flags: string[]; level: "none" | "risk" };
}

export interface StudentDetail {
  id: number;
  name: string;
  email: string;
  cohort_name: string | null;
  sector: Sector | null;
  summary: StudentSummary;
  attendance_records: AttendanceRecord[];
  latest_passport: PassportBrief | null;
}

export interface AttendanceIn {
  kind: AttendanceKind;
  record_date: string;
  value: number;
  note: string | null;
}

export function getStudentDetail(studentId: number): Promise<StudentDetail> {
  return get<StudentDetail>(`/students/${studentId}`);
}

export interface StudentInterviewItem {
  session_id: number;
  scenario: string;
  title_ja: string | null;
  mode: "text" | "voice";
  total: number;
  created_at: string;
  reviewed_at: string | null;
}

export function getStudentInterviews(studentId: number): Promise<StudentInterviewItem[]> {
  return get<StudentInterviewItem[]>(`/students/${studentId}/interviews`);
}

export interface TranscriptTurn {
  seq: number;
  role: "interviewer" | "candidate";
  text_ja: string;
}

export interface TranscriptEvaluation {
  evaluation_id: number;
  rubric_version: string;
  scores: Record<string, number>;
  summary_ja: string | null;
  summary_id: string | null;
  total: number;
  reviewed_at: string | null;
  reviewer_name: string | null;
}

export interface InterviewTranscript {
  session_id: number;
  student_id: number;
  student_name: string;
  scenario: string;
  title_ja: string | null;
  mode: "text" | "voice";
  created_at: string;
  turns: TranscriptTurn[];
  evaluation: TranscriptEvaluation | null;
}

export function getInterviewTranscript(
  studentId: number,
  sessionId: number,
): Promise<InterviewTranscript> {
  return get<InterviewTranscript>(`/students/${studentId}/interviews/${sessionId}`);
}

export interface ReviewQueueItem {
  evaluation_id: number;
  session_id: number;
  student_id: number;
  student_name: string;
  scenario: string;
  title_ja: string | null;
  mode: "text" | "voice";
  total: number;
  created_at: string;
  waiting_days: number;
}

export function getReviewQueue(): Promise<ReviewQueueItem[]> {
  return get<ReviewQueueItem[]>("/review/queue");
}

export interface ReviewComplete {
  evaluation_id: number;
  reviewed_at: string;
  reviewer_id: number;
}

export function completeReview(evaluationId: number): Promise<ReviewComplete> {
  return post<ReviewComplete>(`/review/evaluations/${evaluationId}/complete`);
}

export interface RiskStudent {
  id: number;
  name: string;
  flags: string[];
}

export interface WeeklyPoint {
  week_start: string;
  events: number;
  active_students: number;
  mock_avg: number | null;
}

// PoC KPI カード（BUILD_PLAN の KPI 表と同一定義）。
export interface KpiCards {
  ai_usage_students: number;
  ai_usage_rate: number;
  interview_avg_sessions: number;
  interview_target_met: number;
  interview_improvement_pct: number | null;
  mock_early_avg: number | null;
  mock_recent_avg: number | null;
  review_pending: number;
  review_avg_waiting_days: number | null;
}

export interface AdminKpi {
  students: number;
  risk_students: RiskStudent[];
  n4_rate: number;
  mock_avg: number | null;
  attendance_avg: number | null;
  practice_events_7d: number;
  weekly: WeeklyPoint[];
  kpi_cards: KpiCards;
}

export function getAdminKpi(): Promise<AdminKpi> {
  return get<AdminKpi>("/dashboard/kpi");
}

export function postAttendance(
  studentId: number,
  body: AttendanceIn,
): Promise<StudentDetail> {
  return post<StudentDetail>(`/students/${studentId}/attendance`, body);
}

export function postAttitude(
  studentId: number,
  checklist: AttitudeChecklist,
  note: string | null,
): Promise<StudentDetail> {
  return post<StudentDetail>(`/students/${studentId}/attitude`, { checklist, note });
}

export interface PassportOut {
  passport_id: number;
  user_id: number;
  version: number;
  created_at: string;
  snapshot: StudentSummary;
}

export function generatePassport(studentId: number): Promise<PassportOut> {
  return post<PassportOut>(`/passports/${studentId}`);
}

// 教師用PDF（cookie認証）。<a href> で開くためURLだけ返す。
export function passportPdfUrl(studentId: number): string {
  return `${BASE}/passports/${studentId}/pdf`;
}

export interface ShareLink {
  id: number;
  token: string;
  passport_version: number;
  created_at: string;
  expires_at: string;
  revoked: boolean;
  active: boolean;
  views: number;
  last_viewed_at: string | null;
}

// 企業向け共有ビュー（ログイン不要）。snapshot は StudentSummary と同一構造。
export interface SharedPassport {
  version: number;
  created_at: string;
  expires_at: string;
  snapshot: StudentSummary;
}

export function getShareLinks(studentId: number): Promise<ShareLink[]> {
  return get<ShareLink[]>(`/passports/${studentId}/share-links`);
}

export function createShareLink(studentId: number): Promise<ShareLink> {
  return post<ShareLink>(`/passports/${studentId}/share-links`);
}

export function revokeShareLink(studentId: number, linkId: number): Promise<ShareLink> {
  return post<ShareLink>(`/passports/${studentId}/share-links/${linkId}/revoke`);
}

export function getSharedPassport(token: string): Promise<SharedPassport> {
  return get<SharedPassport>(`/share/${token}`);
}

export function sharedPdfUrl(token: string): string {
  return `${BASE}/share/${token}/pdf`;
}

// 企業に渡すURL（フロントの公開ページ）。トークンはURL経路のみで伝搬する。
export function shareUrl(token: string): string {
  return `${window.location.origin}/share/${token}`;
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

export type QuizSection = "grammar" | "vocabulary" | "reading" | "listening";

// 出題用の問題。answer_index / explanation_id は解答後のレスポンスにのみ含まれる。
// script_ja は聴解のみ。stub モードで browser TTS の読み上げに使う（画面には出さない）。
export interface QuizItem {
  item_id: number;
  section: QuizSection;
  level: string;
  question: string;
  choices: string[];
  passage_ja: string | null;
  script_ja: string | null;
  is_review: boolean;
}

export interface DailyQuiz {
  items: QuizItem[];
  review_count: number;
}

export interface QuizAnswerResult {
  is_correct: boolean;
  correct_index: number;
  explanation_id: string | null;
}

export interface MockExam {
  items: QuizItem[];
  num_questions: number;
}

export interface MockQuestionResult {
  item_id: number;
  is_correct: boolean;
  correct_index: number;
  explanation_id: string | null;
}

export interface MockResult {
  mock_id: number;
  score: number;
  num_questions: number;
  num_correct: number;
  band: string | null;
  results: MockQuestionResult[];
}

export interface MockHistoryItem {
  mock_id: number;
  score: number;
  num_questions: number;
  num_correct: number;
  created_at: string;
}

export function getDailyQuiz(): Promise<DailyQuiz> {
  return get<DailyQuiz>("/drill/daily");
}

export function postDrillAnswer(
  itemId: number,
  selectedIndex: number,
): Promise<QuizAnswerResult> {
  return post<QuizAnswerResult>("/drill/answers", {
    item_id: itemId,
    selected_index: selectedIndex,
  });
}

export function getMockExam(): Promise<MockExam> {
  return get<MockExam>("/mock/exam");
}

export function submitMockExam(
  answers: { item_id: number; selected_index: number }[],
): Promise<MockResult> {
  return post<MockResult>("/mock/submit", { answers });
}

export function getMockHistory(): Promise<MockHistoryItem[]> {
  return get<MockHistoryItem[]>("/mock/history");
}

// 聴解問題の合成音声。stub モードはサーバ音声なし(204)で null を返す（呼び出し側で browser TTS）。
export async function getMockListeningAudio(itemId: number): Promise<Blob | null> {
  const res = await fetch(`${BASE}/mock/items/${itemId}/audio`);
  if (res.status === 204) return null;
  if (!res.ok) {
    throw new ApiError(res.status, `GET listening audio failed: ${res.status}`);
  }
  return await res.blob();
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
