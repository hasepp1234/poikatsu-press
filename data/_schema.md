# データスキーマ（計画書セクション4）

## news.json  … ニュース記事（AI要約＋監修）
| フィールド | 説明 |
|---|---|
| news_id | 記事の一意ID |
| title | 見出し |
| summary | 中立・簡潔なAI要約（丸写し禁止） |
| category | kaiaku / campaign / credit-card / qr-pay / furusato / point-service |
| tags | タグ配列 |
| source_url | 一次ソースURL（必須） |
| published | 公開日時 |
| updated | 更新日時 |
| featured | 任意・true/false。トップページ「TOPニュース」欄に表示する1件を手動で選ぶためのフラグ（2026-07-13追加）。
  複数trueがある場合はpublishedが最新のものを採用 |
| source_type | 任意・influencer / official。記事化のきっかけがインフルエンサー発信か公式発表単独かの区別（2026-07-13追加。表示には使わず社内の出典管理用） |
| source_account | 任意・きっかけとなったXアカウントのhandle（例："haiji_doctor"）。x_sources.json掲載アカウントを想定（2026-07-13追加） |

トップページの「改悪情報」欄は、category=kaiakuかつpublishedが直近30日以内の項目を自動抽出して一覧表示する（2026-07-13、build.py対応）。

## cards.json … クレカ発行キャンペーン比較（公式で裏取り必須）
| フィールド | 説明 |
|---|---|
| slug | カードのURLスラッグ |
| name | カード名 |
| issuer | 発行会社 |
| brand | 国際ブランド |
| campaign_points | 付与ポイント（入会キャンペーン） |
| campaign_conditions | 付与条件 |
| campaign_start | キャンペーン開始日（YYYY-MM-DD、任意。2026-07-13追加）。トップページの「新規/進行中/終了間近」分類に使用 |
| campaign_end | キャンペーン終了日（YYYY-MM-DD、任意。2026-07-13追加）。未定・期限なしの場合は空文字 |
| annual_fee | 年会費 |
| base_return_rate | 基本還元率 |
| category | 分類 |
| affiliate_url | アフィリンク（ASP提携承認後に設定。設定時はPR表記必須） |
| official_url | 公式サイトの参考リンク（affiliate_url未設定時はこちらを表示。2026-07-11追加） |
| updated | 最終更新日（表示必須。値は公式サイト取得日） |

### トップページのキャンペーン分類ロジック（2026-07-13確定・build.py実装）
- campaign_pointsに「特典なし」を含むカードは対象外（比較表には引き続き掲載）
- campaign_endが設定されていて、今日から7日以内（経過後は除外）→ 終了間近
- campaign_startが設定されていて、開始から7日以内 → 新規
- 上記いずれにも該当しないが特典ありのカード → 進行中
- campaign_start/campaign_endは時間の経過で分類が変わるため、cards.json更新時にあわせて見直すこと

## summary.json … トップページ「全体サマリ」欄（2026-07-13追加）
| フィールド | 説明 |
|---|---|
| summary_text | 手動で書く短い要約文（1〜3文程度） |
| updated | 最終更新日 |

運用は自動生成ではなく手動更新（月2〜3時間の運用に合わせ、区切りの良いタイミングで書き換える）。

## deals.json … トップページ「お得商品」欄（2026-07-13追加）
Amazon・楽天等でインフルエンサーが推奨する商品やタイムセール品などを手動でキュレーションする。
Amazon PA-API・楽天商品検索APIとの自動連携は現時点で未整備のため、当面は手動追加運用とする。
| フィールド | 説明 |
|---|---|
| slug | 商品項目の一意スラッグ |
| title | 商品名・オファー名 |
| description | どのようにお得か（例：クーポン適用で通常価格からX%オフ、サブスク初回無料等） |
| source | amazon / rakuten / other |
| url | 商品ページまたはアフィリンク（アフィリンクの場合はPR表記必須） |
| is_affiliate | true/false。trueの場合、表示側でPRバッジを出す |
| category | 任意の分類（例：subscription, coupon, timesale） |
| source_account | 任意・紹介元インフルエンサーのXアカウントhandle（2026-07-13追加。x_sources.json掲載アカウントを想定） |
| updated | 最終更新日・取得日 |

## guides.json … 入門・最適化ガイド（回遊・E-E-A-T）
| フィールド | 説明 |
|---|---|
| slug | ガイドのURLスラッグ |
| title | タイトル |
| body_md | 本文（改行区切りで段落化。簡易的な仕様のため見出し等のMarkdown記法は未対応） |
| related_cards | 関連カードslug配列（cards.jsonのslugと対応。build.pyが/cards/#slugへのリンクを生成） |
| refs | 参考情報源URL配列（個別の数値主張ではなく一般的な制度解説の裏付け用。2026-07-12追加） |
| faq | 任意。[{q, a}, ...]形式。存在する場合はFAQPage JSON-LDになる |
| updated | 最終更新日（2026-07-12追加。sitemapのlastmodにも反映） |

## news_raw.json … collect_news.pyの検知ログ（news.jsonの前段、2026-07-11追加）
X投稿からの速報検知結果。status=pending_verificationのまま自動でnews.jsonへは反映されない。
公式発表で裏取り後、要約＋出典リンクをnews.jsonに人手 or summarize.pyで反映する。
| フィールド | 説明 |
|---|---|
| detected_id | 検知項目の一意ID（x_<tweet_id>） |
| account_handle / account_name | 検知元Xアカウント |
| tweet_id / tweet_url | 元投稿（掲載時の直接引用元には使わない） |
| text | 投稿本文（社内確認用。記事への丸写し禁止） |
| matched_keywords | ヒットしたキーワード |
| status | pending_verification / verified / published / rejected |
| official_source_url | （verified時に人が追記）公式一次ソースURL。summarize.pyはこれが入っている
  かつstatus=verifiedの項目のみを処理する（2026-07-11追加） |

### 裏取り〜記事化のフロー（2026-07-11確定）
1. collect_news.py が status=pending_verification でnews_raw.jsonに書き出す
2. 人（またはユーザー確認）が各社公式発表で裏取りし、official_source_urlを追記して
   statusをverifiedに変更する
3. summarize.py がverified項目をClaude APIで中立要約し、news.jsonに追記。
   news_raw.json側はstatus=publishedに更新（二重反映防止）

## x_state.json … collect_news.pyの重複検知防止用の状態ファイル
直近検知したツイートIDを保持。機密情報ではないため通常のdataファイルとして扱う。

## x_sources.json / x_sources.csv … collect_news.pyが監視するXアカウント一覧
ポイ活・キャッシュレス・クレカ系インフルエンサーのhandle一覧（2026-07-13時点13件）。
「速報のきっかけ検知」用の情報源であり、news.jsonのsource_account・deals.jsonのsource_accountは
基本的にこの一覧のhandleを指す想定。

## トップページ（全体サマリ以外の4欄）の情報収集方針（2026-07-13追加）
毎日更新運用を想定し、TOPニュース／お得商品／改悪情報の3欄は、x_sources.jsonに登録した
ポイ活系インフルエンサーのX投稿を「きっかけ検知」の起点とする。ただし既存のコンプライアンス
ルールは変わらず適用する：
1. インフルエンサー投稿は「話題の一次候補」に過ぎず、そのまま掲載しない（真偽不明なら掲載しない）
2. 数値・条件（還元率、割引率、キャンペーン期間等）は必ず公式一次ソースで裏取りし、
   news.jsonのsource_url・deals.jsonのurlには公式ソース（またはASP経由の公式案内）を設定する
3. 投稿本文の丸写しは禁止。要約＋出典リンクの形式で掲載する
4. 誰が最初に話題にしたかの透明性のため、news.json/deals.jsonのsource_accountに
   きっかけとなったXアカウントのhandleを任意で記録できる（表示への反映は今後の検討事項）
5. news.json側のcollect_news.py→news_raw.json→（人による裏取り）→summarize.pyのフロー
   （上記「裏取り〜記事化のフロー」）は変更なし。deals.jsonは自動収集の仕組みが未整備のため
   当面は同じ考え方で手動キュレーションする

## トップページ見出しの日付表示（2026-07-13追加）
トップページは毎日更新想定のため、templates/index.htmlのH1は
「ポイ活PRESS {{PAGE_DATE}}版」というプレースホルダを持つ。build.pyのbuild_index()内
_page_date_label()がビルド実行日から「M/D」形式（例：7/13）を生成して差し込む。
summary.json側のupdatedフィールド（全体サマリ欄の更新日表示）とは別管理。
