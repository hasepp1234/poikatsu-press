# ポイ活PRESS（No.162＋No.36 統合サイト）

ポイ活ニュース速報 × クレジットカード発行キャンペーン比較。
ニュースで集客 → 高単価クレカ発行アフィリで収益化。運用は月2〜3時間を目標。

## 構成
- `data/`      … news.json / cards.json / guides.json（JSON駆動）＋ `_schema.md`
- `scripts/`   … collect_news / summarize / update_cards / build（Python＋Claude API）
- `templates/` … base / index / news / cards / category / guide のHTML雛形
- `public/`    … 生成物 & 静的資産（robots.txt / llms.txt / sitemap.xml / assets）

## スタック
静的HTML/JS＋JSON ／ GitHub(hasepp1234) → Vercel自動デプロイ ／ Python＋Claude API。
デプロイはGit CLI不使用・GitHub Web UI手動アップロードのみ（playbook参照）。

## ローカル確認
```
python scripts/build.py        # public/index.html を生成（疎通確認用の最小実装）
```

## 未確定・依頼中（着手前に確定）
- ドメイン: poikatsu-press.com（決定済み）
- Claude APIキー（summarize.py用）
- クレカ発行系ASPの提携（未提携 → 提携後に cards.json / update_cards.py 実装）
- ニュース収集対象ソースのリスト（collect_news.py用）

## コンプライアンス（最優先）
PR表記必須 / カード条件は公式一次ソースで裏取り＋最終更新日明示 / 景表法・ステマ規制順守 /
投資助言に踏み込まない。詳細は共通フォルダのplaybookと本プロジェクトの「手順」。
