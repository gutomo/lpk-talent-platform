"""N4 / JFT-Basic ドリルのデイリークイズ組成（簡易SRS）。

出題対象は人間レビュー済み（review_flag=False）の問題のみ。聴解は模試モード専用。
簡易SRSのルール:
  1. 直近の解答が誤答の問題を最優先で再出題する（古い誤答から、1回あたり上限あり）
  2. 未出題の問題（その日のシャッフル順）
  3. 正解済みの問題（解いてから時間が経った順）
選択とシャッフルは (user_id, 日付) を種にした乱数で決めるので、
同じ日に何度取得しても同じ10問が返る（途中でリロードしても続きから解ける）。
"""

import random
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuizAttempt, QuizItem
from app.models.enums import QuizSection

DAILY_QUIZ_SIZE = 10
# 誤答の再出題は1回の枠の半分まで。残りは新規・復習に回して学習が停滞しないようにする。
DAILY_WRONG_CAP = 5


def latest_attempts(db: Session, user_id: int) -> dict[int, QuizAttempt]:
    """問題IDごとの最新解答。昇順で走査して上書きすると最後（最新）が残る。"""
    rows = db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.user_id == user_id)
        .order_by(QuizAttempt.created_at, QuizAttempt.id)
    ).scalars()
    return {a.item_id: a for a in rows}


def build_daily_quiz(
    db: Session, user_id: int, today: date
) -> tuple[list[QuizItem], set[int]]:
    """デイリークイズの問題リストと、再出題（誤答復習）の問題ID集合を返す。"""
    items = list(
        db.execute(
            select(QuizItem).where(
                QuizItem.review_flag.is_(False),
                QuizItem.section != QuizSection.LISTENING,
            )
        ).scalars()
    )
    latest = latest_attempts(db, user_id)

    wrong = [i for i in items if i.id in latest and not latest[i.id].is_correct]
    wrong.sort(key=lambda i: (latest[i.id].created_at, i.id))
    unseen = [i for i in items if i.id not in latest]
    answered_ok = [i for i in items if i.id in latest and latest[i.id].is_correct]
    answered_ok.sort(key=lambda i: (latest[i.id].created_at, i.id))

    rng = random.Random(f"{user_id}:{today.isoformat()}")
    rng.shuffle(unseen)

    picked = wrong[:DAILY_WRONG_CAP]
    for pool in (unseen, answered_ok, wrong[DAILY_WRONG_CAP:]):
        for item in pool:
            if len(picked) >= DAILY_QUIZ_SIZE:
                break
            picked.append(item)

    rng.shuffle(picked)
    wrong_ids = {i.id for i in wrong}
    review_ids = {i.id for i in picked if i.id in wrong_ids}
    return picked, review_ids


# 模試の構成（合計25問）。BUILD_PLAN Phase 3：模試モード25問、スコア換算。
MOCK_SECTION_COUNTS: dict[QuizSection, int] = {
    QuizSection.GRAMMAR: 8,
    QuizSection.VOCABULARY: 8,
    QuizSection.READING: 5,
    QuizSection.LISTENING: 4,
}
MOCK_NUM_QUESTIONS = sum(MOCK_SECTION_COUNTS.values())


def build_mock_exam(db: Session, rng: random.Random) -> list[QuizItem]:
    """模試25問をセクション構成どおりに無作為抽出する（文法→語彙→読解→聴解の順）。"""
    picked: list[QuizItem] = []
    for section, count in MOCK_SECTION_COUNTS.items():
        pool = list(
            db.execute(
                select(QuizItem).where(
                    QuizItem.review_flag.is_(False), QuizItem.section == section
                )
            ).scalars()
        )
        if len(pool) < count:
            raise ValueError(f"問題バンク不足: {section} は {count} 問必要（{len(pool)} 問）")
        picked.extend(rng.sample(pool, count))
    return picked


def score_from_correct(num_correct: int, num_questions: int) -> int:
    """正答数を0〜100スコアへ換算する（実装ルール：スコアは全て0〜100）。"""
    return round(100 * num_correct / num_questions)
