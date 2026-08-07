# Research Trend Explorer

## 文献検索・研究テーマ探索Webアプリ 仕様書

**Version:** 0.1

**開発環境:** VSCode / Python（uv使う）

**主要AI基盤:** OpenAI API

**想定ユーザー:** 大学院生・大学教員・研究者・リサーチャー

---

# 1. アプリ概要

## 1.1 アプリ名

**Research Trend Explorer**

仮称とし、将来的に変更可能とする。

## 1.2 目的

Research Trend Explorer は、研究キーワードまたは研究テーマを入力すると、その分野について以下を自動的に調査・整理して提示する、研究者向け Web アプリケーションである。

1. 分野を理解するための基礎・著名文献
2. 現在注目されている研究テーマ・研究潮流
3. 各研究潮流を代表する比較的新しい研究

単なる論文検索ではなく、「この研究分野を理解するために何を読むべきか」「現在どのような研究が行われているか」「各テーマではどの論文を見るべきか」を短時間で俯瞰できる研究支援ツールとして機能する。

---

# 2. 基本方針

本アプリでは、文章の流暢さや指定件数を満たすことよりも、文献情報の正確性と検証可能性を優先する。

基本原則:

- 実在を十分に確認できない文献は表示しない
- DOI を推測・生成しない
- 著者名、出版年、ジャーナル名等を推測で補完しない
- abstract を確認できない場合、内容をタイトルから推測しない
- 指定件数に達しない場合でも、架空・未確認の文献で補完しない
- AI が生成した書誌情報をそのまま信用せず、可能な限り外部情報源と照合する
- 「著名」「重要」「注目されている」等の評価は絶対的なものとして提示せず、検索時点で取得できる情報に基づく選定であることを明示する
- AI が候補を発見し、プログラム側で検証し、検証済み情報を AI が整理する構造を基本とする

---

# 3. 基本ユーザーフロー

ユーザーはトップ画面の検索フォームに研究テーマを入力する。

例:

- Corporate Social Responsibility
- renewable energy investment
- behavioral economics and climate policy
- supply chain resilience
- generative AI in education
- 企業の社会的責任
- 再生可能エネルギー投資
- 気候変動政策と行動経済学

「研究テーマを探索」ボタンを押すと検索処理を開始する。

内部では概ね以下の処理を実行する。

1. 検索テーマ解析
2. 関連検索語生成
3. 基礎文献候補探索
4. 文献情報検証
5. 最近の研究文献探索
6. 研究潮流分析
7. 各研究潮流の代表文献探索
8. 代表文献の検証
9. 日本語による要約・整理
10. 構造化 JSON 生成
11. 結果画面表示

---

# 4. 検索入力

## 4.1 メイン検索フォーム

画面上部に大きな検索フォームを配置する。

プレースホルダー例:

「研究テーマやキーワードを入力してください」

検索ボタン:

「研究テーマを探索」

検索文字列は日本語・英語の両方を受け付ける。

日本語入力時は、AI が内部的に関連する英語キーワードを生成し、日本語文献だけでなく英語文献も検索対象とする。

---

# 5. 検索条件

検索フォーム付近に詳細条件パネルを配置する。

## 5.1 研究分野

選択肢:

- 自動判定
- 経済学・経営学
- 社会科学
- 工学
- 情報科学
- 環境科学
- 医学・生命科学
- 人文科学
- その他

初期値: 自動判定

## 5.2 基礎文献の件数

初期値: 3 件

## 5.3 研究潮流の件数

初期値: 5 件

## 5.4 各研究潮流の代表文献数

初期値: 3 件

## 5.5 最新研究として扱う期間

初期値: 直近 5 年間

選択肢:

- 直近 3 年間
- 直近 5 年間
- 直近 10 年間
- 期間指定

## 5.6 文献言語

初期値: 日本語・英語

## 5.7 文献タイプ

初期値: 査読付き論文を優先

---

# 6. 検索テーマ解析

検索開始後、入力テーマを AI で解析する。

生成する内容:

- 入力されたキーワード
- 正規化された研究テーマ
- 関連する英語キーワード
- 関連する日本語キーワード
- 類義語
- 略語
- 関連概念
- 推定研究分野
- 検索対象期間

検索語は検索結果画面で確認できるようにする。

---

# 7. 基礎・著名文献

入力テーマについて、その分野を理解するうえで一般的、著名、影響力が大きい、または後続研究の基盤となった文献を原則 3 件提示する。

評価対象:

- 影響力
- 引用実績
- 研究分野形成への影響
- 標準的な理論・方法・概念の提示
- 後続研究での参照頻度
- レビュー論文等での位置づけ
- テーマとの直接的関連性

## 7.1 表示項目

各基礎文献について以下を表示する。

- 文献区分
- タイトル
- 著者
- 出版年
- ジャーナル名、学会名、出版社名等
- 文献タイプ
- DOI
- 日本語概要
- 原文または出版社ページ URL
- Google Scholar 検索リンク
- この文献が重要である理由
- 書誌情報の確認状況
- 確認に利用した情報源

文献区分バッジ: Foundational Paper

---

# 8. 最新の研究テーマ・研究潮流

入力テーマについて、現在特に注目されている研究テーマまたは研究潮流を原則 3～5 件提示する。

初期値は 5 件とする。

判断基準:

- 直近 5 年間の関連文献
- 最近のレビュー論文
- 主要ジャーナル
- 国際会議
- 社会的関心
- 政策動向
- 最近の研究量
- 学術的重要性
- 今後の発展可能性

## 8.1 表示項目

- 研究テーマ名（日本語）
- Research Topic Name（英語）
- 100～200 字程度の日本語説明
- なぜ現在注目されているのか
- 主な研究課題
- 関連キーワード
- 成熟度
- 代表文献

## 8.2 成熟度

- Emerging
- Growing
- Established

成熟度は AI による定性的評価であり、絶対的な指標ではないことを UI 上で示す。

---

# 9. 各研究潮流の代表研究

各研究潮流について、原則 3 件の代表研究を提示する。

基本的には「最新研究として扱う期間」に含まれる研究を優先する。

## 9.1 選定方針

- 研究テーマとの関連性
- 学術的重要性
- 研究内容の代表性
- 掲載媒体
- 新規性
- 後続研究への影響
- 利用可能な引用・参照情報
- レビュー論文等での位置づけ

## 9.2 表示項目

- タイトル
- 著者
- 出版年
- ジャーナル名、学会名、出版社名等
- 文献タイプ
- DOI
- 日本語概要
- 原文または出版社ページ URL
- Google Scholar 検索リンク
- この研究が当該テーマを代表する理由
- verification status
- verification sources
- BibTeX

---

# 10. 文献検証

本アプリの最重要機能の一つとする。

AI が提示した書誌情報をそのまま表示せず、可能な範囲で外部情報源を利用して検証する。

優先情報源:

- 出版社公式ページ
- DOI 公式ページ
- Crossref
- PubMed
- arXiv
- SSRN
- RePEc
- 大学・研究機関リポジトリ
- 学会公式ページ
- その他信頼できる学術情報源

初期プロトタイプでは、OpenAI Web search に加えて Crossref API を主要な書誌検証手段として利用する。

## 10.1 検証項目

- title
- authors
- publication year
- journal / venue
- DOI
- URL

## 10.2 Verification Status

- verified
- partially_verified
- unverified

原則として、unverified の文献は最終検索結果に表示しない。

## 10.3 詳細検証情報

内部データでは以下を保持する。

- titleMatched
- authorsMatched
- yearMatched
- venueMatched
- doiMatched
- publisherPageFound
- abstractFound

---

# 11. Abstract 処理

abstract を出版社、データベース、リポジトリ等で確認できる場合、その内容に基づき日本語で要約する。

原文タイトルは翻訳せず原語表記を維持する。

著者名、ジャーナル名、出版社名についても原語表記を維持する。

abstract が取得できない場合は、「公開されている概要を確認できませんでした」と表示する。

タイトルやキーワードだけから研究内容を推測して abstract 相当の文章を生成してはならない。

---

# 12. OpenAI API

## 12.1 API

OpenAI Responses API を使用する。

## 12.2 Web 検索

OpenAI API の Web search 機能を利用し、最新の研究情報および Web 上の学術情報を取得する。

## 12.3 Structured Outputs

AI の最終レスポンスは構造化された JSON として取得する。

Pydantic モデルまたは JSON Schema によってレスポンス形式を制約する。

## 12.4 モデル

モデル名はコードに固定せず環境変数で設定する。

例: OPENAI_MODEL

初期推奨: gpt-5.6-terra

精度重視の設定として gpt-5.6-sol も利用できる構造とする。

---

# 13. AI の役割

OpenAI モデルは主に以下を担当する。

- 入力テーマの理解
- 日本語・英語検索キーワード生成
- 検索クエリ生成
- Web 検索
- 基礎文献候補探索
- 研究潮流候補探索
- 研究潮流の分類・整理
- 代表研究候補探索
- abstract の日本語要約
- 文献の重要性に関する説明
- 研究潮流説明
- 関連キーワード生成
- 検索結果の最終整理

Python 側で行うもの:

- JSON validation
- DOI normalization
- Crossref 照合
- 書誌情報検証
- 重複文献除去
- URL 形式確認
- citation key 生成
- BibTeX 生成
- Markdown export
- フィルタリング
- 並び替え

---

# 14. 検索処理ステータス

検索には一定時間を要するため、ユーザーが処理状況を確認できる UI を実装する。

表示例:

- 検索テーマを解析しています
- 関連キーワードを生成しています
- 基礎文献候補を検索しています
- 文献情報を検証しています
- 最近の研究を調査しています
- 最新の研究潮流を分析しています
- 各テーマの代表研究を検索しています
- 代表研究の書誌情報を確認しています
- 検索結果を整理しています

必要に応じて、候補数・検証済み件数の進捗も表示する。

---

# 15. 検索結果画面

以下の順序で表示する。

## 15.1 検索テーマの概要

- 入力されたキーワード
- 関連する英語キーワード
- 関連する日本語キーワード
- 判定された研究分野
- 検索対象期間
- 検索実行日時
- 検索結果についての簡単な説明

## 15.2 基礎・著名文献

原則 3 件、カード形式で表示する。

## 15.3 注目されている研究テーマ・研究潮流

原則 5 テーマ。

## 15.4 各テーマの代表的な最新研究

各テーマ 3 件。

## 15.5 検索上の注意事項と情報源

- AI による評価であること
- 取得日時
- Web 検索で確認した主な情報源
- 検索時に発生した警告
- 件数不足の理由
- verification に関する説明

---

# 16. 文献カード

文献はカード形式で表示する。

構成:

- 文献区分バッジ
- 論文タイトル
- 著者 / 出版年
- Journal / Conference / Publisher
- DOI
- 日本語概要
- この文献が重要な理由
- Verification
- 操作ボタン
  - 出版社ページ
  - Google Scholar
  - BibTeX をコピー

DOI が存在する場合はクリック可能にする。

DOI が確認できない場合は「DOI なし」または「DOI を確認できず」と表示する。

---

# 17. Google Scholar

Google Scholar から直接データをスクレイピングする機能は初期版では実装しない。

各文献についてタイトルを用いた Google Scholar 検索 URL を生成し、新しいタブで開く。

---

# 18. BibTeX

各文献カードに「BibTeX をコピー」ボタンを配置する。

書誌情報は検証済みデータから生成する。

Citation key は、可能な限り以下の形式とする。

- 第一著者姓 + 出版年 + タイトルの主要語

例:

- smith2024sustainable
- oga2026corporate

生成ルール:

- 小文字
- 空白なし
- 特殊文字除去

---

# 19. 検索結果操作

検索結果画面で以下を利用可能とする。

- 検索結果全体のコピー
- Markdown 形式でエクスポート
- BibTeX コピー
- 結果内キーワード検索
- 出版年順並び替え
- 文献タイプによるフィルタリング
- Verification Status によるフィルタリング
- 新しい検索
- 再検索

並び替え順:

- 新しい順
- 古い順

---

# 20. Markdown Export

検索結果全体を Markdown ファイルとしてエクスポートできるようにする。

基本構造:

```md
# Search Theme

## Query Summary

## Foundational Papers

### Paper 1

書誌情報

概要

重要性

## Research Trends

### Trend 1

説明

#### Representative Papers

...

## Sources

## Warnings
```

---

# 21. JSON データ構造

トップレベル JSON は最低限以下を持つ。

```json
{
  "querySummary": {},
  "foundationalPapers": [],
  "researchTrends": [],
  "sources": [],
  "warnings": [],
  "searchMetadata": {}
}
```

## QuerySummary

```json
{
  "originalQuery": "",
  "normalizedTopic": "",
  "keywordsJa": [],
  "keywordsEn": [],
  "detectedField": "",
  "searchPeriod": {
    "from": 2022,
    "to": 2026
  },
  "executedAt": ""
}
```

## Paper

```json
{
  "id": "",
  "category": "",
  "title": "",
  "authors": [],
  "year": null,
  "venue": "",
  "publicationType": "",
  "doi": null,
  "abstractJa": null,
  "publisherUrl": null,
  "googleScholarUrl": "",
  "importanceReason": "",
  "bibtex": "",
  "verification": {
    "status": "",
    "titleMatched": false,
    "authorsMatched": false,
    "yearMatched": false,
    "venueMatched": false,
    "doiMatched": false,
    "publisherPageFound": false,
    "abstractFound": false
  },
  "sources": []
}
```

## ResearchTrend

```json
{
  "id": "",
  "nameJa": "",
  "nameEn": "",
  "description": "",
  "whyImportantNow": "",
  "researchQuestions": [],
  "keywords": [],
  "maturity": "",
  "papers": []
}
```

## Source

```json
{
  "id": "",
  "title": "",
  "url": "",
  "sourceType": "",
  "accessedAt": ""
}
```

## Warning

```json
{
  "code": "",
  "message": ""
}
```

---

# 22. バックエンド

Python を使用する。

推奨フレームワーク: FastAPI

主な役割:

- OpenAI API 呼び出し
- Web 検索オーケストレーション
- Crossref API アクセス
- 文献検証
- Structured Output validation
- 検索結果保持
- エクスポート処理
- エラーハンドリング

---

# 23. API エンドポイント

初期版では以下を基本とする。

## POST /api/search

新しい文献調査を開始する。

Request:

- query
- field
- foundationalCount
- trendCount
- papersPerTrend
- recentYears
- languages
- publicationTypes

Response:

- searchId

## GET /api/search/{searchId}

検索状態および検索結果を取得する。

Response:

- status
- progress
- result
- error

## GET /api/search/{searchId}/markdown

Markdown ファイルを生成する。

## GET /api/papers/{paperId}/bibtex

BibTeX データを取得する。

---

# 24. フロントエンド

初期プロトタイプでは複雑な SPA フレームワークを必須としない。

推奨構成:

- HTML
- CSS
- Vanilla JavaScript

---

# 25. デザイン

研究者向けの知的で信頼感のあるモダンなデザインとする。

基本方針:

- 白または淡いグレー背景
- ネイビー
- ダークブルー
- ブルーグレー
- 十分な余白
- 高い可読性
- 過度な装飾を避ける
- 派手なグラデーションを避ける
- 大学図書館 / Academic Database / Research Dashboard を連想させる UI

PC・タブレット・スマートフォンに対応するレスポンシブデザインとする。

---

# 26. ダークモード

ライトモード・ダークモードを切り替え可能にする。

設定はブラウザの localStorage 等に保存してよい。

初回アクセス時は OS 設定を参照することを推奨する。

---

# 27. エラー処理

## OpenAI API Error

「AI による調査中にエラーが発生しました」

再検索ボタンを表示する。

## Web Search Error

可能な範囲で処理を継続する。結果の信頼性が低下する場合は warnings へ追加する。

## Verification Error

確認できない文献は原則除外する。

## 0 件

「条件を満たし、実在を確認できる文献を取得できませんでした」

検索条件の変更または再検索を案内する。

## 件数不足

「指定された 3 件のうち、書誌情報を十分に確認できた 2 件のみ表示しています。」

不足分を AI が生成して補完してはならない。

---

# 28. セキュリティ

OpenAI API Key をフロントエンドへ送信してはならない。

API Key はサーバー側の環境変数として管理する。

.env 例:

- OPENAI_API_KEY
- OPENAI_MODEL
- CROSSREF_MAILTO

.env を GitHub へコミットしない。

ブラウザから OpenAI API を直接呼び出さない。

---

# 29. 推奨プロジェクト構成

```text
research-trend-explorer/
├── app/
│   ├── main.py
│   ├── api/
│   │   └── routes.py
│   ├── services/
│   │   ├── openai_service.py
│   │   ├── search_service.py
│   │   ├── verification_service.py
│   │   ├── crossref_service.py
│   │   ├── bibtex_service.py
│   │   └── export_service.py
│   ├── models/
│   │   ├── search.py
│   │   ├── paper.py
│   │   └── trend.py
│   ├── prompts/
│   │   ├── query_analysis.txt
│   │   ├── foundational_search.txt
│   │   ├── trend_analysis.txt
│   │   └── final_synthesis.txt
│   └── utils/
│       ├── doi.py
│       ├── scholar.py
│       └── text.py
├── frontend/
│   ├── index.html
│   ├── result.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       └── result.js
├── tests/
├── exports/
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

# 30. 検索品質方針

基礎文献、研究潮流、代表文献の具体的な検索方法については、初期仕様では厳密なアルゴリズムを固定しない。

AI に一定の裁量を与え、検索結果を評価しながら適切な検索クエリを生成・追加する。

必要に応じて複数回 Web 検索を行う。

基礎文献 3 件が必要な場合でも、最初から 3 件だけ取得するのではなく、それより多い候補を探索し、その中から検証済み文献を選定する。

研究潮流についても単一検索結果から決定せず、複数の検索結果・最近の研究・レビュー等から総合的に判断する。

---

# 31. AI 回答方針

AI へのシステム指示には最低限以下を含める。

- 回答は日本語
- タイトルは原語
- 著者名は原語
- Journal / Conference / Publisher は原語
- 文献の存在を推測しない
- DOI を推測しない
- abstract のない文献について内容を推測しない
- 件数を満たすために架空の文献を追加しない
- Web で確認できる情報を優先する
- 取得した情報源を記録する
- 評価表現を断定しすぎない
- 医学・法律・政策等では専門的助言として提示しない

---

# 32. 検索ログ

開発・改善用として検索処理のログを保存できる構造とする。

記録する内容:

- searchId
- query
- executedAt
- model
- search settings
- generated search queries
- number of candidate papers
- number of verified papers
- number of rejected papers
- warnings
- API error

API Key や不要な個人情報はログに保存しない。

---

# 33. 将来的な機能

Version 0.1 には含めないが、拡張可能な設計にする。

候補:

- 検索履歴
- お気に入り文献
- 自分の文献ライブラリ
- PDF アップロード
- OpenAI File Search 連携
- Zotero 連携
- DOI から文献追加
- BibTeX ファイル一括エクスポート
- RIS export
- Citation Network
- 著者ネットワーク
- キーワードネットワーク
- 年別研究トレンド可視化
- 文献数推移
- Research Gap 候補提示
- 研究テーマ比較
- 複数検索結果比較
- ユーザーによる文献評価
- 検索結果キャッシュ
- 研究プロジェクト単位での保存

---

# 34. Version 0.1 MVP

初期プロトタイプで必ず実装する。

## 検索

- キーワード入力
- 日本語・英語対応
- 検索条件
- OpenAI Responses API
- Web search

## 調査

- 基礎文献 3 件
- 研究潮流 5 件
- 各潮流 3 件
- 直近 5 年間検索
- 日本語整理

## 検証

- Crossref 照合
- DOI 確認
- 書誌情報確認
- Verification Status
- 未確認文献除外

## 表示

- Query Summary
- Foundational Papers
- Research Trends
- Representative Papers
- Sources
- Warnings

## 操作

- Google Scholar リンク
- Publisher リンク
- DOI リンク
- BibTeX コピー
- Markdown Export
- キーワードフィルタ
- 年順並び替え
- 文献タイプフィルタ
- ダークモード
- 新しい検索
- 再検索

---

# 35. MVP では実装しないもの

- ユーザー登録
- ログイン
- クラウド同期
- Zotero 同期
- PDF 管理
- PDF 全文解析
- 文献推薦履歴学習
- Citation Network
- 複雑な可視化
- 複数ユーザー共有
- 課金機能

---

# 36. 完成条件

Version 0.1 は、以下を満たした時点で動作可能なプロトタイプとして完成とする。

1. ユーザーが研究テーマを入力できる
2. 日本語入力から英語検索語を生成できる
3. OpenAI Web search を利用して文献を探索できる
4. 基礎文献を最大 3 件表示できる
5. 研究潮流を最大 5 件表示できる
6. 各研究潮流について最大 3 件の代表研究を表示できる
7. 文献について書誌情報検証を行う
8. 未検証文献を無理に表示しない
9. abstract を確認できない場合に推測しない
10. 文献ごとに出版社、DOI、Google Scholar 等へアクセスできる
11. BibTeX をコピーできる
12. Markdown 形式で結果を保存できる
13. 検索に利用した主要情報源を確認できる
14. API Key がクライアント側へ露出しない
15. 検索中・エラー・0 件・件数不足の UI が存在する
16. PC・スマートフォン双方で基本操作できる

---

# 37. 開発上の最優先事項

1. 文献情報の正確性
2. 文献の実在確認
3. 基礎文献・研究潮流・代表研究の選定品質
4. 情報源の透明性
5. UI の読みやすさ
6. 検索速度

件数・速度・見栄えよりも、研究者が安心して検索結果を次の文献調査に利用できることを優先する。

---

# 38. 最終コンセプト

Research Trend Explorer は、検索キーワードに一致する論文を単純に列挙するアプリではない。

ユーザーが研究テーマを入力すると、Foundations → Current Research Trends → Representative Recent Studies という流れで研究分野全体を案内することを中核体験とする。

最終的には、「初めて調べる研究分野について、まず何を読み、現在何が研究され、その先にどのような研究機会があるのかを短時間で理解できる研究支援ツール」となることを目標とする。
