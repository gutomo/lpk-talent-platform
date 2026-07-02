"""面接ロールプレイのペルソナ・質問フロー・ルーブリック定義（版管理対象）。

3ペルソナ：介護 / 食品製造 / 外食（BUILD_PLAN Phase 2 の優先順）。企業名は全て架空。
質問フロー：自己紹介 → 志望理由 → 想定質問×2 → 逆質問 → 締め（学生5ターンで完走）。
- stub_questions は llm_provider_mode=stub 用の決定的な台本。学生の回答回数 n に対して
  stub_questions[n-1] を返し、最後の要素が締めの一言（done=True）になる。
- ルーブリック5軸のキーは seed の EVAL_AXES と同一（ダッシュボード集計を単純に保つ）。
"""

from typing import Any

PROMPT_VERSION = "interview-v1"
RUBRIC_VERSION = "interview-rubric-v1"

# 評価軸（順序も表示順として使う）。スコアは全て0〜100、総合は5軸の単純平均。
RUBRIC_AXES: dict[str, dict[str, str]] = {
    "japanese": {
        "label_ja": "日本語力",
        "description_ja": "語彙・文法の正確さ。A2〜N4学習者としての到達度で見る。",
    },
    "consistency": {
        "label_ja": "内容の一貫性",
        "description_ja": "質問の意図に合った回答か。話の筋が通っているか。",
    },
    "keigo": {
        "label_ja": "敬語・礼儀",
        "description_ja": "です・ます体の維持、面接にふさわしい言葉づかい。",
    },
    "hourensou": {
        "label_ja": "報連相",
        "description_ja": "報告・連絡・相談・確認の姿勢が回答に表れているか。",
    },
    "clarity": {
        "label_ja": "発話明瞭さ",
        "description_ja": "テキストモードでは文のわかりやすさ。"
        "音声モードでは発音スコアと連携する。",
    },
}

# Bedrock（Claude）用の面接官システムプロンプト。JSON は ask ツールで強制する。
INTERVIEWER_SYSTEM_TEMPLATE = """\
あなたは日本企業の採用面接官です。インドネシア人学生（日本語レベル A2〜N4）の模擬面接を行います。
企業設定：{company_ja}
あなたの役：{interviewer_ja}
次のルールを必ず守ってください。
- 質問（question_ja）は、面接らしい丁寧な日本語で2文以内。A2レベルでも理解できるやさしい言葉を選ぶ。
- 学生の日本語の間違いは指摘せず、面接を続ける。
- furigana には question_ja の全文をひらがなで入れる。
- hint_id には、学生がどう答えればよいかのヒントをインドネシア語で1文入れる。
- 質問フロー：1) 自己紹介（開始時の質問で済み） 2) 志望理由 3) 仕事に関する想定質問を2つ
  4) 逆質問（「何か質問はありますか」） 5) 締め。
- ここまでの学生の回答回数は {candidate_turns} 回。{max_turns} 回に達したら、学生の逆質問に
  短く答えてから面接をお礼で締めくくり、done を true にする。それまでは false にする。
- 必ず ask ツールを使って構造化された JSON で返答する。
"""

# Bedrock（Claude）用のルーブリック評価システムプロンプト。JSON は evaluate ツールで強制する。
EVALUATION_SYSTEM_TEMPLATE = """\
あなたは日本企業の採用面接の評価者です。インドネシア人学生（日本語レベル A2〜N4）の
模擬面接の文字起こしを読み、ルーブリックで採点します。
次のルールを必ず守ってください。
- 各軸のスコアは 0〜100 の整数。A2〜N4 学生の面接練習として採点する（ネイティブ基準にしない）。
- 軸の定義：
  japanese = 日本語力（語彙・文法の正確さ）
  consistency = 内容の一貫性（質問の意図に合った回答か）
  keigo = 敬語・礼儀（です・ます体、面接のマナー）
  hourensou = 報連相（報告・確認・相談の姿勢）
  clarity = 発話明瞭さ（このテキスト面接では文のわかりやすさ）
- summary_id と advice_id はインドネシア語で書く。summary_ja は同じ内容の日本語要約。
- model_answers には、学生の回答が弱かった質問を2〜3個選び、日本語の模範解答例を入れる。
  模範解答は A2〜N4 で言える簡単な日本語にする。
- 必ず evaluate ツールを使って構造化された JSON で返答する。

企業設定：{company_ja}
"""


def _turn(text_ja: str, furigana: str, hint_id: str) -> dict[str, str]:
    return {"text_ja": text_ja, "furigana": furigana, "hint_id": hint_id}


_CLOSING_HINT = (
    "Wawancara selesai. Akhiri dengan salam. Contoh: 「ありがとうございました。失礼いたします。」"
)
_GYAKU_SHITSUMON = _turn(
    "ありがとうございます。最後に、何か質問はありますか。",
    "ありがとうございます。さいごに、なにかしつもんはありますか。",
    "Ajukan satu pertanyaan tentang pekerjaan. Contoh: 「研修はありますか。」",
)

SCENARIOS: dict[str, dict[str, Any]] = {
    "kaigo": {
        "title_ja": "介護施設の採用面接",
        "title_id": "Wawancara: perawatan lansia",
        "description_id": "Simulasi wawancara kerja dengan kepala fasilitas "
        "perawatan lansia di Jepang.",
        "level": "A2",
        "sector": "kaigo",
        "max_candidate_turns": 5,
        "company_ja": "さくら介護センター（東京都内の特別養護老人ホーム、入居者80名）",
        "interviewer_ja": "施設長の佐藤",
        "opening": _turn(
            "本日は面接に来てくださって、ありがとうございます。施設長の佐藤です。まず、自己紹介をお願いします。",
            "ほんじつはめんせつにきてくださって、ありがとうございます。しせつちょうのさとうです。"
            "まず、じこしょうかいをおねがいします。",
            "Perkenalkan diri: nama, asal, dan salam. Contoh: "
            "「（nama）と申します。インドネシアから参りました。よろしくお願いいたします。」",
        ),
        "stub_questions": [
            _turn(
                "ありがとうございます。どうしてこの施設で働きたいと思いましたか。",
                "ありがとうございます。どうしてこのしせつではたらきたいとおもいましたか。",
                "Jelaskan alasan Anda ingin bekerja di sini. Contoh: "
                "「家族の世話をした経験があるからです。」",
            ),
            _turn(
                "そうですか。では、利用者様が「ごはんを食べたくない」と言ったら、どうしますか。",
                "そうですか。では、りようしゃさまが「ごはんをたべたくない」といったら、どうしますか。",
                "Tanyakan alasannya dengan lembut, lalu laporkan ke senior. Contoh: "
                "「理由を聞いて、先輩に報告します。」",
            ),
            _turn(
                "わかりました。夜勤もありますが、体調の管理はできますか。",
                "わかりました。やきんもありますが、たいちょうのかんりはできますか。",
                "Jawab bahwa Anda bisa dan jelaskan cara menjaga kesehatan. Contoh: "
                "「はい、大丈夫です。早く寝るようにしています。」",
            ),
            _GYAKU_SHITSUMON,
            _turn(
                "ご質問ありがとうございます。研修や生活のサポートがありますので、安心してください。"
                "本日はありがとうございました。結果は後日ご連絡します。",
                "ごしつもんありがとうございます。けんしゅうやせいかつのさぽーとがありますので、"
                "あんしんしてください。ほんじつはありがとうございました。けっかはごじつごれんらくします。",
                _CLOSING_HINT,
            ),
        ],
        "model_answers": [
            {
                "question_ja": "どうしてこの施設で働きたいと思いましたか。",
                "answer_ja": "祖母の世話をした経験があり、日本の介護の技術を学びたいからです。",
            },
            {
                "question_ja": "利用者様が「ごはんを食べたくない」と言ったら、どうしますか。",
                "answer_ja": "まず理由をやさしく聞きます。そして、すぐに先輩職員に報告します。",
            },
            {
                "question_ja": "最後に、何か質問はありますか。",
                "answer_ja": "入社後の研修について教えていただけますか。",
            },
        ],
    },
    "food_manufacturing": {
        "title_ja": "食品工場の採用面接",
        "title_id": "Wawancara: pabrik makanan",
        "description_id": "Simulasi wawancara kerja dengan kepala pabrik makanan di Jepang.",
        "level": "A2",
        "sector": "food_manufacturing",
        "max_candidate_turns": 5,
        "company_ja": "大和食品 千葉工場（お弁当・お惣菜の製造、従業員120名）",
        "interviewer_ja": "工場長の鈴木",
        "opening": _turn(
            "こんにちは。大和食品千葉工場の工場長、鈴木です。本日はよろしくお願いします。まず、自己紹介をお願いします。",
            "こんにちは。やまとしょくひんちばこうじょうのこうじょうちょう、すずきです。"
            "ほんじつはよろしくおねがいします。まず、じこしょうかいをおねがいします。",
            "Perkenalkan diri: nama, asal, dan salam. Contoh: "
            "「（nama）と申します。インドネシアから参りました。よろしくお願いいたします。」",
        ),
        "stub_questions": [
            _turn(
                "ありがとうございます。どうしてこの工場で働きたいと思いましたか。",
                "ありがとうございます。どうしてこのこうじょうではたらきたいとおもいましたか。",
                "Jelaskan alasan Anda ingin bekerja di sini. Contoh: "
                "「日本の技術を学びたいからです。」",
            ),
            _turn(
                "食品の工場では衛生管理がとても大切です。どんなことに気をつけますか。",
                "しょくひんのこうじょうではえいせいかんりがとてもたいせつです。どんなことにきをつけますか。",
                "Sebutkan cara menjaga kebersihan. Contoh: 「手をよく洗って、マスクをつけます。」",
            ),
            _turn(
                "同じ作業が長く続くこともあります。大丈夫ですか。",
                "おなじさぎょうがながくつづくこともあります。だいじょうぶですか。",
                "Jawab bahwa Anda bisa berkonsentrasi. Contoh: "
                "「はい、大丈夫です。集中してがんばります。」",
            ),
            _GYAKU_SHITSUMON,
            _turn(
                "ご質問ありがとうございます。先輩が仕事を丁寧に教えますので、安心してください。"
                "本日はありがとうございました。結果は後日ご連絡します。",
                "ごしつもんありがとうございます。せんぱいがしごとをていねいにおしえますので、"
                "あんしんしてください。ほんじつはありがとうございました。けっかはごじつごれんらくします。",
                _CLOSING_HINT,
            ),
        ],
        "model_answers": [
            {
                "question_ja": "どうしてこの工場で働きたいと思いましたか。",
                "answer_ja": "日本の食品工場は衛生管理がすばらしいので、"
                "その技術を学びたいからです。",
            },
            {
                "question_ja": "衛生管理で、どんなことに気をつけますか。",
                "answer_ja": "作業の前に手をよく洗い、マスクと帽子を正しくつけます。"
                "体調が悪いときは、必ず報告します。",
            },
            {
                "question_ja": "最後に、何か質問はありますか。",
                "answer_ja": "一日の仕事の流れを教えていただけますか。",
            },
        ],
    },
    "restaurant": {
        "title_ja": "レストランの採用面接",
        "title_id": "Wawancara: restoran",
        "description_id": "Simulasi wawancara kerja dengan manajer restoran Jepang.",
        "level": "A2",
        "sector": "restaurant",
        "max_candidate_turns": 5,
        "company_ja": "和食レストラン「あおば食堂」（首都圏5店舗のチェーン）",
        "interviewer_ja": "店長の高橋",
        "opening": _turn(
            "こんにちは。あおば食堂の店長、高橋です。本日はよろしくお願いします。まず、自己紹介をお願いします。",
            "こんにちは。あおばしょくどうのてんちょう、たかはしです。"
            "ほんじつはよろしくおねがいします。まず、じこしょうかいをおねがいします。",
            "Perkenalkan diri: nama, asal, dan salam. Contoh: "
            "「（nama）と申します。インドネシアから参りました。よろしくお願いいたします。」",
        ),
        "stub_questions": [
            _turn(
                "ありがとうございます。どうしてレストランの仕事をしたいと思いましたか。",
                "ありがとうございます。どうしてれすとらんのしごとをしたいとおもいましたか。",
                "Jelaskan alasan Anda ingin bekerja di restoran. Contoh: "
                "「人と話すことが好きだからです。」",
            ),
            _turn(
                "お客様に間違った料理を出してしまったら、どうしますか。",
                "おきゃくさまにまちがったりょうりをだしてしまったら、どうしますか。",
                "Minta maaf dan laporkan ke pemimpin. Contoh: 「すぐに謝って、店長に報告します。」",
            ),
            _turn(
                "土曜日や日曜日に働くことはできますか。",
                "どようびやにちようびにはたらくことはできますか。",
                "Jawab tentang jadwal kerja Anda. Contoh: 「はい、働くことができます。」",
            ),
            _GYAKU_SHITSUMON,
            _turn(
                "ご質問ありがとうございます。接客の研修がありますので、安心してください。"
                "本日はありがとうございました。結果は後日ご連絡します。",
                "ごしつもんありがとうございます。せっきゃくのけんしゅうがありますので、"
                "あんしんしてください。ほんじつはありがとうございました。けっかはごじつごれんらくします。",
                _CLOSING_HINT,
            ),
        ],
        "model_answers": [
            {
                "question_ja": "どうしてレストランの仕事をしたいと思いましたか。",
                "answer_ja": "人と話すことが好きで、日本のおもてなしを学びたいからです。",
            },
            {
                "question_ja": "お客様に間違った料理を出してしまったら、どうしますか。",
                "answer_ja": "すぐにお客様に謝ります。そして、店長に報告して、"
                "正しい料理をお持ちします。",
            },
            {
                "question_ja": "最後に、何か質問はありますか。",
                "answer_ja": "注文の取り方の研修はありますか。",
            },
        ],
    },
}
