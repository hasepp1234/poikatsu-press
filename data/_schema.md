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

## cards.json … クレカ発行キャンペーン比較（公式で裏取り必須）
| フィールド | 説明 |
|---|---|
| slug | カードのURLスラッグ |
| name | カード名 |
| issuer | 発行会社 |
| brand | 国際ブランド |
| campaign_points | 付与ポイント（入会キャンペーン） |
| campaign_conditions | 付与条件 |
| annual_fee | 年会費 |
| base_return_rate | 基本還元率 |
| category | 分類 |
| affiliate_url | アフィリンク（ASP提携承認後に設定。設定時はPR表記必須） |
| official_url | 公式サイトの参考リンク（affiliate_url未設定時はこちらを表示。2026-07-11追加） |
| updated | 最終更新日（表示必須。値は公式サイト取得日） |

## guides.json … 入門・最適化ガイド（回遊・E-E-A-T）
| フィールド | 説明 |
|---|---|
| slug | ガイドのURLスラッグ |
| title | タイトル |
| body_md | 本文（Markdown） |
| related_cards | 関連カードslug配列 |
| refs | 参考一次ソース配列 |

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
