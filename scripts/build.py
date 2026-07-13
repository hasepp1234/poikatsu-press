"""build.py — 静的サイト生成（計画書 6-5）
data/*.json + templates/*.html → public/ にHTML・sitemap・カテゴリ一覧を生成。

本実装内容:
- public/index.html … トップ（全体サマリ→TOPニュース→各種キャンペーン→お得商品→改悪情報の1ページダイジェスト、2026-07-13改訂）
- public/news/{news_id}.html … 個別ニュース記事（NewsArticle JSON-LD）
- public/cards/index.html … クレカ比較表（ItemList JSON-LD）
- public/category/{category}/index.html … カテゴリ別ニュース一覧
- public/guide/{slug}.html … 入門・最適化ガイド（FAQがあればFAQPage JSON-LD）
- public/guide/index.html … ガイド一覧
- public/sitemap.xml … 上記すべてのURLから動的生成

news_raw.json は検知ログ（下書き前段）のため生成対象外。news.json/cards.json/guides.json/deals.json/summary.jsonを対象にする。
"""
import datetime
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

NEW_CAMPAIGN_WINDOW_DAYS = 7
ENDING_SOON_WINDOW_DAYS = 7
KAIAKU_WINDOW_DAYS = 30


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def load_obj(name, default=None):
    p = DATA / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default or {}


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
    return datetime.date.today().isoformat()


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def classify_campaigns(cards):
    """cards.jsonのcampaign_start/campaign_endから新規/進行中/終了間近を分類する（2026-07-13追加）。
    - campaign_pointsに「特典なし」を含むカードは対象外（/cards/の比較表には引き続き掲載）
    - campaign_endがあり、今日から0〜ENDING_SOON_WINDOW_DAYS日以内 → 終了間近（既に終了した分は除外）
    - 上記に該当せずcampaign_startがあり、開始から0〜NEW_CAMPAIGN_WINDOW_DAYS日以内 → 新規
    - それ以外の特典ありカード → 進行中
    """
    today = datetime.date.today()
    new_list, ongoing_list, ending_list = [], [], []
    for c in cards:
        if "特典なし" in c.get("campaign_points", ""):
            continue
        start = _parse_date(c.get("campaign_start", ""))
        end = _parse_date(c.get("campaign_end", ""))
        if end:
            days_left = (end - today).days
            if 0 <= days_left <= ENDING_SOON_WINDOW_DAYS:
                ending_list.append(c)
                continue
            if days_left < 0:
                continue
        if start:
            days_since_start = (today - start).days
            if 0 <= days_since_start <= NEW_CAMPAIGN_WINDOW_DAYS:
                new_list.append(c)
                continue
        ongoing_list.append(c)
    return new_list, ongoing_list, ending_list


def _campaign_group_html(cards_list):
    if not cards_list:
        return "<p>該当するキャンペーンは現在ありません。</p>"
    return "".join(
        f'<div class="campaign-item"><strong><a href="/cards/#{c.get("slug","")}">{c.get("name","")}</a></strong> '
        f'— {c.get("campaign_points","")} <span class="meta">（{c.get("updated","")}時点）</span></div>'
        for c in cards_list
    )


def _top_news_html(news):
    featured = [n for n in news if n.get("featured")]
    featured.sort(key=lambda n: n.get("published", ""), reverse=True)
    if not featured:
        return "<p>準備中です。注目トピックが見つかり次第掲載します。</p>"
    n = featured[0]
    return (
        f'<div class="top-news-item"><a href="/news/{n.get("news_id","")}.html">'
        f'<strong>{n.get("title","")}</strong></a><p>{n.get("summary","")}</p></div>'
    )


def _kaiaku_items_html(news):
    today = datetime.date.today()
    items = []
    for n in news:
        if n.get("category") != "kaiaku":
            continue
        pub = _parse_date((n.get("published") or "")[:10])
        if not pub or (today - pub).days > KAIAKU_WINDOW_DAYS:
            continue
        items.append(n)
    if not items:
        return "<li>直近30日の改悪情報はありません。</li>"
    items.sort(key=lambda n: n.get("published", ""), reverse=True)
    return "".join(
        f'<li><span class="meta">{n.get("published","")[:10]}</span> '
        f'<a href="/news/{n.get("news_id","")}.html">{n.get("title","")}</a></li>'
        for n in items
    )


def _deals_items_html(deals):
    if not deals:
        return "<p>準備中です。おすすめ商品が見つかり次第掲載します。</p>"
    items = []
    for d in deals:
        affiliate = d.get("is_affiliate")
        rel = "nofollow sponsored" if affiliate else "nofollow"
        pr = '<span class="pr-tag">PR</span>' if affiliate else ""
        items.append(
            f'<div class="deal-item"><a href="{d.get("url","")}" rel="{rel}" target="_blank">'
            f'{d.get("title","")}</a>{pr}<p>{d.get("description","")}</p></div>'
        )
    return "".join(items)


def _page_date_label():
    today = datetime.date.today()
    return f"{today.month}/{today.day}"


def _parse_backnumber_date(stem):
    if stem == "index":
        return None
    return _parse_date(stem)


def _date_to_label(date_str):
    d = _parse_date(date_str)
    return f"{d.month}/{d.day}" if d else date_str


def _list_backnumber_dates():
    dir_path = OUT / "backnumber"
    if not dir_path.exists():
        return []
    dates = [p.stem for p in dir_path.glob("*.html") if _parse_backnumber_date(p.stem)]
    return sorted(dates, reverse=True)


def build_backnumber_index(base, urls):
    dates = _list_backnumber_dates()
    if dates:
        items = "".join(
            f'<li><a href="/backnumber/{d}.html">{_date_to_label(d)}版</a><span class="meta"> {d}</span></li>'
            for d in dates
        )
    else:
        items = "<li>準備中です。</li>"
    content = (
        '<section class="backnumber-index"><h1>バックナンバー一覧</h1>'
        '<p>過去に公開したポイ活PRESSのダイジェストです。最新情報は<a href="/">トップページ</a>をご覧ください。</p>'
        f'<ul class="backnumber-list">{items}</ul></section>'
    )
    canonical = f"{SITE}/backnumber/"
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "バックナンバー一覧"}
    html = page(base, "バックナンバー一覧", "過去に公開したポイ活PRESSのダイジェスト一覧。",
                canonical, "website", jsonld, content)
    write(OUT / "backnumber" / "index.html", html, urls, canonical, _today())


def build_index(base, tpl_index, news, cards, deals, summary, urls):
    new_list, ongoing_list, ending_list = classify_campaigns(cards)
    page_date = _page_date_label()
    today_iso = _today()

    content = tpl_index.replace("{{PAGE_DATE}}", page_date)
    content = content.replace("<!-- {{SUMMARY_TEXT}} -->", f'<p>{summary.get("summary_text","")}</p>')
    content = content.replace("{{SUMMARY_UPDATED}}", summary.get("updated", ""))
    content = content.replace("<!-- {{TOP_NEWS}} -->", _top_news_html(news))
    content = content.replace("<!-- {{CAMPAIGNS_NEW}} -->", _campaign_group_html(new_list))
    content = content.replace("<!-- {{CAMPAIGNS_ONGOING}} -->", _campaign_group_html(ongoing_list))
    content = content.replace("<!-- {{CAMPAIGNS_ENDING}} -->", _campaign_group_html(ending_list))
    content = content.replace("<!-- {{DEALS_ITEMS}} -->", _deals_items_html(deals))
    content = content.replace("<!-- {{KAIAKU_ITEMS}} -->", _kaiaku_items_html(news))

    content_live = content.replace("<!-- {{BACKNUMBER_NOTICE}} -->", "")
    backnumber_notice = (
        f'<p class="backnumber-notice">このページは過去のバックナンバー（{page_date}版）です。'
        f'最新情報は<a href="/">トップページ</a>をご覧ください。</p>'
    )
    content_archive = content.replace("<!-- {{BACKNUMBER_NOTICE}} -->", backnumber_notice)

    jsonld = {"@context": "https://schema.org", "@type": "WebSite", "name": "ポイ活PRESS"}

    html_live = page(base, "トップ", "ポイント改悪・新キャンペーン速報と高還元クレカ比較を1ページで。",
                      f"{SITE}/", "website", jsonld, content_live)
    write(OUT / "index.html", html_live, urls, f"{SITE}/", today_iso)

    # バックナンバー保存: 同日中の再ビルドは同一ファイル（今日の日付）を上書きするだけなので
    # 重複ファイルは発生しない。日付が変わって初めて新しいバックナンバーが1件増える
    backnumber_canonical = f"{SITE}/backnumber/{today_iso}.html"
    html_archive = page(base, f"{page_date}版バックナンバー",
                         f"ポイ活PRESS {page_date}版のバックナンバー（アーカイブ）。",
                         backnumber_canonical, "article", jsonld, content_archive)
    write(OUT / "backnumber" / f"{today_iso}.html", html_archive, urls, backnumber_canonical, today_iso)

    build_backnumber_index(base, urls)


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


def _latest_digest_html(category, news, cards, page_date, today_iso):
    # 案A（2026-07-13確定）: 新キャンペーン／改悪情報のカテゴリページ先頭に、
    # トップページ（最新号 x/x版）の該当セクションをそのまま転載する
    if category == "campaign":
        new_list, ongoing_list, ending_list = classify_campaigns(cards)
        body = (
            '<div class="campaign-group"><h3>新キャンペーン</h3><div class="campaign-list">'
            f'{_campaign_group_html(new_list)}</div></div>'
            '<div class="campaign-group"><h3>進行中キャンペーン</h3><div class="campaign-list">'
            f'{_campaign_group_html(ongoing_list)}</div></div>'
            '<div class="campaign-group"><h3>終了間近キャンペーン</h3><div class="campaign-list">'
            f'{_campaign_group_html(ending_list)}</div></div>'
        )
    elif category == "kaiaku":
        body = f'<ul class="kaiaku-items">{_kaiaku_items_html(news)}</ul>'
    else:
        return ""

    return (
        f'<section class="latest-digest"><h2>最新号（{page_date}版）の内容</h2>'
        f'{body}'
        f'<p class="meta">出典: <a href="/backnumber/{today_iso}.html">{page_date}版バックナンバー</a></p>'
        '</section>'
    )


def build_categories(base, tpl_category, news, cards, urls):
    by_category = {}
    for n in news:
        by_category.setdefault(n.get("category", ""), []).append(n)

    page_date = _page_date_label()
    today_iso = _today()

    for category, label in CATEGORY_LABELS.items():
        items = sorted(by_category.get(category, []), key=lambda n: n.get("published", ""), reverse=True)
        news_items = "".join(
            f'<li><a href="/news/{n.get("news_id","")}.html">{n.get("title","")}</a></li>'
            for n in items
        ) or "<li>準備中です。</li>"

        content = render(tpl_category, {"CATEGORY_LABEL": label})
        content = content.replace(
            "<!-- {{LATEST_DIGEST}} -->", _latest_digest_html(category, news, cards, page_date, today_iso)
        )
        content = content.replace("<!-- {{NEWS_ITEMS}} -->", news_items)

        canonical = f"{SITE}/category/{category}/"
        jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": label}
        html = page(base, label, f"{label}の最新ニュース一覧。", canonical, "website", jsonld, content)
        write(OUT / "category" / category / "index.html", html, urls, canonical, _today())


def build_deals_page(base, deals, urls):
    page_date = _page_date_label()
    today_iso = _today()
    content = (
        '<section class="deals-page"><h1>お得商品</h1>'
        '<p class="note">Amazon・楽天などでインフルエンサーが特に推している商品や、期間限定の割引情報を'
        'ピックアップします。掲載時は自社のアフィリエイトリンクを使用し、該当する場合はPR表記を付けます。</p>'
        f'<h2>最新号（{page_date}版）の内容</h2>'
        f'<div id="deals-list">{_deals_items_html(deals)}</div>'
        f'<p class="meta">出典: <a href="/backnumber/{today_iso}.html">{page_date}版バックナンバー</a></p>'
        '</section>'
    )
    canonical = f"{SITE}/deals/"
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "お得商品"}
    html = page(base, "お得商品", "Amazon・楽天などのお得な商品・キャンペーン情報一覧。",
                canonical, "website", jsonld, content)
    write(OUT / "deals" / "index.html", html, urls, canonical, today_iso)


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
    deals = load("deals.json")
    summary = load_obj("summary.json", {"summary_text": "", "updated": ""})

    base = (TPL / "base.html").read_text(encoding="utf-8")
    tpl_index = (TPL / "index.html").read_text(encoding="utf-8")
    tpl_news = (TPL / "news.html").read_text(encoding="utf-8")
    tpl_cards = (TPL / "cards.html").read_text(encoding="utf-8")
    tpl_category = (TPL / "category.html").read_text(encoding="utf-8")
    tpl_guide = (TPL / "guide.html").read_text(encoding="utf-8")

    OUT.mkdir(exist_ok=True)
    urls = []

    build_index(base, tpl_index, news, cards, deals, summary, urls)
    build_news(base, tpl_news, news, urls)
    build_cards(base, tpl_cards, cards, urls)
    build_categories(base, tpl_category, news, cards, urls)
    build_deals_page(base, deals, urls)
    build_guides(base, tpl_guide, guides, cards, urls)
    build_guide_index(base, guides, urls)
    write_sitemap(urls)

    print(
        f"built: index=1, news={len(news)}, cards_page=1, categories={len(CATEGORY_LABELS)}, "
        f"guides={len(guides)}, deals={len(deals)}, sitemap_urls={len(urls)}"
    )


if __name__ == "__main__":
    main()
