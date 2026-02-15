# 自動同期の設定手順

chart0 の data/ および financedata/ が更新されたとき、chart0_table を自動で更新する仕組みです。

## 必要な設定

### 1. GitHub Personal Access Token (PAT) の作成

1. GitHub の Settings > Developer settings > Personal access tokens > Tokens (classic) へ移動
2. `Generate new token (classic)` をクリック
3. 以下の権限を付与:
   - `repo` (Full control of private repositories)
4. トークンを生成してコピー

### 2. Secrets の登録

#### chart0_table リポジトリ
1. keroppa88/chart0_table の Settings > Secrets and variables > Actions へ移動
2. `New repository secret` をクリック
3. Name: `PAT_TOKEN`、Value: 上記で作成した PAT を設定

#### chart0 リポジトリ
1. keroppa88/chart0 の Settings > Secrets and variables > Actions へ移動
2. `New repository secret` をクリック
3. Name: `PAT_TOKEN`、Value: 同じ PAT を設定

### 3. chart0 リポジトリにワークフローを追加

chart0 リポジトリの `.github/workflows/trigger-table-sync.yml` に以下の内容のファイルを作成してください:

```yaml
name: Trigger chart0_table sync

on:
  push:
    paths:
      - 'data/**'
      - 'financedata/**'

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger chart0_table sync
        run: |
          curl -X POST \
            -H "Accept: application/vnd.github.v3+json" \
            -H "Authorization: token ${{ secrets.PAT_TOKEN }}" \
            https://api.github.com/repos/keroppa88/chart0_table/dispatches \
            -d '{"event_type":"chart0-data-updated"}'
```

## 動作の流れ

1. chart0 の data/ または financedata/ にファイルが push される
2. chart0 の GitHub Actions が `repository_dispatch` イベントを chart0_table に送信
3. chart0_table の GitHub Actions が chart0 から最新データを取得・同期・コミット

## 手動実行

chart0_table の Actions タブから「Sync data from chart0」ワークフローを手動で実行することもできます（workflow_dispatch）。
