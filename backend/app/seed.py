"""デモ用seedデータ生成。全て架空データ（PII最小化方針）。乱数は固定シードで決定的。

学生30名の内訳：優秀層8名（スコア上昇）、平均層21名（横ばい〜微増）、
リスク学生1名（出席率80%未満 + スコア下降 + 直近12日間未利用の3条件を満たす）。
"""

import random
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.models.enums import (
    AttendanceKind,
    ContentModule,
    Locale,
    OrgType,
    Sector,
    SessionMode,
    SessionStatus,
    TurnRole,
    UserRole,
)
from app.services.auth import hash_password

STUDENT_PASSWORD = "siswa-demo-123"
TEACHER_PASSWORD = "sensei-demo-123"
ADMIN_PASSWORD = "admin-demo-123"

RUBRIC_VERSION = "seed-v0"
HISTORY_DAYS = 60
RISK_INACTIVE_DAYS = 12

TOP_COUNT = 8
RISK_INDEX = 29

# 架空のインドネシア名30組（実在の有名人と重ならない一般的な組み合わせ）
STUDENT_NAMES = [
    ("Siti", "Rahmawati"), ("Budi", "Santoso"), ("Dewi", "Anggraini"), ("Agus", "Wijaya"),
    ("Rina", "Kusuma"), ("Andi", "Saputra"), ("Ayu", "Utami"), ("Eko", "Hidayat"),
    ("Putri", "Maharani"), ("Joko", "Setiawan"), ("Indah", "Purnama"), ("Wahyu", "Nugroho"),
    ("Ratna", "Sari"), ("Fajar", "Ramadhan"), ("Yuni", "Astuti"), ("Gilang", "Permana"),
    ("Fitri", "Handayani"), ("Rudi", "Hartono"), ("Wulan", "Safitri"), ("Dedi", "Kurniawan"),
    ("Nur", "Aini"), ("Hendra", "Susanto"), ("Lia", "Puspitasari"), ("Bayu", "Firmansyah"),
    ("Mega", "Lestari"), ("Arif", "Rahman"), ("Sari", "Wulandari"), ("Doni", "Prasetyo"),
    ("Tika", "Amelia"), ("Rizky", "Pratama"),
]

CONTENT_ITEMS = [
    (Sector.KAIGO, "おはようございます。今日の体調はいかがですか。",
     "おはようございます。きょうのたいちょうはいかがですか。",
     "Selamat pagi. Bagaimana kondisi badan Anda hari ini?"),
    (Sector.KAIGO, "朝の検温の時間です。体温を測りますね。",
     "あさのけんおんのじかんです。たいおんをはかりますね。",
     "Sekarang waktunya pengukuran suhu pagi. Saya ukur suhu tubuh Anda ya."),
    (Sector.KAIGO, "田中さん、お薬の時間です。お水をどうぞ。",
     "たなかさん、おくすりのじかんです。おみずをどうぞ。",
     "Bapak/Ibu Tanaka, waktunya minum obat. Silakan airnya."),
    (Sector.KAIGO, "ゆっくり立ち上がってください。手すりにつかまってくださいね。",
     "ゆっくりたちあがってください。てすりにつかまってくださいね。",
     "Silakan berdiri pelan-pelan. Pegang pegangannya ya."),
    (Sector.KAIGO, "朝ごはんはぜんぶ食べられましたか。",
     "あさごはんはぜんぶたべられましたか。",
     "Apakah sarapannya sudah dihabiskan?"),
    (Sector.KAIGO, "何かあったら、すぐにナースコールを押してください。",
     "なにかあったら、すぐにナースコールをおしてください。",
     "Kalau terjadi sesuatu, segera tekan tombol panggilan perawat."),
    (Sector.GENERAL, "はじめまして。インドネシアから来ました。よろしくお願いします。",
     "はじめまして。インドネシアからきました。よろしくおねがいします。",
     "Perkenalkan, saya datang dari Indonesia. Mohon bantuannya."),
    (Sector.GENERAL, "すみません、もう一度ゆっくり話してください。",
     "すみません、もういちどゆっくりはなしてください。",
     "Maaf, tolong bicara sekali lagi dengan pelan."),
    (Sector.GENERAL, "昨日はよく眠れましたか。",
     "きのうはよくねむれましたか。",
     "Apakah semalam tidurnya nyenyak?"),
    (Sector.GENERAL, "今日はいい天気ですね。散歩に行きましょう。",
     "きょうはいいてんきですね。さんぽにいきましょう。",
     "Hari ini cuacanya bagus ya. Ayo kita jalan-jalan."),
    (Sector.FOOD_MANUFACTURING, "手を洗ってから、作業を始めます。",
     "てをあらってから、さぎょうをはじめます。",
     "Cuci tangan dulu sebelum mulai bekerja."),
    (Sector.FOOD_MANUFACTURING, "賞味期限を確認してください。",
     "しょうみきげんをかくにんしてください。",
     "Tolong periksa tanggal kedaluwarsa."),
]

INTERVIEW_TURNS = [
    (TurnRole.INTERVIEWER, "自己紹介をお願いします。"),
    (TurnRole.CANDIDATE, "はじめまして。インドネシアから来ました。よろしくお願いいたします。"),
    (TurnRole.INTERVIEWER, "どうして日本でこの仕事をしたいですか。"),
    (TurnRole.CANDIDATE, "家族の世話をした経験があり、日本の技術を学びたいからです。"),
    (TurnRole.INTERVIEWER, "困ったことがあったら、どうしますか。"),
    (TurnRole.CANDIDATE, "すぐに安全を確認して、リーダーに報告します。"),
]

EVAL_AXES = ["japanese", "consistency", "keigo", "hourensou", "clarity"]
CHECKLIST_KEYS = ["hourensou", "punctuality", "dormitory", "manner", "teamwork"]

# segment -> (発音base, 発音gain, 面接base, 面接gain, 週あたり活動確率, 出席率範囲)
SEGMENT_PARAMS = {
    "top": (70.0, 15.0, 58.0, 12.0, 0.75, (93, 99)),
    "mid": (62.0, 6.0, 55.0, 4.0, 0.45, (84, 96)),
    "risk": (58.0, -10.0, 60.0, -12.0, 0.50, (68, 76)),
}


def _segment(index: int) -> str:
    if index == RISK_INDEX:
        return "risk"
    return "top" if index < TOP_COUNT else "mid"


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def reset_all(db: Session) -> None:
    """FK依存の逆順で全行を削除する。"""
    tables = [
        models.Event, models.AuthSession, models.QuizAttempt, models.MockSession,
        models.InterviewEvaluation, models.InterviewTurn, models.InterviewSession,
        models.ConversationSession, models.PronunciationAttempt, models.ShareLink,
        models.Passport, models.AttendanceRecord, models.AttitudeReview, models.QuizItem,
        models.Enrollment, models.Cohort, models.ContentItem, models.User, models.Organization,
    ]
    for table in tables:
        db.execute(delete(table))
    db.commit()


def seed_all(db: Session, now: datetime, rng_seed: int = 42) -> dict[str, object]:
    if db.execute(select(models.User.id).limit(1)).first() is not None:
        raise RuntimeError("DB is not empty. Run with reset to reseed.")

    rng = random.Random(rng_seed)
    start = now - timedelta(days=HISTORY_DAYS - 1)

    lpk = models.Organization(name="LPK Harapan Nusantara", type=OrgType.LPK)
    company = models.Organization(name="株式会社さくらケアジャパン", type=OrgType.COMPANY)
    db.add_all([lpk, company])
    db.flush()

    teacher_hash = hash_password(TEACHER_PASSWORD)
    teachers = [
        models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA, name="田中 美咲",
                    email="misaki.tanaka@lpk-demo.example", password_hash=teacher_hash),
        models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA, name="佐藤 健一",
                    email="kenichi.sato@lpk-demo.example", password_hash=teacher_hash),
    ]
    admin = models.User(org_id=lpk.id, role=UserRole.ADMIN, locale=Locale.JA,
                        name="Hendra Gunawan", email="hendra.gunawan@lpk-demo.example",
                        password_hash=hash_password(ADMIN_PASSWORD))
    db.add_all([*teachers, admin])

    student_hash = hash_password(STUDENT_PASSWORD)
    students = []
    for first, last in STUDENT_NAMES:
        students.append(models.User(
            org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
            name=f"{first} {last}",
            email=f"{first.lower()}.{last.lower()}@student.lpk-demo.example",
            password_hash=student_hash,
            created_at=start - timedelta(days=30),
        ))
    db.add_all(students)
    db.flush()

    cohort_start = (start - timedelta(days=30)).date()
    cohort_kaigo = models.Cohort(org_id=lpk.id, name="2026年4月期 介護コース",
                                 sector=Sector.KAIGO, start_date=cohort_start)
    cohort_food = models.Cohort(org_id=lpk.id, name="2026年4月期 食品製造コース",
                                sector=Sector.FOOD_MANUFACTURING, start_date=cohort_start)
    db.add_all([cohort_kaigo, cohort_food])
    db.flush()
    for i, student in enumerate(students):
        cohort = cohort_kaigo if i < 20 else cohort_food
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=student.id))

    items = []
    for sector, text_ja, furigana, gloss in CONTENT_ITEMS:
        items.append(models.ContentItem(
            module=ContentModule.PRONUNCIATION, sector=sector, text_ja=text_ja,
            furigana=furigana, gloss_id=gloss, level="A2", meta={},
        ))
    db.add_all(items)
    db.flush()

    def items_for(sector: Sector) -> list[models.ContentItem]:
        return [i for i in items if i.sector in (sector, Sector.GENERAL)]

    def log(user_id: int, event_type: str, at: datetime, meta: dict | None = None) -> None:
        db.add(models.Event(user_id=user_id, type=event_type, meta=meta or {}, created_at=at))

    for i, student in enumerate(students):
        seg = _segment(i)
        pron_base, pron_gain, itv_base, itv_gain, act_prob, att_range = SEGMENT_PARAMS[seg]
        sector = Sector.KAIGO if i < 20 else Sector.FOOD_MANUFACTURING
        my_items = items_for(sector)
        next_interview_in = rng.randint(2, 6)

        for day in range(HISTORY_DAYS):
            date_ = start + timedelta(days=day)
            # リスク学生は直近 RISK_INACTIVE_DAYS 日間、完全に未利用
            if seg == "risk" and (now - date_).days < RISK_INACTIVE_DAYS:
                continue
            if rng.random() >= act_prob:
                continue

            progress = day / (HISTORY_DAYS - 1)
            at = datetime.combine(date_.date(), time(hour=rng.randint(10, 13),
                                                     minute=rng.randint(0, 59)), tzinfo=UTC)
            log(student.id, "login", at)

            for _ in range(rng.randint(1, 3)):
                item = rng.choice(my_items)
                accuracy = _clamp(pron_base + pron_gain * progress + rng.uniform(-3, 3))
                scores = {
                    "accuracy": accuracy,
                    "fluency": _clamp(accuracy + rng.uniform(-6, 4)),
                    "completeness": _clamp(accuracy + rng.uniform(-2, 6)),
                }
                weak = rng.sample(["検温", "手すり", "賞味期限", "報告", "確認"],
                                  k=(2 if accuracy < 70 else (1 if accuracy < 82 else 0)))
                at = at + timedelta(minutes=rng.randint(2, 8))
                attempt = models.PronunciationAttempt(
                    user_id=student.id, item_id=item.id, scores=scores,
                    weak_words=[{"word": w, "accuracy": _clamp(accuracy - rng.uniform(12, 25))}
                                for w in weak],
                    created_at=at,
                )
                db.add(attempt)
                db.flush()
                log(student.id, "pronunciation_attempt", at,
                    {"attempt_id": attempt.id, "item_id": item.id, "accuracy": accuracy})

            next_interview_in -= 1
            if next_interview_in <= 0:
                next_interview_in = rng.randint(4, 7) if seg != "top" else rng.randint(3, 5)
                at = at + timedelta(minutes=rng.randint(5, 15))
                session = models.InterviewSession(
                    user_id=student.id, scenario="self_intro_basic", sector=sector,
                    mode=SessionMode.VOICE if rng.random() < 0.6 else SessionMode.TEXT,
                    status=SessionStatus.COMPLETED, created_at=at,
                )
                db.add(session)
                db.flush()
                for seq, (turn_role, text_ja) in enumerate(INTERVIEW_TURNS, start=1):
                    db.add(models.InterviewTurn(
                        session_id=session.id, seq=seq, role=turn_role, text_ja=text_ja,
                        stt=None, created_at=at + timedelta(minutes=seq),
                    ))
                axes = {a: _clamp(itv_base + itv_gain * progress + rng.uniform(-4, 4))
                        for a in EVAL_AXES}
                total = _clamp(itv_base + itv_gain * progress + rng.uniform(-2, 2))
                eval_at = at + timedelta(minutes=len(INTERVIEW_TURNS) + 2)
                db.add(models.InterviewEvaluation(
                    session_id=session.id, rubric_version=RUBRIC_VERSION, scores=axes,
                    feedback={
                        "id": "Jawaban Anda sudah jelas. Latih penggunaan keigo lebih lanjut.",
                        "ja": "回答は明確です。敬語の使い方をさらに練習しましょう。",
                    },
                    total=total, created_at=eval_at,
                ))
                log(student.id, "interview_completed", eval_at,
                    {"session_id": session.id, "total": total})

            if rng.random() < 0.25:
                at = at + timedelta(minutes=rng.randint(5, 15))
                conv = models.ConversationSession(
                    user_id=student.id, scenario="morning_greeting", sector=sector,
                    mode=SessionMode.VOICE, status=SessionStatus.COMPLETED, created_at=at,
                )
                db.add(conv)
                db.flush()
                log(student.id, "conversation_completed", at, {"session_id": conv.id})

        for day in (10, 25, 40, 55):
            date_ = start + timedelta(days=day)
            if seg == "risk" and (now - date_).days < RISK_INACTIVE_DAYS:
                continue
            progress = day / (HISTORY_DAYS - 1)
            score = _clamp(itv_base + itv_gain * progress + rng.uniform(-3, 3))
            at = datetime.combine(date_.date(), time(hour=12), tzinfo=UTC)
            mock = models.MockSession(
                user_id=student.id, score=score, num_questions=25,
                num_correct=round(score / 4), meta={"level": "N4"}, created_at=at,
            )
            db.add(mock)
            db.flush()
            log(student.id, "mock_completed", at, {"mock_id": mock.id, "score": score})

        for month_offset in (2, 1):
            first_of_month = (now.date().replace(day=1) - timedelta(days=1)).replace(day=1)
            if month_offset == 2:
                first_of_month = (first_of_month - timedelta(days=1)).replace(day=1)
            db.add(models.AttendanceRecord(
                user_id=student.id, kind=AttendanceKind.MONTHLY, record_date=first_of_month,
                value=rng.randint(*att_range), note=None,
            ))

        checklist_base = {"top": (85, 95), "mid": (70, 88), "risk": (50, 65)}[seg]
        db.add(models.AttitudeReview(
            user_id=student.id, reviewer_id=teachers[i % 2].id,
            checklist={k: rng.randint(*checklist_base) for k in CHECKLIST_KEYS},
            note="真面目に取り組んでいます。" if seg != "risk" else "遅刻が増えています。要面談。",
            created_at=start + timedelta(days=30),
        ))

    db.commit()

    return {
        "organizations": 2,
        "teachers": len(teachers),
        "admins": 1,
        "students": len(students),
        "content_items": len(items),
        "risk_student_email": students[RISK_INDEX].email,
        "demo_student_email": students[0].email,
        "teacher_email": teachers[0].email,
        "admin_email": admin.email,
    }
