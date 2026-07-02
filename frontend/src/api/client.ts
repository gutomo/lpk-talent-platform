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
