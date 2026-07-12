"""build.py — 静的サイト生成（計画書 6-5）
data/*.json + templates/*.html → public/ にHTML・sitemap・カテゴリ一覧を生成。

本実装内容:
- public/index.html … トップ（最新ニュース＋注目クレカ）
- public/news/{news_id}.html … 個別ニュース記事（NewsArticle JSON-LD）
- public/cards/index.html … クレカ比較表（ItemList JSON-LD）
- public/category/{category}/index.html … カテゴリ別ニュース一覧
- public/guide/{slug}.html … 入門・最適化ガイド（FAQがあればFAQPage JSON-LD）
- public/sitemap.xml … 上記すべてのURLから動的生成

news_raw.json は検知ログ（下書き前段）のため生成対象外。news.json/cards.json/guides.jsonのみを対象にする。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TPL = ROOT / "templates"
OUT = ROOT / "public"

SITE = "https://poikatsu-press.com"

CATEGORY_LABELS = {
    "kaiaku": "改悪情報",
    "campaign": "新キャンペーン",
    "credit-card": "クレジットカード",
    "qr-pay": "QRコード決済",
    "furusato": "ふるさと納税",
    "point-service": "ポイントサービス",
}


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def render(template: str, values: dict) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def write(path: pathlib.Path, html: str, urls: list, loc: str, lastmod: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    urls.append({"loc": loc, "lastmod": lastmod})


def page(base: str, title: str, description: str, canonical: str, og_type: str, jsonld: dict, content: str) -> str:
    return render(base, {
        "TITLE": title,
        "DESCRIPTION": description,
        "CANONICAL": canonical,
        "OG_TYPE": og_type,
        "JSONLD": json.dumps(jsonld, ensure_ascii=False),
        "CONTENT": content,
    })


def _today():
    import datetime
    return datetime.date.today().isoformat()


def build_index(base, tpl_index, news, cards, urls):
    news_sorted = sorted(news, key=lambda n: n.get("published", ""), reverse=True)[:10]
    news_items = "".join(
        f'<li><a href="/news/{n.get("news_id","")}.html">{n.get("title","")}</a></li>'
        for n in news_sorted
    ) or "<li>準備中です。</li>"

    card_items = "".join(
        f'<div class="card"><strong>{c.get("name","")}</strong> — {c.get("campaign_points","")}</div>'
        for c in cards[:6]
    ) or '<div class="card">クレカ案件を準備中です。</div>'

    content = tpl_index.replace("<!-- {{NEWS_ITEMS}} -->", news_items)
    content = content.replace("<!-- {{CARD_ITEMS}} -->", card_items)

    html = page(base, "トップ", "ポイント改悪・新キャンペーン速報と高還元クレカ比較。",
                f"{SITE}/", "website",
                {"@context": "https://schema.org", "@type": "WebSite", "name": "ポイ活PRESS"},
                content)
    write(OUT / "index.html", html, urls, f"{SITE}/", _today())


def build_news(base, tpl_news, news, urls):
    for n in news:
        news_id = n.get("news_id", "")
        if not news_id:
            continue
        category = n.get("category", "")
        cat_label = CATEGORY_LABELS.get(category, category)
        breadcrumb = f'<a href="/">トップ</a> &gt; <a href="/category/{category}/">{cat_label}</a> &gt; {n.get("title","")}'

        content = render(tpl_news, {
            "BREADCRUMB": breadcrumb,
            "TITLE": n.get("title", ""),
            "PUBLISHED": n.get("published", ""),
            "UPDATED": n.get("updated", n.get("published", "")),
            "CATEGORY": cat_label,
            "SUMMARY": n.get("summary", ""),
            "SOURCE_URL": n.get("source_url", ""),
        })
        content = content.replace("<!-- {{RELATED_CARDS}} -->", "<p>関連クレカ案件は準備中です。</p>")

        jsonld = {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": n.get("title", ""),
            "datePublished": n.get("published", ""),
            "dateModified": n.get("updated", n.get("published", "")),
            "description": n.get("summary", ""),
        }
        canonical = f"{SITE}/news/{news_id}.html"
        html = page(base, n.get("title", ""), n.get("summary", ""), canonical, "article", jsonld, content)
        write(OUT / "news" / f"{news_id}.html", html, urls, canonical, n.get("updated", n.get("published", "")))


def _card_link_cell(c: dict) -> str:
    affiliate_url = c.get("affiliate_url", "")
    official_url = c.get("official_url", "")
    if affiliate_url:
        return (
            f'<a href="{affiliate_url}" rel="nofollow sponsored" target="_blank">'
            f'公式サイトで詳細を見る<span class="pr-tag">PR</span></a>'
        )
    if official_url:
        return f'<a href="{official_url}" rel="nofollow" target="_blank">公式サイトで詳細を見る</a>'
    return "準備中"


def build_cards(base, tpl_cards, cards, urls):
    if cards:
        rows = "".join(
            f'<tr><td>{c.get("name","")}</td><td>{c.get("issuer","")}</td>'
            f'<td>{c.get("campaign_points","")}</td><td>{c.get("annual_fee","")}</td>'
            f'<td>{c.get("base_return_rate","")}</td><td>{c.get("updated","")}</td>'
            f'<td>{_card_link_cell(c)}</td></tr>'
            for c in cards
        )
        table = (
            '<table class="cards-table"><thead><tr>'
            "<th>カード名</th><th>発行会社</th><th>付与ポイント</th><th>年会費</th>"
            "<th>基本還元率</th><th>最終更新日</th><th>詳細</th></tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    else:
        table = "<p>クレカ案件を準備中です。</p>"

    content = tpl_cards.replace("<!-- {{CARDS_TABLE}} Grid.js等で描画 -->", table)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": c.get("name", ""),
                "url": f"{SITE}/cards/#{c.get('slug','')}",
            }
            for i, c in enumerate(cards)
        ],
    }
    canonical = f"{SITE}/cards/"
    html = page(base, "クレジットカード発行キャンペーン比較", "付与ポイント・年会費・条件・還元率でクレカを比較。",
                canonical, "website", jsonld, content)
    write(OUT / "cards" / "index.html", html, urls, canonical, _today())


def build_categories(base, tpl_category, news, urls):
    by_category = {}
    for n in news:
        by_category.setdefault(n.get("category", ""), []).append(n)

    for category, label in CATEGORY_LABELS.items():
        items = sorted(by_category.get(category, []), key=lambda n: n.get("published", ""), reverse=True)
        news_items = "".join(
            f'<li><a href="/news/{n.get("news_id","")}.html">{n.get("title","")}</a></li>'
            for n in items
        ) or "<li>準備中です。</li>"

        content = render(tpl_category, {"CATEGORY_LABEL": label})
        content = content.replace("<!-- {{NEWS_ITEMS}} -->", news_items)

        canonical = f"{SITE}/category/{category}/"
        jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": label}
        html = page(base, label, f"{label}の最新ニュース一覧。", canonical, "website", jsonld, content)
        write(OUT / "category" / category / "index.html", html, urls, canonical, _today())


def _related_cards_html(related_slugs: list, cards_by_slug: dict) -> str:
    items = []
    for slug in related_slugs or []:
        c = cards_by_slug.get(slug)
        if not c:
            continue
        items.append(
            f'<li><a href="/cards/#{slug}">{c.get("name","")}</a> — {c.get("campaign_points","")}</li>'
        )
    if not items:
        return "<p>関連クレカ案件は準備中です。</p>"
    return '<p>関連するクレカ発行キャンペーン:</p><ul class="related-cards-list">' + "".join(items) + "</ul>"


def build_guides(base, tpl_guide, guides, cards, urls):
    cards_by_slug = {c.get("slug", ""): c for c in cards}
    for g in guides:
        slug = g.get("slug", "")
        if not slug:
            continue
        updated = g.get("updated", _today())
        breadcrumb = f'<a href="/">トップ</a> &gt; <a href="/guide/">ガイド</a> &gt; {g.get("title","")}'

        body_html = "".join(f"<p>{line}</p>" for line in g.get("body_md", "").splitlines() if line.strip())

        faq_items = g.get("faq", [])
        if faq_items:
            faq_html = "".join(
                f'<div class="faq-item"><h3>{f.get("q","")}</h3><p>{f.get("a","")}</p></div>'
                for f in faq_items
            )
            jsonld = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f.get("q", ""),
                        "acceptedAnswer": {"@type": "Answer", "text": f.get("a", "")},
                    }
                    for f in faq_items
                ],
            }
        else:
            faq_html = ""
            jsonld = {"@context": "https://schema.org", "@type": "Article", "headline": g.get("title", "")}

        content = render(tpl_guide, {
            "BREADCRUMB": breadcrumb,
            "TITLE": g.get("title", ""),
            "UPDATED": updated,
            "BODY": body_html,
        })
        content = content.replace("<!-- {{FAQ}} LLMO対応FAQ -->", faq_html)
        content = content.replace(
            "<!-- {{RELATED_CARDS}} -->", _related_cards_html(g.get("related_cards", []), cards_by_slug)
        )

        canonical = f"{SITE}/guide/{slug}.html"
        html = page(base, g.get("title", ""), g.get("title", ""), canonical, "article", jsonld, content)
        write(OUT / "guide" / f"{slug}.html", html, urls, canonical, updated)


def build_guide_index(base, guides, urls):
    items = "".join(
        f'<li><a href="/guide/{g.get("slug","")}.html">{g.get("title","")}</a>'
        f'<span class="meta"> 更新日: {g.get("updated","")}</span></li>'
        for g in guides
        if g.get("slug")
    ) or "<li>準備中です。</li>"
    content = (
        '<section class="guide-index"><h1>ガイド一覧</h1>'
        "<p>ポイ活・クレジットカード選びの基本を解説する入門・最適化ガイドです。</p>"
        f'<ul class="guide-list">{items}</ul></section>'
    )
    canonical = f"{SITE}/guide/"
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "ガイド一覧"}
    html = page(base, "ガイド一覧", "ポイ活・クレジットカード選びの基本を解説するガイド記事一覧。",
                canonical, "website", jsonld, content)
    write(OUT / "guide" / "index.html", html, urls, canonical, _today())


def write_sitemap(urls):
    entries = "\n".join(
        f"  <url><loc>{u['loc']}</loc>" + (f"<lastmod>{u['lastmod']}</lastmod>" if u["lastmod"] else "") + "</url>"
        for u in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )
    (OUT / "sitemap.xml").write_text(xml, encoding="utf-8")


def main():
    news = load("news.json")
    cards = load("cards.json")
    guides = load("guides.json")

    base = (TPL / "base.html").read_text(encoding="utf-8")
    tpl_index = (TPL / "index.html").read_text(encoding="utf-8")
    tpl_news = (TPL / "news.html").read_text(encoding="utf-8")
    tpl_cards = (TPL / "cards.html").read_text(encoding="utf-8")
    tpl_category = (TPL / "category.html").read_text(encoding="utf-8")
    tpl_guide = (TPL / "guide.html").read_text(encoding="utf-8")

    OUT.mkdir(exist_ok=True)
    urls = []

    build_index(base, tpl_index, news, cards, urls)
    build_news(base, tpl_news, news, urls)
    build_cards(base, tpl_cards, cards, urls)
    build_categories(base, tpl_category, news, urls)
    build_guides(base, tpl_guide, guides, cards, urls)
    build_guide_index(base, guides, urls)
    write_sitemap(urls)

    print(
        f"built: index=1, news={len(news)}, cards_page=1, categories={len(CATEGORY_LABELS)}, "
        f"guides={len(guides)}, sitemap_urls={len(urls)}"
    )


if __name__ == "__main__":
    main()
