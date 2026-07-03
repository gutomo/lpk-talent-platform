"""ドリル問題の下書き生成CLI（Claude → review_flag=True で保存）。

生成した問題案はレビュー待ちとして保存され、approve するまで出題されない。

使い方（backendディレクトリから）:
    uv run python ../scripts/quiz/generate_quiz_drafts.py generate --section grammar --count 5
    uv run python ../scripts/quiz/generate_quiz_drafts.py generate --section listening \
        --level JFT-Basic --topic 介護のしごと
    uv run python ../scripts/quiz/generate_quiz_drafts.py list
    uv run python ../scripts/quiz/generate_quiz_drafts.py approve --ids 113 114
"""

import argparse
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend"))

from app.db import SessionLocal  # noqa: E402
from app.models import QuizItem  # noqa: E402
from app.models.enums import QuizSection  # noqa: E402
from app.services.quiz_gen import (  # noqa: E402
    VALID_LEVELS,
    approve_items,
    generate_drafts,
    list_pending,
    save_drafts,
)

MARKS = ["A", "B", "C", "D"]


def print_item(item: QuizItem) -> None:
    print(f"[{item.id}] ({item.section.value} / {item.level}) {item.question}")
    if item.meta.get("passage_ja"):
        print(f"    本文: {item.meta['passage_ja']}")
    if item.meta.get("script_ja"):
        print(f"    スクリプト: {item.meta['script_ja']}")
    for i, choice in enumerate(item.choices):
        mark = "*" if i == item.answer_index else " "
        print(f"   {mark}{MARKS[i]}. {choice}")
    print(f"    解説(id): {item.explanation_id}")


def cmd_generate(args: argparse.Namespace) -> None:
    section = QuizSection(args.section)
    drafts = generate_drafts(section, args.count, level=args.level, topic_ja=args.topic)
    with SessionLocal() as db:
        items = save_drafts(db, section, args.level, drafts, topic_ja=args.topic)
        db.commit()
        print(f"saved {len(items)} drafts (review_flag=True, 出題対象外):")
        for item in items:
            print_item(item)
    print("レビュー後に approve --ids <ID...> で出題対象にしてください。")


def cmd_list(_args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        items = list_pending(db)
        if not items:
            print("レビュー待ちの下書きはありません。")
            return
        print(f"レビュー待ち {len(items)} 件:")
        for item in items:
            print_item(item)


def cmd_approve(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        items = approve_items(db, args.ids)
        db.commit()
        print(f"approved {len(items)} items（出題対象になりました）: {[i.id for i in items]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate / review quiz item drafts")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Claudeで問題案を生成しレビュー待ちで保存する")
    gen.add_argument("--section", required=True, choices=[s.value for s in QuizSection])
    gen.add_argument("--count", type=int, default=5)
    gen.add_argument("--level", default="N4", choices=VALID_LEVELS)
    gen.add_argument("--topic", default=None, help="題材の指定（例: 介護のしごと）")
    gen.set_defaults(func=cmd_generate)

    lst = sub.add_parser("list", help="レビュー待ちの下書きを表示する")
    lst.set_defaults(func=cmd_list)

    apr = sub.add_parser("approve", help="レビュー済みの下書きを承認して出題対象にする")
    apr.add_argument("--ids", type=int, nargs="+", required=True)
    apr.set_defaults(func=cmd_approve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
