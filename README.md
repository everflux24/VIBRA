# VIBRA

Yahoo! リアルタイム検索のトレンドまとめを取得し、スマホ縦スワイプ（TikTok 風）のビューアを静的 HTML として自動生成・公開するプロジェクト。

## 特徴

- **依存ゼロ** — Python 標準ライブラリのみ。Selenium / ブラウザ / 外部パッケージ不要
- **堅牢な取得** — Yahoo の SSR JSON（`__NEXT_DATA__`）を直接解析。CSS セレクタに依存しない
- **CoreToken エンジン** — 同一話題をクラスタリングして重複排除。英数字・カタカナ・漢字混在タイトルに対応したトークナイザで固有名詞を正確に抽出
- **自動更新** — GitHub Actions が 1 時間ごとに再生成し、GitHub Pages へデプロイ

## ファイル構成

```
VIBRA/
├── local_build.py              # ビルドスクリプト本体
└── .github/
    └── workflows/
        └── deploy.yml          # 自動ビルド & Pages デプロイ
```

## GitHub Pages の初回設定

1. このリポジトリに push する
2. GitHub の **Settings → Pages → Build and deployment → Source** を **「GitHub Actions」** に変更する
3. **Actions** タブで `Build & Deploy VIBRA` を手動実行（Run workflow）する
4. 公開 URL は `https://everflux24.github.io/VIBRA/` になる

## ローカルでビルド

```bash
python local_build.py
# → index.html を生成（ブラウザで開くだけで動作）

python -m http.server 8000
# → http://localhost:8000 で確認
```

CI と同じく出力先を変えたい場合：

```bash
VIBRA_OUTPUT_DIR=_site python local_build.py
```

## 更新頻度の変更

`.github/workflows/deploy.yml` の `cron` を編集する。

```yaml
# 例：毎時0分（現在の設定）
- cron: "0 * * * *"

# 例：6時間ごと
- cron: "0 */6 * * *"
```
