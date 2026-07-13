# collect_news.py ローカル実行手順

Coworkのサンドボックスからは `api.x.com` に直接アクセスできない（中間プロキシに阻まれる既知の制約）ため、
`collect_news.py` の実運用はユーザーのローカルPC（Windows）で実行する。このフォルダは
`D:\AI\export\スモールビジネス\ポイ活セクタ\poikatsu-press` としてすでにローカルに存在するため、
リポジトリを別途cloneする必要はない。

## 前提

- Python 3.10以上がインストールされていること（`str | None` 構文を使用しているため3.10未満は不可）
- 追加ライブラリのインストールは不要（標準ライブラリのみで実装済み）
- Bearer Tokenは `secrets\secrets_x_api.md` に保存済み（このフォルダはGit非公開・GitHubにアップロードしないこと）

## 実行手順

1. コマンドプロンプトまたはPowerShellを開く
2. フォルダに移動する
   ```
   cd D:\AI\export\スモールビジネス\ポイ活セクタ\poikatsu-press
   ```
3. Pythonのバージョンを確認する
   ```
   python --version
   ```
   3.10未満の場合は、python.org から最新版をインストールしてから再実行する。
4. スクリプトを実行する（Bearer Tokenは `secrets\secrets_x_api.md` から自動で読み込まれる）
   ```
   python scripts\collect_news.py
   ```
   - 環境変数で明示的にトークンを渡したい場合は、実行前に以下を設定してもよい（任意）
     ```
     set X_BEARER_TOKEN=（secrets_x_api.mdのBearer Tokenの値）
     python scripts\collect_news.py
     ```

## 実行結果の確認

- 正常終了すると `collected: N new item(s) (pending_verification). total in news_raw.json: M` のような
  メッセージが表示される
- `data\news_raw.json` に新規検知項目が追記される（`status: "pending_verification"`）
- `data\x_state.json` が最終検知ツイートIDで更新される（次回実行時の重複防止用）

## 実行後にやること（裏取り〜記事化フロー）

1. `data\news_raw.json` の各項目の `text`（投稿本文）を確認し、該当する公式発表
   （プレスリリース・公式サイトのお知らせ）を探す
2. 裏取りできた項目に `official_source_url` フィールドを追記し、`status` を `"verified"` に変更する
   （このJSON編集はCoworkの会話内でClaudeに依頼してもよい）
3. `verified` になった項目は `python scripts\summarize.py` （こちらもローカル実行が必要。理由は
   collect_news.py と同じくCoworkサンドボックスから `api.anthropic.com` へ直接アクセスできないため）
   でClaude APIによる中立要約を生成し、`data\news.json` に反映される
4. `news.json` が更新されたら、Cowork側で `python scripts\build.py` を実行して `public\` を再生成し、
   GitHubへアップロードして本番反映する

## 注意事項

- `secrets\` フォルダの中身は絶対にGitHubへアップロードしないこと（`.gitignore` 等での除外を別途検討してもよい）
- X APIはPay Per Use（従量課金）のため、実行頻度が多いとコストが積み上がる。日次1回程度を目安にする
- 実行時にエラーが出た場合（401/403など）は、Developer Console（console.x.com）でクレジット残高・
  アプリのステータスを確認する

## 日次自動実行の設定（Windowsタスクスケジューラ、2026-07-14追加）

TOPページの「TOPニュース」「お得商品」「改悪情報」を直近24時間以内のインフルエンサー投稿に限定する
運用に変更したため（2026-07-14）、collect_news.pyは毎日決まった時刻に実行することが望ましい。
CoworkのサンドボックスからはX APIに到達できないため、この自動実行はユーザーのローカルPC側で
Windowsタスクスケジューラを使って設定する（Claudeはシステム設定の変更を直接行えないため、
以下はユーザー本人による設定作業になる）。

実行用のバッチファイルは `run_collect_news_daily.bat`（このフォルダ直下）として用意済み。
実行結果は `logs\collect_news_daily.log` に追記される。

### 設定手順

1. Windowsの検索バーで「タスクスケジューラ」と入力して開く
2. 右側の「操作」ペインから「基本タスクの作成」をクリック
3. 名前: `ポイ活PRESS_collect_news_daily`（任意）、次へ
4. トリガー: 「毎日」を選択、次へ
5. 開始時刻を指定（例: 毎朝9:00。X APIのコスト・投稿の鮮度を考慮して決める）、次へ
6. 操作: 「プログラムの開始」を選択、次へ
7. 「プログラム/スクリプト」欄に以下を入力（参照ボタンでファイルを選んでもよい）
   ```
   D:\AI\export\スモールビジネス\ポイ活セクタ\poikatsu-press\run_collect_news_daily.bat
   ```
8. 「完了」をクリックしてタスクを作成
9. 作成後、タスク一覧から該当タスクを右クリック→「実行」で一度テスト実行し、
   `logs\collect_news_daily.log` に結果が記録されることを確認する

### 自動化できる範囲・できない範囲

- **自動化できる**: X投稿の検知（collect_news.py実行 → `data\news_raw.json` への追記）
- **自動化できない（人の判断が必須・コンプライアンス上の要件）**:
  - 検知項目を公式一次ソースで裏取りし、`official_source_url` を追記して `status` を
    `verified` に変更する作業
  - `summarize.py` の実行（verified項目のみを処理するため、裏取り作業の後に手動実行）
  - deal候補（`candidate_type: "deal"`）を `deals.json` へ反映する作業（人手のみ）
  - `build.py` の再実行とGitHub Web UIでのアップロード（デプロイ）

TOPページの「直近24時間」表示は `build.py` 実行時点の時刻を基準に静的HTMLを生成するため、
収集を自動化しても、裏取り・summarize.py・build.py・GitHubアップロードまでを日次で回さない限り、
表示内容の鮮度は上がらない点に注意（詳細は `data/_schema.md` の「TOPページ掲載条件」参照）。
