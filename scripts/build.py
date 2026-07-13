"""build.py — 静的サイト生成（計画書 6-5）
data/*.json + templates/*.html → public/ にHTML・sitemap・カテゴリ一覧を生成。

本実装内容:
- public/index.html … トップ（全体サマリ→TOPニュース→各種キャンペーン→お得商品→改悪情報の1ページダイジェスト、2026-07-13改訂）
  TOPニュース・お得商品・改悪情報はインフルエンサー起点かつ元Xツイート投稿から24時間以内のみ表示（2026-07-14変更）
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

# TOPニュース／お得商品／改悪情報は「元Xツイート投稿時刻(source_posted_at)」基準で
# 直近FRESHNESS_WINDOW_HOURS時間以内・source_type=="influencer"のものだけを表示する
# （2026-07-14追加。ユーザー要望によりTOPページの3セクションをインフルエンサー起点の
# 24時間以内情報に限定）
FRESHNESS_WINDOW_HOURS = 24


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


def _parse_iso_datetime(s):
    """ISO 8601文字列（末尾Z許容）をtz付きdatetimeに変換。パース不可ならNone"""
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _is_fresh(posted_at_str, hours=FRESHNESS_WINDOW_HOURS):
    """source_posted_at（元Xツイート投稿時刻）が直近hours時間以内かどうか"""
    dt = _parse_iso_datetime(posted_at_str)
    if not dt:
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    return datetime.timedelta(0) <= (now - dt) <= datetime.timedelta(hours=hours)


def _is_influencer_fresh(item, hours=FRESHNESS_WINDOW_HOURS):
    """TOPニュース／お得商品／改悪情報共通の掲載条件:
    インフルエンサー起点（source_type=="influencer" もしくはdeals.jsonのsource_account設定）
    かつ元ツイートの投稿時刻がhours時間以内であること"""
    is_influencer = item.get("source_type") == "influencer" or bool(item.get("source_account"))
    return is_influencer and _is_fresh(item.get("source_posted_at"), hours)


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


def _campaign_group_html(cards_list, kind=""):
    """kind: "new" / "ending" / ""(進行中)。カード左のアクセント色分けに使う（2026-07-14追加）"""
    if not cards_list:
        return "<p>該当するキャンペーンは現在ありません。</p>"
    css_class = f"campaign-item campaign-item--{kind}" if kind else "campaign-item"
    return "".join(
        f'<div class="{css_class}"><strong><a href="/cards/#{c.get("slug","")}">{c.get("name","")}</a></strong> '
        f'— {c.get("campaign_points","")} <span class="meta">（{c.get("updated","")}時点）</span></div>'
        for c in cards_list
    )


def _top_news_html(news):
    # B方式（2026-07-14確定）: featuredフラグは人が手動で立てる編集判断を維持しつつ、
    # 元Xツイートから24時間経過したら自動的にTOPから外れる（準備中表示に戻る）
    featured = [n for n in news if n.get("featured") and _is_influencer_fresh(n)]
    featured.sort(key=lambda n: n.get("source_posted_at", ""), reverse=True)
    if not featured:
        return "<p>準備中です。直近24時間以内の注目トピックが見つかり次第掲載します。</p>"
    n = featured[0]
    return (
        f'<div class="top-news-item"><a href="/news/{n.get("news_id","")}.html">'
        f'<strong>{n.get("title","")}</strong></a><p>{n.get("summary","")}</p></div>'
    )


def _kaiaku_items_html(news):
    items = [n for n in news if n.get("category") == "kaiaku" and _is_influencer_fresh(n)]
    if not items:
        return "<li>直近24時間の改悪情報はありません。</li>"
    items.sort(key=lambda n: n.get("source_posted_at", ""), reverse=True)
    return "".join(
        f'<li><span class="meta">{n.get("published","")[:10]}</span> '
        f'<a href="/news/{n.get("news_id","")}.html">{n.get("title","")}</a></li>'
        for n in items
    )


def _deals_items_html(deals):
    items = [d for d in deals if _is_influencer_fresh(d)]
    if not items:
        return "<p>準備中です。直近24時間以内のお得商品が見つかり次第掲載します。</p>"
    items.sort(key=lambda d: d.get("source_posted_at", ""), reverse=True)
    rendered = []
    for d in items:
        affiliate = d.get("is_affiliate")
        rel = "nofollow sponsored" if affiliate else "nofollow"
        pr = '<span class="pr-tag">PR</span>' if affiliate else ""
        rendered.append(
            f'<div class="deal-item"><a href="{d.get("url","")}" rel="{rel}" target="_blank">'
            f'{d.get("title","")}</a>{pr}<p>{d.get("description","")}</p></div>'
        )
    return "".join(rendered)


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
    content = content.replace("<!-- {{CAMPAIGNS_NEW}} -->", _campaign_group_html(new_list, "new"))
    content = content.replace("<!-- {{CAMPAIGNS_ONGOING}} -->", _campaign_group_html(ongoing_list))
    content = content.replace("<!-- {{CAMPAIGNS_ENDING}} -->", _campaign_group_html(ending_list, "ending"))
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
            f'<a class="btn-outline" href="{affiliate_url}" rel="nofollow sponsored" target="_blank">'
            f'公式サイトで詳細を見る<span class="pr-tag">PR</span></a>'
        )
    if official_url:
        return f'<a class="btn-outline" href="{official_url}" rel="nofollow" target="_blank">公式サイトで詳細を見る</a>'
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
            f'{_campaign_group_html(new_list, "new")}</div></div>'
            '<div class="campaign-group"><h3>進行中キャンペーン</h3><div class="campaign-list">'
            f'{_campaign_group_html(ongoing_list)}</div></div>'
            '<div class="campaign-group"><h3>終了間近キャンペーン</h3><div class="campaign-list">'
            f'{_campaign_group_html(ending_list, "ending")}</div></div>'
        )
    elif category == "kaiaku":
        # 2026-07-14修正: CSSは#kaiaku-items（ID）を参照しているため、従来の
        # class="kaiaku-items"ではスタイルが当たらないバグがあった。idに統一
        body = f'<ul id="kaiaku-items">{_kaiaku_items_html(news)}</ul>'
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


def _official_link_cell(url):
    if not url:
        return "準備中"
    return f'<a class="btn-outline" href="{url}" rel="nofollow" target="_blank">公式サイトを見る</a>'


def build_qr_pay_page(base, tpl_qr_pay, qr_pay, urls):
    if qr_pay:
        rows = "".join(
            f'<tr><td>{s.get("name","")}</td><td>{s.get("operator","")}</td>'
            f'<td>{s.get("campaign_points","")}</td><td>{s.get("base_return_rate","")}</td>'
            f'<td>{s.get("updated","")}</td><td>{_official_link_cell(s.get("official_url",""))}</td></tr>'
            for s in qr_pay
        )
        table = (
            '<table class="cards-table"><thead><tr>'
            "<th>サービス名</th><th>運営会社</th><th>現在のキャンペーン</th>"
            "<th>基本還元率</th><th>最終更新日</th><th>詳細</th></tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    else:
        table = "<p>QR決済サービスの情報を準備中です。</p>"

    content = tpl_qr_pay.replace("<!-- {{QR_PAY_TABLE}} -->", table)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": s.get("name", ""), "url": s.get("official_url", "")}
            for i, s in enumerate(qr_pay)
        ],
    }
    canonical = f"{SITE}/qr-pay/"
    html = page(base, "QRコード決済比較", "主要QR決済サービスの基本還元率・キャンペーンを比較。",
                canonical, "website", jsonld, content)
    write(OUT / "qr-pay" / "index.html", html, urls, canonical, _today())


def build_furusato_page(base, tpl_furusato, furusato, urls):
    if furusato:
        rows = "".join(
            f'<tr><td>{s.get("name","")}</td><td>{s.get("operator","")}</td>'
            f'<td>{s.get("campaign_points","")}</td><td>{s.get("features","")}</td>'
            f'<td>{s.get("updated","")}</td><td>{_official_link_cell(s.get("official_url",""))}</td></tr>'
            for s in furusato
        )
        table = (
            '<table class="cards-table"><thead><tr>'
            "<th>サイト名</th><th>運営会社</th><th>現在の特典・キャンペーン</th>"
            "<th>特徴</th><th>最終更新日</th><th>詳細</th></tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    else:
        table = "<p>ふるさと納税サイトの情報を準備中です。</p>"

    content = tpl_furusato.replace("<!-- {{FURUSATO_TABLE}} -->", table)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": s.get("name", ""), "url": s.get("official_url", "")}
            for i, s in enumerate(furusato)
        ],
    }
    canonical = f"{SITE}/furusato/"
    html = page(base, "ふるさと納税サイト比較", "主要ふるさと納税サイトの特徴・キャンペーンを比較。",
                canonical, "website", jsonld, content)
    write(OUT / "furusato" / "index.html", html, urls, canonical, _today())


def build_deals_page(base, deals, urls):
    page_date = _page_date_label()
    today_iso = _today()
    content = (
        '<section class="deals-page"><h1>お得商品</h1>'
        '<p class="note">Amazon・楽天などでインフルエンサーが特に推している商品や、期間限定の割引情報を'
        'ピックアップします。掲載時は自社のアフィリエイトリンクを使用し、該当する場合はPR表記を付けます。'
        '元の投稿から24時間以内の情報のみ掲載しています。</p>'
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


CONTACT_FORM_URL = "https://forms.gle/AtPvyEsJBuVMjCvf9"


def build_static_pages(base, urls):
    """about/contact/privacy … footer固定リンクの3ページ（2026-07-13追加・課題#23対応）。
    データファイルを持たない静的ページのため、本文はここに直書きする。
    個人名・個人メールアドレスは掲載しない（問い合わせはGoogleフォーム経由に統一）。
    """
    today_iso = _today()

    about_content = (
        '<section class="static-page"><h1>運営者情報</h1>'
        "<p>「ポイ活PRESS」（poikatsu-press.com）は、クレジットカード・QRコード決済・"
        "ふるさと納税・お得なキャンペーン情報など、ポイ活に関する情報を整理してお届けする"
        "情報メディアです。公式サイト等の一次情報を確認のうえ、内容を整理して掲載しています。</p>"
        '<table class="info-table">'
        "<tr><th>サイト名</th><td>ポイ活PRESS</td></tr>"
        "<tr><th>運営者</th><td>ポイ活PRESS運営事務局</td></tr>"
        f'<tr><th>サイトURL</th><td><a href="{SITE}/">{SITE}/</a></td></tr>'
        "<tr><th>運営開始</th><td>2026年7月</td></tr>"
        '<tr><th>お問い合わせ</th><td><a href="/contact/">お問い合わせページ</a>よりご連絡ください</td></tr>'
        "</table>"
        "<h2>掲載情報について</h2>"
        "<p>価格・還元率・キャンペーン期間などの数値情報は、可能な限り公式一次ソースを確認したうえで"
        "掲載日時点の情報として掲載しています。内容は予告なく変更される場合がありますので、"
        "お申し込み等の際は必ず各社公式サイトで最新情報をご確認ください。</p>"
        "<h2>広告・アフィリエイトについて</h2>"
        "<p>当サイトはアフィリエイト広告を利用しており、掲載リンクを経由した申込み・購入等により"
        "当サイトに成果報酬が発生する場合があります。該当する箇所には「PR」を明示しています。"
        "広告の有無にかかわらず、内容の評価や紹介順位を恣意的に操作することはありません。</p>"
        "</section>"
    )
    canonical = f"{SITE}/about/"
    jsonld = {"@context": "https://schema.org", "@type": "AboutPage", "name": "運営者情報"}
    html = page(base, "運営者情報", "ポイ活PRESSの運営者情報・サイトの目的についてご案内します。",
                canonical, "website", jsonld, about_content)
    write(OUT / "about" / "index.html", html, urls, canonical, today_iso)

    contact_content = (
        '<section class="static-page"><h1>お問い合わせ</h1>'
        "<p>ポイ活PRESSに関するお問い合わせ・掲載情報の誤り等のご指摘は、下記のGoogleフォームより"
        "お願いいたします。内容を確認のうえ、必要に応じてご連絡いたします。"
        "（個人情報保護のため、メールアドレスの直接掲載は行っておりません）</p>"
        f'<p><a class="contact-form-link" href="{CONTACT_FORM_URL}" target="_blank" '
        'rel="noopener">お問い合わせフォームを開く</a></p>'
        "</section>"
    )
    canonical = f"{SITE}/contact/"
    jsonld = {"@context": "https://schema.org", "@type": "ContactPage", "name": "お問い合わせ"}
    html = page(base, "お問い合わせ", "ポイ活PRESSへのお問い合わせはこちらのフォームからお願いいたします。",
                canonical, "website", jsonld, contact_content)
    write(OUT / "contact" / "index.html", html, urls, canonical, today_iso)

    privacy_content = (
        '<section class="static-page"><h1>プライバシーポリシー</h1>'
        f'<p class="meta">最終更新日: {today_iso}</p>'
        "<p>「ポイ活PRESS」（以下「当サイト」）は、利用者の個人情報の取り扱いについて、"
        "以下のとおりプライバシーポリシーを定めます。</p>"
        "<h2>個人情報の収集について</h2>"
        "<p>当サイトでは、お問い合わせの際にお名前・メールアドレス等の情報をGoogleフォーム経由で"
        "ご提供いただく場合があります。取得した情報は、お問い合わせへの対応以外の目的では利用いたしません。</p>"
        "<h2>アクセス解析ツールについて</h2>"
        "<p>当サイトは、利用状況を把握するためGoogle アナリティクス（GA4）を利用しています。"
        "このツールはトラフィックデータの収集のためにCookieを使用しますが、収集は匿名で行われ、"
        "個人を特定するものではありません。</p>"
        "<h2>広告の配信について（Google アドセンス）</h2>"
        "<p>当サイトは、第三者配信の広告サービス「Google アドセンス」を利用しています。"
        "広告配信事業者は、利用者の興味に応じた広告を表示するためにCookieを使用することがあります。"
        "Cookieを無効にする設定や、Google アドセンスに関する詳細については、"
        '<a href="https://policies.google.com/technologies/ads?hl=ja" target="_blank" '
        'rel="noopener">Googleの広告ポリシーページ</a>をご覧ください。</p>'
        "<h2>アフィリエイトプログラムについて</h2>"
        "<p>当サイトは、クレジットカード会社・ASP（アフィリエイトサービスプロバイダ）等との"
        "アフィリエイトプログラム（成果報酬型広告）に参加しています。掲載リンクを経由して"
        "申込み・購入等が行われた場合、当サイトに成果報酬が支払われることがありますが、"
        "これによって利用者が負担する金額が変わることはありません。該当箇所には「PR」を明示しています。</p>"
        "<h2>掲載情報の正確性について</h2>"
        "<p>当サイトに掲載する価格・還元率・キャンペーン条件等は、公式一次ソースを確認のうえ"
        "掲載時点の情報として記載していますが、内容は予告なく変更される場合があります。"
        "最新情報は必ず各社公式サイトでご確認ください。内容に誤りがあった場合は速やかに訂正いたします。</p>"
        "<h2>プライバシーポリシーの変更について</h2>"
        "<p>当サイトは、必要に応じて本ポリシーの内容を変更することがあります。"
        "変更後のプライバシーポリシーは、当ページに掲載した時点から効力を生じるものとします。</p>"
        "<h2>お問い合わせ</h2>"
        '<p>本ポリシーに関するお問い合わせは、<a href="/contact/">お問い合わせページ</a>よりお願いいたします。</p>'
        "</section>"
    )
    canonical = f"{SITE}/privacy/"
    jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": "プライバシーポリシー"}
    html = page(base, "プライバシーポリシー", "ポイ活PRESSのプライバシーポリシー。",
                canonical, "website", jsonld, privacy_content)
    write(OUT / "privacy" / "index.html", html, urls, canonical, today_iso)


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
    qr_pay = load("qr_pay.json")
    furusato = load("furusato.json")
    summary = load_obj("summary.json", {"summary_text": "", "updated": ""})

    base = (TPL / "base.html").read_text(encoding="utf-8")
    tpl_index = (TPL / "index.html").read_text(encoding="utf-8")
    tpl_news = (TPL / "news.html").read_text(encoding="utf-8")
    tpl_cards = (TPL / "cards.html").read_text(encoding="utf-8")
    tpl_category = (TPL / "category.html").read_text(encoding="utf-8")
    tpl_guide = (TPL / "guide.html").read_text(encoding="utf-8")
    tpl_qr_pay = (TPL / "qr_pay.html").read_text(encoding="utf-8")
    tpl_furusato = (TPL / "furusato.html").read_text(encoding="utf-8")

    OUT.mkdir(exist_ok=True)
    urls = []

    build_index(base, tpl_index, news, cards, deals, summary, urls)
    build_news(base, tpl_news, news, urls)
    build_cards(base, tpl_cards, cards, urls)
    build_categories(base, tpl_category, news, cards, urls)
    build_deals_page(base, deals, urls)
    build_qr_pay_page(base, tpl_qr_pay, qr_pay, urls)
    build_furusato_page(base, tpl_furusato, furusato, urls)
    build_guides(base, tpl_guide, guides, cards, urls)
    build_guide_index(base, guides, urls)
    build_static_pages(base, urls)
    write_sitemap(urls)

    print(
        f"built: index=1, news={len(news)}, cards_page=1, categories={len(CATEGORY_LABELS)}, "
        f"guides={len(guides)}, deals={len(deals)}, qr_pay={len(qr_pay)}, furusato={len(furusato)}, "
        f"sitemap_urls={len(urls)}"
    )


if __name__ == "__main__":
    main()
