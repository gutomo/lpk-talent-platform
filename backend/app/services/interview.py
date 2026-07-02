"""面接ロールプレイサービス（テキストモード）。

llm_provider_mode=stub: 質問台本（prompts/interview_v1.py）を順に返し、評価は文字起こしの
特徴量（回答の長さ・です/ます・報連相語彙）から決定的に算出する。資格情報不要でテスト可能。
llm_provider_mode=bedrock: Amazon Bedrock の Claude（Sonnet）。temperature 0.2、
ツールの toolChoice 強制で構造化 JSON を得る（実装ルール：LLM評価はJSON強制）。

Bedrock はクロスクラウド呼び出しなのでターン制のみ（地雷：リアルタイム双方向は狙わない）。
総合スコアはLLMに計算させず、サーバ側で5軸の単純平均から算出する。
"""

from typing import Any

from app.config import Settings, get_settings
from app.models.enums import TurnRole
from app.prompts.interview_v1 import (
    EVALUATION_SYSTEM_TEMPLATE,
    INTERVIEWER_SYSTEM_TEMPLATE,
    PROMPT_VERSION,
    RUBRIC_AXES,
    RUBRIC_VERSION,
    SCENARIOS,
)

__all__ = [
    "PROMPT_VERSION",
    "RUBRIC_AXES",
    "RUBRIC_VERSION",
    "SCENARIOS",
    "LlmProviderError",
    "compute_total",
    "evaluate_interview",
    "generate_question",
    "parse_ask_response",
    "parse_evaluate_response",
]

_BEDROCK_MAX_TOKENS_ASK = 400
_BEDROCK_MAX_TOKENS_EVAL = 1200

# Converse API の ask ツール入力スキーマ。面接官の次の発話の形をここで強制する。
_ASK_TOOL = {
    "toolSpec": {
        "name": "ask",
        "description": "面接官の次の発話を構造化して返す。",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "question_ja": {
                        "type": "string",
                        "description": "面接官の次の発話（丁寧な日本語、2文以内）",
                    },
                    "furigana": {
                        "type": "string",
                        "description": "question_ja 全文のひらがな",
                    },
                    "hint_id": {
                        "type": "string",
                        "description": "答え方のヒント（インドネシア語）",
                    },
                    "done": {"type": "boolean", "description": "面接を締めたら true"},
                },
                "required": ["question_ja", "furigana", "hint_id", "done"],
            }
        },
    }
}

# Converse API の evaluate ツール入力スキーマ。ルーブリック評価の形をここで強制する。
_EVALUATE_TOOL = {
    "toolSpec": {
        "name": "evaluate",
        "description": "面接のルーブリック評価を構造化して返す。",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "scores": {
                        "type": "object",
                        "properties": {
                            axis: {"type": "integer", "description": meta["label_ja"]}
                            for axis, meta in RUBRIC_AXES.items()
                        },
                        "required": list(RUBRIC_AXES),
                    },
                    "summary_id": {
                        "type": "string",
                        "description": "総評（インドネシア語、2文以内）",
                    },
                    "summary_ja": {
                        "type": "string",
                        "description": "summary_id と同じ内容の日本語要約",
                    },
                    "advice_id": {
                        "type": "string",
                        "description": "次の練習への助言（インドネシア語、2文以内）",
                    },
                    "model_answers": {
                        "type": "array",
                        "description": "弱かった質問への日本語の模範解答例（2〜3個）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_ja": {"type": "string"},
                                "answer_ja": {"type": "string"},
                            },
                            "required": ["question_ja", "answer_ja"],
                        },
                    },
                },
                "required": [
                    "scores",
                    "summary_id",
                    "summary_ja",
                    "advice_id",
                    "model_answers",
                ],
            }
        },
    }
}

_HOURENSOU_WORDS = ("報告", "連絡", "相談", "確認", "ほうこく", "れんらく", "そうだん", "かくにん")
_POLITE_MARKERS = ("です", "ます", "ました", "ません", "ください", "お願い")


class LlmProviderError(Exception):
    """LLMプロバイダ呼び出しの失敗（設定不備・ネットワーク・応答形式エラー）。"""


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def compute_total(scores: dict[str, int]) -> int:
    """総合0〜100。5軸の単純平均（LLMの算術には依存しない）。"""
    return _clamp(sum(scores[axis] for axis in RUBRIC_AXES) / len(RUBRIC_AXES))


def generate_question(
    scenario_key: str,
    history: list[tuple[TurnRole, str]],
    candidate_turns: int,
) -> dict[str, Any]:
    """学生の回答を受けた面接官の次の発話を返す。

    history は開幕からの全ターン（最後は学生の回答）。
    返り値: {question_ja, furigana, hint_id, done}
    """
    settings = get_settings()
    scenario = SCENARIOS[scenario_key]
    if settings.llm_provider_mode == "bedrock":
        result = _ask_bedrock(scenario, history, candidate_turns, settings)
    else:
        result = _ask_stub(scenario, candidate_turns)
    # 打ち切りはサーバ側でも保証する（LLMの done 判断には依存しない）。
    if candidate_turns >= scenario["max_candidate_turns"]:
        result["done"] = True
    return result


def evaluate_interview(
    scenario_key: str, history: list[tuple[TurnRole, str]]
) -> dict[str, Any]:
    """完走した面接をルーブリックで評価する。

    返り値: {scores: {axis: 0-100}, total: 0-100,
             feedback: {id, ja, advice_id, model_answers}}
    feedback["id"] / ["ja"] のキーは seed 由来の評価行と互換にする。
    """
    settings = get_settings()
    scenario = SCENARIOS[scenario_key]
    if settings.llm_provider_mode == "bedrock":
        result = _evaluate_bedrock(scenario, history, settings)
    else:
        result = _evaluate_stub(scenario, history)
    result["total"] = compute_total(result["scores"])
    return result


# ------------------------------------------------------------------ stub

def _ask_stub(scenario: dict[str, Any], candidate_turns: int) -> dict[str, Any]:
    questions = scenario["stub_questions"]
    turn = questions[min(candidate_turns, len(questions)) - 1]
    return {
        "question_ja": turn["text_ja"],
        "furigana": turn["furigana"],
        "hint_id": turn["hint_id"],
        "done": candidate_turns >= scenario["max_candidate_turns"],
    }


def _evaluate_stub(
    scenario: dict[str, Any], history: list[tuple[TurnRole, str]]
) -> dict[str, Any]:
    answers = [text for role, text in history if role == TurnRole.CANDIDATE] or [""]
    avg_len = sum(len(a) for a in answers) / len(answers)
    length_pts = min(avg_len, 30.0) / 30.0 * 15.0
    polite_ratio = sum(
        1 for a in answers if any(m in a for m in _POLITE_MARKERS)
    ) / len(answers)
    hourensou_hit = any(w in a for a in answers for w in _HOURENSOU_WORDS)
    base = 55.0 + length_pts
    return {
        "scores": {
            "japanese": _clamp(base + polite_ratio * 8),
            "consistency": _clamp(base),
            "keigo": _clamp(48 + polite_ratio * 45),
            "hourensou": _clamp(base + (12 if hourensou_hit else -5)),
            "clarity": _clamp(base + 4),
        },
        "feedback": {
            "id": "Anda menyelesaikan wawancara sampai akhir. "
            "Jawaban Anda singkat tetapi mudah dipahami.",
            "ja": "面接を最後まで完走しました。回答は短いですが、伝わる内容でした。",
            "advice_id": "Gunakan bentuk sopan (desu/masu) secara konsisten, dan tambahkan "
            "kata seperti 「報告します」 saat menjelaskan masalah.",
            "model_answers": scenario["model_answers"],
        },
    }


# ------------------------------------------------------------------ bedrock

def _converse(
    settings: Settings,
    system: str,
    messages: list[dict[str, Any]],
    tool: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    import boto3  # stub モードでは不要なため遅延 import
    from botocore.exceptions import BotoCoreError, ClientError

    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    tool_name = tool["toolSpec"]["name"]
    try:
        return client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": system}],
            messages=messages,
            inferenceConfig={"temperature": 0.2, "maxTokens": max_tokens},
            toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": tool_name}}},
        )
    except (BotoCoreError, ClientError) as exc:
        raise LlmProviderError(f"Bedrock を呼び出せません: {exc}") from exc


def _ask_bedrock(
    scenario: dict[str, Any],
    history: list[tuple[TurnRole, str]],
    candidate_turns: int,
    settings: Settings,
) -> dict[str, Any]:
    system = INTERVIEWER_SYSTEM_TEMPLATE.format(
        company_ja=scenario["company_ja"],
        interviewer_ja=scenario["interviewer_ja"],
        candidate_turns=candidate_turns,
        max_turns=scenario["max_candidate_turns"],
    )
    messages = [
        {
            "role": "assistant" if role == TurnRole.INTERVIEWER else "user",
            "content": [{"text": text_ja}],
        }
        for role, text_ja in history
    ]
    resp = _converse(settings, system, messages, _ASK_TOOL, _BEDROCK_MAX_TOKENS_ASK)
    return parse_ask_response(resp)


def _transcript_ja(history: list[tuple[TurnRole, str]]) -> str:
    label = {TurnRole.INTERVIEWER: "面接官", TurnRole.CANDIDATE: "学生"}
    return "\n".join(f"{label[role]}: {text_ja}" for role, text_ja in history)


def _evaluate_bedrock(
    scenario: dict[str, Any],
    history: list[tuple[TurnRole, str]],
    settings: Settings,
) -> dict[str, Any]:
    system = EVALUATION_SYSTEM_TEMPLATE.format(company_ja=scenario["company_ja"])
    prompt = "次の面接の文字起こしを評価してください。\n\n" + _transcript_ja(history)
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    resp = _converse(settings, system, messages, _EVALUATE_TOOL, _BEDROCK_MAX_TOKENS_EVAL)
    return parse_evaluate_response(resp)


def _tool_input(resp: dict[str, Any], tool_name: str) -> dict[str, Any]:
    content = resp.get("output", {}).get("message", {}).get("content", [])
    for block in content:
        tool_use = block.get("toolUse")
        if tool_use is not None and tool_use.get("name") == tool_name:
            return tool_use.get("input") or {}
    raise LlmProviderError(f"応答に {tool_name} ツール呼び出しが含まれていません")


def parse_ask_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Converse 応答から ask ツール入力を取り出して検証する。"""
    data = _tool_input(resp, "ask")
    keys = ("question_ja", "furigana", "hint_id", "done")
    missing = [k for k in keys if k not in data]
    if missing:
        raise LlmProviderError(f"ask ツール入力に欠落キー: {missing}")
    return {
        "question_ja": str(data["question_ja"]),
        "furigana": str(data["furigana"]),
        "hint_id": str(data["hint_id"]),
        "done": bool(data["done"]),
    }


def parse_evaluate_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Converse 応答から evaluate ツール入力を取り出し、スコアを0〜100に正規化する。"""
    data = _tool_input(resp, "evaluate")
    keys = ("scores", "summary_id", "summary_ja", "advice_id", "model_answers")
    missing = [k for k in keys if k not in data]
    if missing:
        raise LlmProviderError(f"evaluate ツール入力に欠落キー: {missing}")

    raw_scores = data["scores"] or {}
    scores: dict[str, int] = {}
    for axis in RUBRIC_AXES:
        if axis not in raw_scores:
            raise LlmProviderError(f"evaluate の scores に軸がありません: {axis}")
        try:
            scores[axis] = _clamp(float(raw_scores[axis]))
        except (TypeError, ValueError) as exc:
            raise LlmProviderError(f"evaluate の scores.{axis} が数値ではありません") from exc

    model_answers = [
        {"question_ja": str(m["question_ja"]), "answer_ja": str(m["answer_ja"])}
        for m in data["model_answers"]
        if isinstance(m, dict) and "question_ja" in m and "answer_ja" in m
    ]
    return {
        "scores": scores,
        "feedback": {
            "id": str(data["summary_id"]),
            "ja": str(data["summary_ja"]),
            "advice_id": str(data["advice_id"]),
            "model_answers": model_answers,
        },
    }
