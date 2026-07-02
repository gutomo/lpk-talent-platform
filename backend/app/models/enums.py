import enum


class OrgType(enum.StrEnum):
    LPK = "lpk"
    COMPANY = "company"


class UserRole(enum.StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class Locale(enum.StrEnum):
    ID = "id"
    JA = "ja"


class Sector(enum.StrEnum):
    KAIGO = "kaigo"
    FOOD_MANUFACTURING = "food_manufacturing"
    RESTAURANT = "restaurant"
    GENERAL = "general"


class ContentModule(enum.StrEnum):
    PRONUNCIATION = "pronunciation"
    DRILL = "drill"


class SessionMode(enum.StrEnum):
    TEXT = "text"
    VOICE = "voice"


class SessionStatus(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TurnRole(enum.StrEnum):
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class ConversationRole(enum.StrEnum):
    PARTNER = "partner"
    STUDENT = "student"


class QuizSection(enum.StrEnum):
    GRAMMAR = "grammar"
    VOCABULARY = "vocabulary"
    READING = "reading"
    LISTENING = "listening"


class AttendanceKind(enum.StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
