@echo off
REM collect_news.py を日次実行するためのバッチファイル（2026-07-14作成）
REM Windowsタスクスケジューラから毎日決まった時刻に実行する想定。
REM 実行結果は logs\collect_news_daily.log に追記される（ログは自動では削除されないため、
REM 肥大化してきたら手動で整理すること）。

setlocal
set PROJECT_DIR=D:\AI\export\スモールビジネス\ポイ活セクタ\poikatsu-press
set LOG_DIR=%PROJECT_DIR%\logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

cd /d "%PROJECT_DIR%"

echo ==== %date% %time% ==== >> "%LOG_DIR%\collect_news_daily.log"
python scripts\collect_news.py >> "%LOG_DIR%\collect_news_daily.log" 2>&1
echo. >> "%LOG_DIR%\collect_news_daily.log"

endlocal
