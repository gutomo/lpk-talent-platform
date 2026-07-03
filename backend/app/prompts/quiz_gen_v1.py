"""ドリル問題の下書き生成プロンプト（版管理対象）。

BUILD_PLAN Phase 3「問題生成スクリプト」用。生成した問題案は必ず review_flag=True で
保存し、人間がレビューして承認するまで出題しない。
完全オリジナル方針：JLPT / JFT-Basic の公式問題・過去問・市販教材の複製や言い換えは禁止。
STUB_DRAFTS は llm_provider_mode=stub 用の決定的な下書き（資格情報なしの動作確認用）。
"""

PROMPT_VERSION = "quiz-gen-v1"

# 分野ごとの作問ルール。SYSTEM_TEMPLATE の {section_rules} に入る。
SECTION_RULES: dict[str, str] = {
    "grammar": (
        "助詞・動詞の活用・N4文型を問う。question は空欄「（　）」を1つ含む短文にし、"
        "choices は空欄に入る語句とする。"
    ),
    "vocabulary": (
        "N4水準の語彙の意味・使い方を問う。question は短文または「〜はどれですか」形式、"
        "choices は語句とする。"
    ),
    "reading": (
        "passage_ja に3〜6文のやさしい本文を書き、question はその内容確認とする。"
        "本文は職場や生活の場面（連絡メモ・お知らせ・短い手紙など）にする。"
    ),
    "listening": (
        "script_ja に2〜4文の音声スクリプト（TTSで読み上げる。会話または館内放送風）を書き、"
        "question はその内容確認とする。question 自体は音声を聞く前提の短い設問にする。"
    ),
}

SYSTEM_TEMPLATE = """\
あなたは日本語教材の作問者です。インドネシア人学生（日本語レベル A2〜N4）向けの
試験対策ドリルの問題案を {count} 問作ります。水準タグは {level}（非公式の対策教材）。
次のルールを必ず守ってください。
- 完全オリジナルの問題のみ。JLPT / JFT-Basic の公式問題・過去問・市販教材の複製や
  言い換えは禁止する。
- 出題分野：{section}。{section_rules}
- 題材は日本で働くインドネシア人の生活と仕事（介護・食品製造・外食・日常生活）を優先する。
- choices は必ず4つ。互いに重複せず、正解は1つだけ。answer_index（0〜3）はばらけさせる。
- explanation_id には、なぜ正解かのやさしい解説をインドネシア語で1〜2文入れる。
- 問題文・選択肢・本文はやさしい日本語。漢字はN4までを目安にする。
- 実在の企業名・実在の人物は使わない。
- 必ず draft_items ツールを使い、構造化 JSON で返す。
"""

# stub モード用の決定的な下書き（分野ごとに1問の雛形。件数分は連番で複製する）。
STUB_DRAFTS: dict[str, dict] = {
    "grammar": {
        "question": "しごとが おわったら、りーだーに（　）します。",
        "choices": ["ほうこく", "しつもん", "あいさつ", "れんしゅう"],
        "answer_index": 0,
        "explanation_id": (
            "Setelah pekerjaan selesai, kita melapor (houkoku) kepada pemimpin. "
            "Ini bagian dari hourensou."
        ),
    },
    "vocabulary": {
        "question": "「まいにち おなじ じかんに おきます」の いみは どれですか。",
        "choices": [
            "Bangun pada jam yang sama setiap hari",
            "Tidur larut malam setiap hari",
            "Bekerja pada hari libur",
            "Makan pagi bersama keluarga",
        ],
        "answer_index": 0,
        "explanation_id": (
            "Okimasu artinya bangun. Mainichi onaji jikan ni = setiap hari pada jam yang sama."
        ),
    },
    "reading": {
        "question": "メモを よんだ ひとは、まず なにを しますか。",
        "choices": [
            "じむしょに でんわを かける",
            "そうじを はじめる",
            "きゅうけいを とる",
            "かいぎに いく",
        ],
        "answer_index": 0,
        "passage_ja": (
            "スタッフの みなさんへ。あした ごぜん 9じから ミーティングが あります。"
            "でる まえに、じむしょに でんわを して ください。よろしく おねがいします。"
        ),
        "explanation_id": "Memo meminta menelepon kantor terlebih dahulu sebelum hadir.",
    },
    "listening": {
        "question": "おとこの ひとは いつ びょういんに いきますか。",
        "choices": ["あしたの あさ", "きょうの よる", "らいしゅう", "こんしゅうの どようび"],
        "answer_index": 0,
        "script_ja": (
            "あたまが いたいので、あしたの あさ びょういんに いきます。"
            "きょうは はやく ねます。"
        ),
        "explanation_id": (
            "Laki-laki itu berkata akan pergi ke rumah sakit besok pagi (ashita no asa)."
        ),
    },
}
