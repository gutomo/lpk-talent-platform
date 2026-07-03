"""デモ用seed投入CLI。

使い方（backendディレクトリから）:
    uv run python ../scripts/seed/seed_demo.py           # 空DBに投入
    uv run python ../scripts/seed/seed_demo.py --reset   # 全消しして再投入
"""

import argparse
import os
import sys
from datetime import UTC, datetime

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend"))

from app.db import SessionLocal  # noqa: E402
from app.seed import (  # noqa: E402
    ADMIN_PASSWORD,
    STUDENT_PASSWORD,
    TEACHER_PASSWORD,
    reset_all,
    seed_all,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--reset", action="store_true", help="delete all rows before seeding")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.reset:
            reset_all(db)
        summary = seed_all(db, now=datetime.now(UTC))

    print("seeded:")
    for key in ("organizations", "teachers", "admins", "students", "content_items", "quiz_items"):
        print(f"  {key}: {summary[key]}")
    print("demo accounts:")
    print(f"  student: {summary['demo_student_email']} / {STUDENT_PASSWORD}")
    print(f"  teacher: {summary['teacher_email']} / {TEACHER_PASSWORD}")
    print(f"  admin:   {summary['admin_email']} / {ADMIN_PASSWORD}")
    print(f"  risk student: {summary['risk_student_email']}")


if __name__ == "__main__":
    main()
