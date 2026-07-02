"""AI会話練習のシナリオ定義とプロンプト（版管理対象）。

3シナリオ：自己紹介 / 職場会話 / 報連相。学生レベルは A2/N4。
- stub_replies は llm_provider_mode=stub 用の決定的な台本。学生の発話回数 n に対して
  stub_replies[n-1] を返し、最後の要素が締めの一言（done=True）になる。
- 台本・例文は完全オリジナル（JLPT/JFT の過去問・公式問題は使わない）。
"""

from typing import Any

PROMPT_VERSION = "conversation-v1"

# Bedrock（Claude）用の共通システムプロンプト。JSON は reply ツールで強制する。
SYSTEM_TEMPLATE = """\
あなたはインドネシア人学生の日本語会話練習の相手です。学生のレベルは A2〜N4 です。
次のルールを必ず守ってください。
- あなたの返答（reply_ja）は、やさしい日本語で2文以内。難しい漢語や敬語は避ける。
- 学生の間違いは指摘せず、正しい言い方をさりげなく自分の返答に含める。
- reply_furigana には reply_ja の全文をひらがなで入れる。
- hint_id には、学生が次に何と答えればよいかのヒントをインドネシア語で1文入れる。
- ここまでの学生の発話回数は {student_turns} 回。{max_turns} 回に達したら、
  会話をお礼で自然に締めくくり、done を true にする。それまでは false にする。
- 必ず reply ツールを使って構造化された JSON で返答する。

シナリオ：{situation_ja}
あなたの役：{ai_role}
"""


def _turn(text_ja: str, furigana: str, hint_id: str) -> dict[str, str]:
    return {"text_ja": text_ja, "furigana": furigana, "hint_id": hint_id}


SCENARIOS: dict[str, dict[str, Any]] = {
    "self_intro": {
        "title_ja": "自己紹介",
        "title_id": "Perkenalan diri",
        "description_id": "Berlatih memperkenalkan diri kepada senior di tempat kerja.",
        "level": "A2",
        "max_student_turns": 4,
        "ai_role": "職場で初めて会う先輩職員の田中さん",
        "situation_ja": "職場の休憩室。先輩職員の田中が、新しく来た学生に初めて話しかける。",
        "opening": _turn(
            "はじめまして。田中です。お名前を教えてください。",
            "はじめまして。たなかです。おなまえをおしえてください。",
            "Sebutkan nama Anda. Contoh: 「（nama）と申します。よろしくお願いします。」",
        ),
        "stub_replies": [
            _turn(
                "いい名前ですね。お国はどちらですか。",
                "いいなまえですね。おくにはどちらですか。",
                "Sebutkan asal negara Anda. Contoh: 「インドネシアから来ました。」",
            ),
            _turn(
                "インドネシアですか。日本の生活はどうですか。",
                "いんどねしあですか。にほんのせいかつはどうですか。",
                "Ceritakan kesan Anda tentang kehidupan di Jepang dengan sederhana.",
            ),
            _turn(
                "そうですか。休みの日は何をしますか。",
                "そうですか。やすみのひはなにをしますか。",
                "Ceritakan kegiatan Anda di hari libur. Contoh: 「日本語を勉強します。」",
            ),
            _turn(
                "いいですね。これから一緒にがんばりましょう。今日は話せてよかったです。",
                "いいですね。これからいっしょにがんばりましょう。きょうははなせてよかったです。",
                "Percakapan selesai. Akhiri dengan salam. Contoh: 「よろしくお願いします。」",
            ),
        ],
    },
    "workplace_talk": {
        "title_ja": "職場会話",
        "title_id": "Percakapan di tempat kerja",
        "description_id": "Berlatih menerima instruksi kerja pagi hari dari senior.",
        "level": "A2",
        "max_student_turns": 4,
        "ai_role": "朝の申し送りをする先輩職員",
        "situation_ja": "介護施設の朝。先輩職員が学生に今日の仕事の指示を出す。",
        "opening": _turn(
            "おはようございます。今日は忙しいですよ。準備はいいですか。",
            "おはようございます。きょうはいそがしいですよ。じゅんびはいいですか。",
            "Jawab salam dan katakan Anda siap. Contoh: 「おはようございます。はい、大丈夫です。」",
        ),
        "stub_replies": [
            _turn(
                "いいですね。まず、山田さんの部屋の掃除をお願いします。",
                "いいですね。まず、やまださんのへやのそうじをおねがいします。",
                "Terima instruksi itu. Contoh: 「はい、わかりました。」",
            ),
            _turn(
                "ありがとうございます。終わったら、私に教えてください。",
                "ありがとうございます。おわったら、わたしにおしえてください。",
                "Katakan Anda akan melapor setelah selesai. Contoh: 「終わったら報告します。」",
            ),
            _turn(
                "お疲れさまでした。次は昼ごはんの準備を手伝ってください。",
                "おつかれさまでした。つぎはひるごはんのじゅんびをてつだってください。",
                "Terima tugas berikutnya. Contoh: 「はい、手伝います。」",
            ),
            _turn(
                "助かりました。午後もよろしくお願いします。",
                "たすかりました。ごごもよろしくおねがいします。",
                "Percakapan selesai. Contoh: 「こちらこそ、よろしくお願いします。」",
            ),
        ],
    },
    "hourensou": {
        "title_ja": "報連相（報告・連絡・相談）",
        "title_id": "Hourensou (lapor, informasikan, konsultasi)",
        "description_id": "Berlatih melaporkan masalah kepada pemimpin dan berkonsultasi.",
        "level": "A2",
        "max_student_turns": 4,
        "ai_role": "話を聞いてくれる職場のリーダー",
        "situation_ja": "職場で学生が困ったことに気づき、リーダーに報告・相談する。",
        "opening": _turn(
            "お疲れさまです。何かありましたか。",
            "おつかれさまです。なにかありましたか。",
            "Laporkan masalah yang Anda temukan. Contoh: 「すみません、報告があります。」",
        ),
        "stub_replies": [
            _turn(
                "報告ありがとうございます。それはいつ気づきましたか。",
                "ほうこくありがとうございます。それはいつきづきましたか。",
                "Katakan kapan Anda menyadarinya. Contoh: 「さっき気づきました。」",
            ),
            _turn(
                "わかりました。ほかに困っていることはありますか。",
                "わかりました。ほかにこまっていることはありますか。",
                "Sampaikan hal lain yang membuat Anda bingung, atau katakan tidak ada.",
            ),
            _turn(
                "そうですか。では、あとで一緒に確認しましょう。",
                "そうですか。では、あとでいっしょにかくにんしましょう。",
                "Setujui ajakan itu. Contoh: 「はい、お願いします。」",
            ),
            _turn(
                "すぐに知らせてくれて助かりました。何かあったら、また相談してくださいね。",
                "すぐにしらせてくれてたすかりました。なにかあったら、またそうだんしてくださいね。",
                "Percakapan selesai. Contoh: 「ありがとうございます。失礼します。」",
            ),
        ],
    },
}
