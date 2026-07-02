"""AI会話練習サービス。

llm_provider_mode=stub: シナリオ台本（prompts/conversation_v1.py）を順に返す決定的モック。
llm_provider_mode=bedrock: Amazon Bedrock の Claude（Sonnet）。temperature 0.2、
reply ツールの toolChoice 強制で構造化 JSON を得る（実装ルール：LLM評価はJSON強制）。

Bedrock はクロスクラウド呼び出しなのでターン制のみ（地雷：リアルタイム双方向は狙わない）。
"""

from typing import Any

from app.config import Settings, get_settings
from app.models.enums import ConversationRole
from app.prompts.conversation_v1 import PROMPT_VERSION, SCENARIOS, SYSTEM_TEMPLATE

__all__ = ["PROMPT_VERSION", "SCENARIOS", "LlmProviderError", "generate_reply"]

_BEDROCK_MAX_TOKENS = 400

# Converse API の reply ツール入力スキーマ。返答 JSON の形をここで強制する。
_REPLY_TOOL = {
    "toolSpec": {
        "name": "reply",
        "description": "会話練習の次の返答を構造化して返す。",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "reply_ja": {
                        "type": "string",
                        "description": "やさしい日本語の返答（2文以内）",
                    },
                    "reply_furigana": {
                        "type": "string",
                        "description": "reply_ja 全文のひらがな",
                    },
                    "hint_id": {
                        "type": "string",
                        "description": "次に言うことのヒント（インドネシア語）",
                    },
                    "done": {"type": "boolean", "description": "会話を締めたら true"},
                },
                "required": ["reply_ja", "reply_furigana", "hint_id", "done"],
            }
        },
    }
}


class LlmProviderError(Exception):
    """LLMプロバイダ呼び出しの失敗（設定不備・ネットワーク・応答形式エラー）。"""


def generate_reply(
    scenario_key: str,
    history: list[tuple[ConversationRole, str]],
    student_turns: int,
) -> dict[str, Any]:
    """学生の発話を受けた次のAI返答を返す。

    history は開幕からの全ターン（最後は学生の発話）。
    返り値: {reply_ja, reply_furigana, hint_id, done}
    """
    settings = get_settings()
    scenario = SCENARIOS[scenario_key]
    if settings.llm_provider_mode == "bedrock":
        result = _reply_bedrock(scenario, history, student_turns, settings)
    else:
        result = _reply_stub(scenario, student_turns)
    # 打ち切りはサーバ側でも保証する（LLMの done 判断には依存しない）。
    if student_turns >= scenario["max_student_turns"]:
        result["done"] = True
    return result


def _reply_stub(scenario: dict[str, Any], student_turns: int) -> dict[str, Any]:
    replies = scenario["stub_replies"]
    turn = replies[min(student_turns, len(replies)) - 1]
    return {
        "reply_ja": turn["text_ja"],
        "reply_furigana": turn["furigana"],
        "hint_id": turn["hint_id"],
        "done": student_turns >= scenario["max_student_turns"],
    }


def _reply_bedrock(
    scenario: dict[str, Any],
    history: list[tuple[ConversationRole, str]],
    student_turns: int,
    settings: Settings,
) -> dict[str, Any]:
    import boto3  # stub モードでは不要なため遅延 import
    from botocore.exceptions import BotoCoreError, ClientError

    system = SYSTEM_TEMPLATE.format(
        student_turns=student_turns,
        max_turns=scenario["max_student_turns"],
        situation_ja=scenario["situation_ja"],
        ai_role=scenario["ai_role"],
    )
    messages = [
        {
            "role": "assistant" if role == ConversationRole.PARTNER else "user",
            "content": [{"text": text_ja}],
        }
        for role, text_ja in history
    ]
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    try:
        resp = client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": system}],
            messages=messages,
            inferenceConfig={"temperature": 0.2, "maxTokens": _BEDROCK_MAX_TOKENS},
            toolConfig={"tools": [_REPLY_TOOL], "toolChoice": {"tool": {"name": "reply"}}},
        )
    except (BotoCoreError, ClientError) as exc:
        raise LlmProviderError(f"Bedrock を呼び出せません: {exc}") from exc
    return parse_converse_response(resp)


def parse_converse_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Converse 応答から reply ツール入力を取り出して検証する。"""
    content = resp.get("output", {}).get("message", {}).get("content", [])
    for block in content:
        tool_use = block.get("toolUse")
        if tool_use is not None and tool_use.get("name") == "reply":
            data = tool_use.get("input") or {}
            keys = ("reply_ja", "reply_furigana", "hint_id", "done")
            missing = [k for k in keys if k not in data]
            if missing:
                raise LlmProviderError(f"reply ツール入力に欠落キー: {missing}")
            return {
                "reply_ja": str(data["reply_ja"]),
                "reply_furigana": str(data["reply_furigana"]),
                "hint_id": str(data["hint_id"]),
                "done": bool(data["done"]),
            }
    raise LlmProviderError("応答に reply ツール呼び出しが含まれていません")
