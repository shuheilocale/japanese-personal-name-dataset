# QA トリアージ UI 設計書

- 作成日: 2026-08-30
- 対象: 保留中 findings（現状 763 件）の承認/却下判断を効率化するローカル Web ツール
- 位置づけ: Phase 1 QA 基盤の承認レイヤー（/qa-apply）の補助ツール。git 管理する（再利用資産・標準ライブラリのみ）

## 1. 目的と要件

- **FR-1** findings JSONL を読み込み、行（file + entry）単位にまとめて表示し、承認 / 却下 / 保留をキー操作で記録できる。判断は即座に JSONL へ書き戻す（原子的書き込み）。
- **FR-2** 各 finding に機械計算した**客観シグナル**を付与して表示する:
  - `dup_elsewhere`: remove_kanji の対象漢字が同ファイルの別読み行にも存在する（その読み一覧を示す）
  - `suffix_rule`: 対象漢字の末尾が固定読みの接尾辞（郎/朗→ろう、彦→ひこ、子→こ、也/哉→や、夫/雄/男→お、美→み、江/恵/枝→え）なのに読みの末尾が一致しない
  - `fix_reading_dup`: fix_reading の提案値が同ファイルの既存読みと重複する（適用すると重複行を生む）
- **FR-3** フィルタ（status / check / confidence / action / file / シグナル有無）と、**フィルタ結果の一括承認・却下**（件数確認付き）。
- **FR-4** 対象漢字のハイライト表示、根拠・提案・確信度の表示、外部検索リンク（Google: 漢字 + 読み + 名前）。
- **NFR** 標準ライブラリのみ、Python 3.8 互換、単一ユーザー前提（排他制御なし）、`applied` の finding は変更不可。

## 2. 構成

```text
.claude/skills/qa-apply/scripts/
├── triage_server.py   # CLI + HTTP サーバ + シグナル計算 + 判断の書き戻し
└── triage_ui.html     # 画面（vanilla JS、外部リソースなし）
tests/test_qa_triage.py
```

起動: `python3 .claude/skills/qa-apply/scripts/triage_server.py --findings qa/findings/<run-id>.jsonl --dataset-dir japanese_personal_name_dataset/dataset [--port 8765] [--no-browser]`

## 3. API

- `GET /` → triage_ui.html
- `GET /api/items` → `{"items": [Item...], "counts": {"pending": n, "approved": n, "rejected": n, "applied": n}}`
  - Item = finding の全フィールド + `row` `{reading, romaji, kanji: [...], population|null}` + `targets: [対象漢字...]` + `signals: [{"type": ..., ...}]` + `search_url`
- `POST /api/decide` body `{"ids": [...], "status": "approved|rejected|pending"}` → `{"updated": n, "counts": {...}}`
  - 未知の id / 不正な status / `applied` の変更 → 400。成功時は JSONL を tmp→rename で全置換保存。

## 4. 画面

左: フィルタ群と残件数バッジ、行リスト（読み・疑義数・シグナル数）。中央: 現在行のカード — 読み/ローマ字、漢字チップ（対象は赤+取り消し線）、各 finding の check/confidence/action/value/evidence とシグナルバッジ、検索リンク。ヘッダ: 進捗（pending 残数）と一括ボタン。キー: `a`=承認 `r`=却下 `s`=保留 `u`=直前の判断を取り消し `j`/`k`=次/前。判断すると自動で次の行へ。

## 5. テスト

- `compute_signals`: dup_elsewhere / suffix_rule / fix_reading_dup の検出と非検出
- `build_items`: row 解析（名/姓の列差）、targets、counts
- `apply_decision`: 状態遷移、applied 拒否、未知 id 拒否、原子的保存の結果
- HTTP: スレッド起動したサーバに http.client で GET /api/items と POST /api/decide（正常・400）
- 画面は実データで手動スモーク（起動して pending 件数が表示されること）
