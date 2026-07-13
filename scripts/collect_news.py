"""collect_news.py — X投稿からの速報検知（計画書 6-1 / 進捗ログ2026-07-09決定事項）
（2026-07-13追加: お得商品(deals.json)候補の検知にも対応。課題#58 / タスク#58）

方針（重要・playbook & 台帳のコンプライアンスルール準拠）:
- X投稿は「速報のきっかけ検知」専用。ここで集めた投稿の文章をそのまま記事にはしない。
- 検知した話題は、次工程（人手 or summarize.py）で必ず各社公式発表（プレスリリース／
  公式サイトのお知らせ）で裏取りしてから、要約＋出典リンクで news.json（または人手で
  deals.json）に反映する。
- 出力の news_raw.json は「検知ログ」であり、status=pending_verification のまま
  news.json / deals.json に自動反映されることはない。
- news_raw.json の各項目には candidate_type（["news"] / ["deal"] / 両方）を付与する。
  NEWS_KEYWORDS にヒットすれば"news"、DEAL_KEYWORDS（クーポン・セール・割引等）に
  ヒットすれば"deal"を含める。deal候補をdeals.jsonへ反映する際は、source・is_affiliate・
  category・url（自社アフィリンクへの貼り替え含む）を人手で設定すること（自動化はしない。
  data/_schema.mdのdeals.json項を参照）。

認証情報:
- Bearer Tokenは環境変数 X_BEARER_TOKEN から読む（推奨）。
- ローカル実行の利便性のため、環境変数が無い場合のみ
  poikatsu-press/secrets/secrets_x_api.md を読んでBearer Tokenを抽出する
  （このファイルはGit非公開。GitHubには絶対にアップロードしないこと）。

入力:
- data/x_sources.json … 監視対象アカウント一覧
- data/x_state.json   … 前回実行時の最終検知ツイートID（アカウント別、重複検知防止）

出力:
- data/news_raw.json  … 検知した投稿のログ（要約前）。次工程の裏取り対象リスト。
- data/x_state.json   … 更新後の最終検知ツイートID

X API: recent search endpoint (過去7日分) を使用。
複数アカウントを "(from:a OR from:b ...) (kw1 OR kw2 ...) -is:retweet" で1クエリに
まとめてコスト（従量課金の読み取り件数）を抑える。アカウント数が多い場合は分割する。
"""
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SECRETS_MD = ROOT / "secrets" / "secrets_x_api.md"

X_SOURCES = DATA / "x_sources.json"
STATE_FILE = DATA / "x_state.json"
RAW_OUT = DATA / "news_raw.json"

SEARCH_URL = "https://api.x.com/2/tweets/search/recent"

# 速報のきっかけとみなすキーワード（進捗ログ2026-07-09の方針より）
NEWS_KEYWORDS = [
    "改悪", "改定", "還元率", "新キャンペーン", "キャンペーン", "終了",
    "上限", "改良", "増量", "改善", "廃止", "変更", "発表", "新登場",
    "ポイント還元", "付与率",
]

# お得商品(deals.json)候補とみなすキーワード（2026-07-13追加・課題#58）
# あくまで「きっかけ検知」用。数値・条件は必ず公式一次ソースで裏取りしてからdeals.jsonへ反映する
DEAL_KEYWORDS = [
    "クーポン", "セール", "タイムセール", "割引", "オフ", "無料体験", "初回無料",
    "ポイントバック", "キャンペーンコード", "特典", "お得情報", "プライムデー",
    "限定価格", "最安値",
]

# 後方互換用（既存コード・ドキュメントからの参照を壊さないため。中身はNEWS_KEYWORDSと同じ）
KEYWORDS = NEWS_KEYWORDS
ALL_KEYWORDS = NEWS_KEYWORDS + DEAL_KEYWORDS

ACCOUNTS_PER_CHUNK = 10  # 1クエリに詰め込むアカウント数の上限（クエリ長対策）
MAX_RESULTS_PER_QUERY = 30  # recent search の1リクエストあたり最大取得件数
REQUEST_INTERVAL_SEC = 2  # チャンク間のインターバル（レート制限対策）


def load_bearer_token() -> str:
    token = os.environ.get("X_BEARER_TOKEN")
    if token:
        return token.strip()
    if SECRETS_MD.exists():
        text = SECRETS_MD.read_text(encoding="utf-8")
        m = re.search(r"## Bearer Token\n(.+)", text)
        if m:
            return m.group(1).strip()
    raise RuntimeError(
        "Bearer Tokenが見つかりません。環境変数 X_BEARER_TOKEN を設定するか、"
        "secrets/secrets_x_api.md を確認してください。"
    )


def load_accounts() -> list[dict]:
    data = json.loads(X_SOURCES.read_text(encoding="utf-8"))
    return data["accounts"]


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_raw() -> list[dict]:
    if RAW_OUT.exists():
        return json.loads(RAW_OUT.read_text(encoding="utf-8"))
    return []


def save_raw(items: list[dict]) -> None:
    RAW_OUT.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def chunk(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def build_query(accounts: list[dict]) -> str:
    from_clause = " OR ".join(f"from:{a['handle']}" for a in accounts)
    kw_clause = " OR ".join(ALL_KEYWORDS)
    return f"({from_clause}) ({kw_clause}) -is:retweet"


def search_recent(token: str, query: str, since_id: str | None) -> list[dict]:
    params = {
        "query": query,
        "max_results": str(MAX_RESULTS_PER_QUERY),
        "tweet.fields": "created_at,author_id",
        "expansions": "author_id",
        "user.fields": "username,name",
    }
    if since_id:
        params["since_id"] = since_id
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"[ERROR] HTTP {e.code} for query={query!r}: {body}", file=sys.stderr)
        return {}


def match_keywords(text: str) -> list[str]:
    return [kw for kw in ALL_KEYWORDS if kw in text]


def classify_candidate_type(matched: list[str]) -> list[str]:
    """マッチしたキーワードから news_raw.json 項目の候補種別を判定する（2026-07-13追加）。"""
    types = []
    if any(kw in NEWS_KEYWORDS for kw in matched):
        types.append("news")
    if any(kw in DEAL_KEYWORDS for kw in matched):
        types.append("deal")
    return types or ["news"]


def main() -> None:
    token = load_bearer_token()
    accounts = load_accounts()
    handle_to_name = {a["handle"]: a["name"] for a in accounts}
    state = load_state()
    raw_items = load_raw()
    existing_ids = {item["tweet_id"] for item in raw_items}

    new_count = 0
    for group in chunk(accounts, ACCOUNTS_PER_CHUNK):
        query = build_query(group)
        # このグループ内で最も古いsince_idを使う（グループ単位でstateを持たない簡易実装。
        # 将来アカウント数が増えたら、グループごとにsinceを分けることを検討）
        since_id = state.get("_last_group_since_id")
        result = search_recent(token, query, since_id)
        tweets = result.get("data", [])
        users = {u["id"]: u for u in result.get("includes", {}).get("users", [])}

        max_id_seen = state.get("_last_group_since_id")
        for tw in tweets:
            tweet_id = tw["id"]
            if tweet_id in existing_ids:
                continue
            matched = match_keywords(tw["text"])
            if not matched:
                continue
            author = users.get(tw.get("author_id", ""), {})
            handle = author.get("username", "")
            candidate_type = classify_candidate_type(matched)
            note = "公式発表での裏取り前。この文面をそのまま記事化しないこと。"
            if "deal" in candidate_type:
                note += (
                    " deals.json掲載時はsource/is_affiliate/category/urlを人手で設定"
                    "（自社アフィリンクへの貼り替え含む。data/_schema.md参照）。"
                )
            raw_items.append(
                {
                    "detected_id": f"x_{tweet_id}",
                    "source": "x",
                    "account_handle": handle,
                    "account_name": handle_to_name.get(handle, author.get("name", "")),
                    "tweet_id": tweet_id,
                    "tweet_url": f"https://x.com/{handle}/status/{tweet_id}",
                    "text": tw["text"],
                    "created_at": tw.get("created_at", ""),
                    "matched_keywords": matched,
                    "candidate_type": candidate_type,
                    "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "status": "pending_verification",
                    "note": note,
                }
            )
            existing_ids.add(tweet_id)
            new_count += 1
            if max_id_seen is None or int(tweet_id) > int(max_id_seen):
                max_id_seen = tweet_id

        if max_id_seen:
            state["_last_group_since_id"] = max_id_seen

        time.sleep(REQUEST_INTERVAL_SEC)

    save_raw(raw_items)
    save_state(state)
    deal_count = sum(
        1 for item in raw_items if "deal" in item.get("candidate_type", ["news"])
    )
    print(
        f"collected: {new_count} new item(s) (pending_verification). "
        f"total in news_raw.json: {len(raw_items)} (うちdeal候補: {deal_count})"
    )
    if new_count:
        print(
            "次のステップ: data/news_raw.json の各項目を公式発表で裏取りしてから、"
            "candidate_type=news の項目はsummarize.py（またはユーザー確認）でnews.jsonへ、"
            "candidate_type=deal の項目は人手でdeals.jsonへ反映してください"
            "（source/is_affiliate/category/urlの設定はdata/_schema.md参照）。"
        )


if __name__ == "__main__":
    main()
