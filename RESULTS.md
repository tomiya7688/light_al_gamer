# 実行・検証結果

実施日: 2026-11-01（日本時間） / 作者: Tomiya

## 最終自律プレイ

コマンド: `python run_demo.py --turns 150 --output artifacts/final-150`

| 項目 | 実測 |
|---|---:|
| 連続した有効操作 | 150ターン |
| ゲーム再起動 | 0回 |
| スコア | 2068 |
| 最大タイル | 256 |
| 画像認識エラー | 0 |
| 操作後の遷移不整合 | 0 |
| プレイ時間（動画生成を除く） | 7.049秒 |
| PNG保存数 | 151枚 |
| MP4 | H.264 / 480×600 / 151フレーム |

seed=7、探索深さ2。150ターンの制限で正常終了しました。ゲームオーバーにはなっていません。
初回と最終の2回の150ターン実行で同じ盤面・スコアになりました。
最終画像の表示スコア2068と、ログから合計した合成スコア2068の一致を目視確認しました。

`demo/` に最終実行のサマリー、全ターンログ、初期・最終PNG、MP4を収録します。
再実行では全PNGとGIFも `artifacts/` に保存します。

## 自動テスト・修正

環境: Windows / Python 3.14.7 / Pillow 12.3.0 / pytest 9.1.1 / Ruff 0.15.22。

- `python -m pytest -q`: **30 passed**。
- `python -m ruff check .`: 成功。
- `python -m ruff format --check .`: 16ファイル整形済み。
- 実子プロセスと画像・キーだけのHTTP通信を使い、100ターンの統合テストに成功。
- 200個のランダム盤面×4方向で、合成の質量保存を確認。
- 全対応色、未知色、画面サイズ異常、部分的な隠れ、合法手、合成報酬、無反応・不正遷移を確認。
- 状態・盤面・スコアAPIは404、未知キーは400となることを確認。
- 子プロセス終了、画像ハッシュ、既存出力の上書き禁止も確認。

最初のテストでは、pytestの一時フォルダーがアクセス拒否となり27 passed / 3 errorsでした。
テスト生成物をプロジェクト内の固有フォルダーへ保存するfixtureに変え、キャッシュを無効化して修正しました。
Ruffの探索対象から実行生成物と失敗した一時ディレクトリを除外し、再検証しました。

GitHub ActionsのPython 3.11 / 3.14検証を定義しました。クラウド上のCI実行結果はこのローカル検証とは別です。

## 残る制約・未確認範囲

- 実行環境ではOSの画面キャプチャが失敗しました。本デモは独立ゲームプロセスが描画した
  ラスターフレームバッファのPNGを観測しています。デスクトップキャプチャ・OSキー入力は未実装です。
- 認識は同梱ゲームの色・座標に特化しています。任意のゲーム画面やテーマ変更には対応しません。
- 2048到達の保証、LLM/VLM実装、外部ゲームのアニメーション待機はありません。
- 手動ブラウザービューアーのHTTP応答はテストしましたが、ブラウザー上の操作は未検証です。
- Python 3.11でのローカル実行は未検証です。

## 外部レビュー実行の証跡

共通手順 `E:/projects/REVIEW_OPERATIONS.md` を開始時・終了前に読み、指定クライアントを検出しました。
公開可能なソースを3単位の資料に分け、1単位目を既存ランチャーで実際に依頼しました。
各ランチャーが環境制限で送信前に失敗したため、外部レビュー完了とは扱いません。
レビュー目的での権限昇格・課金・モデル変更・再試行は行っていません。

| 相手 | 今回の実行結果 |
|---|---|
| Codex Luna low | Invoke-LocalReview: `E:/projects/.review-work/runs/` の作成がアクセス拒否 |
| Antigravity | Invoke-FreeCliReview: 同じ実行ディレクトリ作成がアクセス拒否 |
| Continue | Invoke-FreeCliReview: 同じ実行ディレクトリ作成がアクセス拒否 |
| Qwen Code | Invoke-FreeCliReview: 同じ実行ディレクトリ作成がアクセス拒否。検出結果でも代替無料経路は未設定 |
| Grok | Invoke-FreeCliReview: 同じ実行ディレクトリ作成がアクセス拒否 |
| Jules | `jules remote list --repo`: プロキシ127.0.0.1:9接続拒否でトークン更新・対象確認不可。CLIログ保存もアクセス拒否 |
| 追加: DeepSeek Harness | Invoke-ExtraFreeReview: `E:/projects/.review-work/extra-free/` の結果保存がアクセス拒否 |

Lunaは `Invoke-LocalReview.ps1 -Reviewer Luna`、他4者は `Invoke-FreeCliReview.ps1 -Reviewer <名称>`、
追加は `Invoke-ExtraFreeReview.ps1 -Reviewer DeepSeekHarness`。
各々 `-InputFile review/packet-1.txt -OutputFile review/<相手>.json -PublicPacketConfirmed` を指定しました。
2026-11-01 20:30〜20:31 JSTに試行しました。2・3単位目は同一の実行環境障害により未送信です。
資料SHA256と詳細は `demo/review_attempts.json` に記録します。
自己レビュー・自動テストは実施済み、外部レビューは未完了です。
