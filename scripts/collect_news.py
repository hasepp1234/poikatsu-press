"""collect_news.py — 日次ニュース収集（計画書 6-1）
対象: ポイントサービス公式のお知らせ / カード会社告知 / 公的情報 / 公開SNS(X)のポイ活話題。
出力: data/news_raw.json（要約前の生収集データ）
方針: 一次ソースへのリンクを必ず保持。丸写しはせず、次段(summarize.py)で独自要約する。
TODO: 監視対象ソースのリストをオーナーから受領して実装（計画書14）。
"""
def main():
    raise NotImplementedError("収集対象ソース確定後に実装（進捗ログ参照）")

if __name__ == "__main__":
    main()
