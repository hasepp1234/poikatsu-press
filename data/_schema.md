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
| affiliate_url | アフィリンク（提携後に設定。PR表記必須） |
| updated | 最終更新日（表示必須） |

## guides.json … 入門・最適化ガイド（回遊・E-E-A-T）
| フィールド | 説明 |
|---|---|
| slug | ガイドのURLスラッグ |
| title | タイトル |
| body_md | 本文（Markdown） |
| related_cards | 関連カードslug配列 |
| refs | 参考一次ソース配列 |
