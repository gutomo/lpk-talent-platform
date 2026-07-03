"""ドリル問題の下書き生成サービス（BUILD_PLAN Phase 3：問題生成スクリプト）。

llm_provider_mode=stub: prompts/quiz_gen_v1.py の雛形を連番で複製する決定的モック。
llm_provider_mode=bedrock: Amazon Bedrock の Claude（Sonnet）。draft_items ツールの
toolChoice 強制で構造化 JSON を得る。

生成した下書きは必ず review_flag=True で保存する。人間が approve_items で承認するまで
デイリークイズ・模試には出題されない（出題側は review_flag=False のみ選ぶ）。
"""

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import QuizItem
from app.models.enums import QuizSection
from app.prompts.quiz_gen_v1 import (
    PROMPT_VERSION,
    SECTION_RULES,
    STUB_DRAFTS,
    SYSTEM_TEMPLATE,
)

__all__ = [
    "PROMPT_VERSION",
    "VALID_LEVELS",
    "LlmProviderError",
    "approve_items",
    "generate_drafts",
    "list_pending",
    "save_drafts",
    "validate_draft",
]

VALID_LEVELS = ("N4", "JFT-Basic")

_BEDROCK_MAX_TOKENS = 4000

_DRAFT_FIELDS = {
    "question": {"type": "string", "description": "設問文（やさしい日本語）"},
    "choices": {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 4,
        "maxItems": 4,
        "description": "選択肢4つ。重複禁止、正解は1つだけ。",
    },
    "answer_index": {"type": "integer", "description": "正解の位置（0〜3）"},
    "explanation_id": {"type": "string", "description": "インドネシア語の解説（1〜2文）"},
    "passage_ja": {"type": "string", "description": "読解のみ：本文（3〜6文）"},
    "script_ja": {"type": "string", "description": "聴解のみ：音声スクリプト（2〜4文）"},
}

# Converse API の draft_items ツール入力スキーマ。下書き JSON の形をここで強制する。
_DRAFT_TOOL = {
    "toolSpec": {
        "name": "draft_items",
        "description": "ドリル問題の下書きを構造化して返す。",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": _DRAFT_FIELDS,
                            "required": ["question", "choices", "answer_index", "explanation_id"],
                        },
                    }
                },
                "required": ["items"],
            }
        },
    }
}


class LlmProviderError(Exception):
    """LLMプロバイダ呼び出しの失敗（設定不備・ネットワーク・応答形式エラー）。"""


def generate_drafts(
    section: QuizSection, count: int, level: str = "N4", topic_ja: str | None = None
) -> list[dict[str, Any]]:
    """問題の下書きを count 件生成する。

    返り値: [{question, choices, answer_index, explanation_id, passage_ja?, script_ja?}]
    形式チェック済み（validate_draft を通過したもののみ）。内容の正しさは保証しないので、
    保存後に必ず人間レビュー（approve_items）を通すこと。
    """
    if level not in VALID_LEVELS:
        raise ValueError(f"level は {VALID_LEVELS} のいずれか: {level}")
    settings = get_settings()
    if settings.llm_provider_mode == "bedrock":
        drafts = _generate_bedrock(section, count, level, topic_ja, settings)
    else:
        drafts = _generate_stub(section, count)
    bad = [(d, problems) for d in drafts if (problems := validate_draft(section, d))]
    if bad:
        detail = "; ".join(f"{d.get('question', '?')!r}: {p}" for d, p in bad[:3])
        raise LlmProviderError(f"形式不正の下書きが {len(bad)} 件: {detail}")
    return drafts


def _generate_stub(section: QuizSection, count: int) -> list[dict[str, Any]]:
    base = STUB_DRAFTS[section.value]
    drafts = []
    for n in range(1, count + 1):
        draft = copy.deepcopy(base)
        # 連番を付けて設問を一意にする（保存・レビューの動作確認用）。
        draft["question"] = f"（下書き{n}）{draft['question']}"
        drafts.append(draft)
    return drafts


def _generate_bedrock(
    section: QuizSection,
    count: int,
    level: str,
    topic_ja: str | None,
    settings: Settings,
) -> list[dict[str, Any]]:
    import boto3  # stub モードでは不要なため遅延 import
    from botocore.exceptions import BotoCoreError, ClientError

    system = SYSTEM_TEMPLATE.format(
        count=count,
        level=level,
        section=section.value,
        section_rules=SECTION_RULES[section.value],
    )
    user_text = f"{section.value} の問題案を {count} 問作ってください。"
    if topic_ja:
        user_text += f" 題材：{topic_ja}"
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    try:
        resp = client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            # 実装ルールの temperature 0.2 は評価用。下書き生成は多様性を優先し、
            # 内容の担保は人間レビュー（review_flag）側で行う。
            inferenceConfig={"temperature": 0.7, "maxTokens": _BEDROCK_MAX_TOKENS},
            toolConfig={
                "tools": [_DRAFT_TOOL],
                "toolChoice": {"tool": {"name": "draft_items"}},
            },
        )
    except (BotoCoreError, ClientError) as exc:
        raise LlmProviderError(f"Bedrock を呼び出せません: {exc}") from exc
    return parse_drafts_response(resp)


def parse_drafts_response(resp: dict[str, Any]) -> list[dict[str, Any]]:
    """Converse 応答から draft_items ツール入力を取り出して検証する。"""
    content = resp.get("output", {}).get("message", {}).get("content", [])
    for block in content:
        tool_use = block.get("toolUse")
        if tool_use is not None and tool_use.get("name") == "draft_items":
            items = (tool_use.get("input") or {}).get("items")
            if not isinstance(items, list) or not items:
                raise LlmProviderError("draft_items の items が空です")
            return items
    raise LlmProviderError("応答に draft_items ツール呼び出しが含まれていません")


def validate_draft(section: QuizSection, draft: dict[str, Any]) -> list[str]:
    """下書き1件の形式チェック。問題点のリストを返す（空なら合格）。"""
    problems = []
    question = draft.get("question")
    if not isinstance(question, str) or not question.strip():
        problems.append("question が空")
    choices = draft.get("choices")
    if not isinstance(choices, list) or len(choices) != 4:
        problems.append("choices は4つ必要")
    elif any(not isinstance(c, str) or not c.strip() for c in choices):
        problems.append("choices に空の選択肢がある")
    elif len(set(choices)) != 4:
        problems.append("choices が重複")
    answer_index = draft.get("answer_index")
    if not isinstance(answer_index, int) or not 0 <= answer_index < 4:
        problems.append("answer_index が範囲外")
    explanation = draft.get("explanation_id")
    if not isinstance(explanation, str) or not explanation.strip():
        problems.append("explanation_id（インドネシア語解説）が空")
    if section == QuizSection.READING and not str(draft.get("passage_ja") or "").strip():
        problems.append("読解に passage_ja が無い")
    if section == QuizSection.LISTENING and not str(draft.get("script_ja") or "").strip():
        problems.append("聴解に script_ja が無い")
    return problems


def save_drafts(
    db: Session,
    section: QuizSection,
    level: str,
    drafts: list[dict[str, Any]],
    topic_ja: str | None = None,
) -> list[QuizItem]:
    """下書きを review_flag=True（レビュー待ち）で quiz_items に保存する。"""
    items = []
    for draft in drafts:
        problems = validate_draft(section, draft)
        if problems:
            raise ValueError(f"下書きが形式不正: {problems} / {draft.get('question')!r}")
        meta: dict[str, Any] = {"source": "llm-draft", "prompt_version": PROMPT_VERSION}
        if topic_ja:
            meta["topic_ja"] = topic_ja
        if draft.get("passage_ja"):
            meta["passage_ja"] = draft["passage_ja"]
        if draft.get("script_ja"):
            meta["script_ja"] = draft["script_ja"]
        items.append(
            QuizItem(
                section=section,
                level=level,
                question=draft["question"],
                choices=draft["choices"],
                answer_index=draft["answer_index"],
                explanation_id=draft["explanation_id"],
                review_flag=True,
                meta=meta,
            )
        )
    db.add_all(items)
    db.flush()
    return items


def list_pending(db: Session) -> list[QuizItem]:
    """レビュー待ち（review_flag=True）の問題を古い順に返す。"""
    return list(
        db.execute(
            select(QuizItem).where(QuizItem.review_flag.is_(True)).order_by(QuizItem.id)
        ).scalars()
    )


def approve_items(db: Session, item_ids: list[int]) -> list[QuizItem]:
    """人間レビュー済みの問題を承認し（review_flag=False）、出題対象にする。"""
    items = list(
        db.execute(
            select(QuizItem).where(QuizItem.id.in_(item_ids), QuizItem.review_flag.is_(True))
        ).scalars()
    )
    found = {i.id for i in items}
    missing = [i for i in item_ids if i not in found]
    if missing:
        raise ValueError(f"レビュー待ちの問題が見つかりません: {missing}")
    for item in items:
        item.review_flag = False
    db.flush()
    return items
