"""summarize.py — Claude APIで中立・簡潔な要約を生成（計画書 6-2）

前提となる裏取りフロー（重要・コンプライアンス）:
- collect_news.py が data/news_raw.json に status=pending_verification で検知ログを書き出す。
- そのままこのスクリプトでnews.jsonに反映することはしない。
  検知したツイートは「速報のきっかけ」に過ぎず、記事化には各社公式発表（プレスリリース／
  公式サイトのお知らせ）での裏取りが必須（playbook・台帳のコンプライアンスルール準拠）。
- 人が data/news_raw.json の該当項目に "official_source_url"（公式一次ソースURL）を追記し、
  status を "verified" に変更する。このスクリプトは status=="verified" かつ
  official_source_url が入っている項目のみを処理対象にする。
- Claude APIには元投稿の文章ではなく、公式ソースURLと検知の要点（キーワード等）を渡し、
  断定的・誇大な表現を避けた中立的な要約を生成させる（丸写し禁止）。
- 生成した記事は news.json に追記し、news_raw.json 側は status="published" に更新して
  二重反映を防ぐ。

認証情報:
- APIキーは環境変数 ANTHROPIC_API_KEY から読む（推奨）。
- ローカル実行の利便性のため、環境変数が無い場合のみ
  poikatsu-press/secrets/secrets_claude_api.md から読む（Git非公開ファイル）。

入力: data/news_raw.json（status=="verified" の項目）
出力: data/news.json（追記）、data/news_raw.json（status更新）

TOPページ掲載条件（2026-07-14追加）:
- news.jsonの各記事にはsource_type="influencer"・source_account（news_raw.jsonのaccount_handle）・
  source_posted_at（news_raw.jsonのcreated_at＝元Xツイート投稿時刻）を自動で引き継ぐ。
- build.pyはsource_posted_atが直近24時間以内の記事のみをTOPニュース／改悪情報欄に表示する。
- featuredはデフォルトfalseで生成される。TOPニュース欄に出したい記事があれば、生成後に
  news.jsonの該当項目のfeaturedを手動でtrueに変更すること（24時間を過ぎると自動的に非表示に戻る）。
"""
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SECRETS_MD = ROOT / "secrets" / "secrets_claude_api.md"

RAW_FILE = DATA / "news_raw.json"
NEWS_FILE = DATA / "news.json"

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"  # 最新の安価モデル（2026-07-11時点）。コスト最適重視

CATEGORY_KEYWORDS = {
    "kaiaku": ["改悪", "改定", "上限", "廃止", "終了"],
    "campaign": ["新キャンペーン", "キャンペーン", "新登場", "増量"],
    "credit-card": ["クレジットカード", "クレカ", "年会費"],
    "qr-pay": ["paypay", "楽天ペイ", "d払い", "au pay", "qr決済"],
    "furusato": ["ふるさと納税"],
    "point-service": ["ポイント還元", "付与率", "還元率"],
}

SYSTEM_PROMPT = (
    "あなたはポイ活・キャッシュレス決済の情報メディア「ポイ活PRESS」の編集者です。"
    "与えられた公式発表の内容をもとに、断定的・誇大な表現を避けた中立的で簡潔な日本語の"
    "ニュース要約を作成してください。景品表示法・ステマ規制に配慮し、事実のみを述べてください。"
    "出力は必ず次のJSON形式のみで返してください（説明文やコードブロック記法は不要）: "
    '{"title": "見出し(40字程度)", "summary": "要約(150字程度)", "tags": ["タグ1","タグ2"]}'
)


def load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    if SECRETS_MD.exists():
        text = SECRETS_MD.read_text(encoding="utf-8")
        m = re.search(r"## APIキー\n(.+)", text)
        if m:
            return m.group(1).strip()
    raise RuntimeError(
        "Claude APIキーが見つかりません。環境変数 ANTHROPIC_API_KEY を設定するか、"
        "secrets/secrets_claude_api.md を確認してください。"
    )


def load_json(path: pathlib.Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: pathlib.Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def guess_category(text: str) -> str:
    lower = text.lower()
    for category, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in lower:
                return category
    return "point-service"


def call_claude(api_key: str, matched_keywords: list[str], official_source_url: str) -> dict:
    user_content = (
        "以下の公式発表URLの内容にもとづいて、記事の見出し・要約・タグ案を作成してください。\n"
        f"公式ソースURL: {official_source_url}\n"
        f"検知のきっかけとなったキーワード: {', '.join(matched_keywords)}\n"
        "注意: 元のURL先の内容を実際に確認できない場合は、キーワードから推測せず、"
        '"summary"に「公式発表の内容を編集部で確認のうえ執筆してください」という'
        "編集者向けの注記を含めてください。"
    )
    body = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 500,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    text = payload["content"][0]["text"]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # モデルがJSON以外を返した場合のフォールバック
        return {"title": text[:40], "summary": text[:150], "tags": []}


def main() -> None:
    api_key = load_api_key()
    raw_items = load_json(RAW_FILE, [])
    news_items = load_json(NEWS_FILE, [])
    existing_ids = {n.get("news_id") for n in news_items}

    targets = [
        item
        for item in raw_items
        if item.get("status") == "verified" and item.get("official_source_url")
    ]

    if not targets:
        print(
            "処理対象がありません。data/news_raw.json の項目に official_source_url を追記し、"
            'status を "verified" にしてから再実行してください。'
        )
        return

    created = 0
    for item in targets:
        news_id = f"news_{item['tweet_id']}"
        if news_id in existing_ids:
            item["status"] = "published"
            continue

        result = call_claude(api_key, item.get("matched_keywords", []), item["official_source_url"])
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        news_items.append(
            {
                "news_id": news_id,
                "title": result.get("title", ""),
                "summary": result.get("summary", ""),
                "category": guess_category(" ".join(item.get("matched_keywords", []))),
                "tags": result.get("tags", []),
                "source_url": item["official_source_url"],
                "source_type": "influencer",
                "source_account": item.get("account_handle", ""),
                "source_posted_at": item.get("created_at", ""),
                "published": now,
                "updated": now,
                "featured": False,
            }
        )
        item["status"] = "published"
        existing_ids.add(news_id)
        created += 1
        time.sleep(1)  # 簡易レート制限対策

    save_json(NEWS_FILE, news_items)
    save_json(RAW_FILE, raw_items)
    print(f"generated: {created} article(s). total in news.json: {len(news_items)}")


if __name__ == "__main__":
    main()
