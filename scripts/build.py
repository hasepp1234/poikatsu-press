"""build.py — 静的サイト生成（計画書 6-5）
data/*.json + templates/*.html → public/ にHTML・sitemap・カテゴリ一覧を生成。
この雛形は最小の疎通確認用: base+index を結合して public/index.html を書き出すだけ。
本実装で news/cards/category/guide 各ページ生成・JSON-LD差し込み・sitemap生成を追加する。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TPL = ROOT / "templates"
OUT = ROOT / "public"

def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

def render(template: str, values: dict) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template

def main():
    news = load("news.json")
    cards = load("cards.json")

    base = (TPL / "base.html").read_text(encoding="utf-8")
    index_block = (TPL / "index.html").read_text(encoding="utf-8")

    news_items = "".join(
        f'<li><a href="/news/{n.get("news_id","")}.html">{n.get("title","")}</a></li>'
        for n in news
    ) or "<li>準備中です。</li>"
    index_block = index_block.replace("<!-- {{NEWS_ITEMS}} -->", news_items)

    card_items = "".join(
        f'<div class="card"><strong>{c.get("name","")}</strong> — {c.get("campaign_points","")}</div>'
        for c in cards
    ) or '<div class="card">クレカ案件を準備中です。</div>'
    index_block = index_block.replace("<!-- {{CARD_ITEMS}} -->", card_items)

    html = render(base, {
        "TITLE": "トップ",
        "DESCRIPTION": "ポイント改悪・新キャンペーン速報と高還元クレカ比較。",
        "CANONICAL": "https://poikatsu-press.com/",
        "OG_TYPE": "website",
        "JSONLD": '{"@context":"https://schema.org","@type":"WebSite","name":"ポイ活PRESS"}',
        "CONTENT": index_block,
    })

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"built: {OUT/'index.html'}  (news={len(news)}, cards={len(cards)})")

if __name__ == "__main__":
    main()
