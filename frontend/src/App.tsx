import { useEffect, useState, type ReactElement } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { getMe, logout, type Role, type User } from "./api/client";
import { setLocale, t } from "./i18n";
import AdminKpiPage from "./pages/AdminKpiPage";
import ConversationPage from "./pages/ConversationPage";
import DrillPage from "./pages/DrillPage";
import InterviewPage from "./pages/InterviewPage";
import LoginPage from "./pages/LoginPage";
import MockExamPage from "./pages/MockExamPage";
import PronunciationPage from "./pages/PronunciationPage";
import SharePassportPage from "./pages/SharePassportPage";
import StudentHomePage from "./pages/StudentHomePage";
import TeacherInterviewTranscriptPage from "./pages/TeacherInterviewTranscriptPage";
import TeacherReviewQueuePage from "./pages/TeacherReviewQueuePage";
import TeacherStudentDetailPage from "./pages/TeacherStudentDetailPage";
import TeacherStudentsPage from "./pages/TeacherStudentsPage";

function homePath(role: Role): string {
  if (role === "student") return "/student";
  // 経営者はKPIダッシュボード、教師はクラス一覧が起点。
  return role === "admin" ? "/admin/kpi" : "/teacher/students";
}

function RoleRoute({
  user,
  roles,
  children,
}: {
  user: User | null;
  roles: Role[];
  children: ReactElement;
}) {
  if (user === null) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) return <Navigate to={homePath(user.role)} replace />;
  return children;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    getMe()
      .then((me) => {
        setLocale(me.locale);
        setUser(me);
      })
      .catch(() => setUser(null))
      .finally(() => setBooting(false));
  }, []);

  function handleLogin(me: User) {
    setLocale(me.locale);
    setUser(me);
  }

  async function handleLogout() {
    try {
      await logout();
    } finally {
      setLocale("id");
      setUser(null);
    }
  }

  if (booting) {
    return (
      <main style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
        <p>{t("common.loading")}</p>
      </main>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            user !== null ? (
              <Navigate to={homePath(user.role)} replace />
            ) : (
              <LoginPage onLogin={handleLogin} />
            )
          }
        />
        <Route
          path="/student"
          element={
            <RoleRoute user={user} roles={["student"]}>
              <StudentHomePage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/student/pronunciation"
          element={
            <RoleRoute user={user} roles={["student"]}>
              <PronunciationPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/student/conversation"
          element={
            <RoleRoute user={user} roles={["student"]}>
              <ConversationPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/student/interview"
          element={
            <RoleRoute user={user} roles={["student"]}>
              <InterviewPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/student/drill"
          element={
            <RoleRoute user={user} roles={["student"]}>
              <DrillPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/student/mock"
          element={
            <RoleRoute user={user} roles={["student"]}>
              <MockExamPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/teacher/students"
          element={
            <RoleRoute user={user} roles={["teacher", "admin"]}>
              <TeacherStudentsPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/teacher/students/:studentId"
          element={
            <RoleRoute user={user} roles={["teacher", "admin"]}>
              <TeacherStudentDetailPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/teacher/students/:studentId/interviews/:sessionId"
          element={
            <RoleRoute user={user} roles={["teacher", "admin"]}>
              <TeacherInterviewTranscriptPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/teacher/review"
          element={
            <RoleRoute user={user} roles={["teacher", "admin"]}>
              <TeacherReviewQueuePage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        <Route
          path="/admin/kpi"
          element={
            <RoleRoute user={user} roles={["admin"]}>
              <AdminKpiPage user={user as User} onLogout={handleLogout} />
            </RoleRoute>
          }
        />
        {/* 企業向け共有ビュー。ログイン不要（トークンのみで認可、日本語のみ）。 */}
        <Route path="/share/:token" element={<SharePassportPage />} />
        <Route
          path="*"
          element={<Navigate to={user !== null ? homePath(user.role) : "/login"} replace />}
        />
      </Routes>
    </BrowserRouter>
  );
}
