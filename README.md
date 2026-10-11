# koji-kokuban-skills

工事黒板アプリ（工事写真台帳）用の、Claude Code のスキル集です。

## mamezu：図面から豆図と黒板Excelを作る

構造図などの図面PDFから、符号ごとの豆図（断面の画像）を切り出し、アプリに取り込める黒板Excelを作ります。

### 入れ方（1回だけ）
Claude Code で、次の2つを実行します。

```
/plugin marketplace add usura50-ctrl/koji-kokuban-skills
/plugin install mamezu@koji-kokuban-skills
```

### 使い方
Claude Code で、図面のPDFを渡して、頼みます。

> この図面から、豆図と黒板Excelを作って。（PDFのパス）

Claude が、工種などを質問し、画像を作り、図面と見比べて確認し、結果を報告します。

### 更新（ルールが直ったとき）
```
/plugin marketplace update koji-kokuban-skills
```

### 必要なもの
- Python 3.10 以上（部品は、初めて使うときに自動で入ります）
- 図面PDFは、文字が読み取れるもの（CAD出力）

ルールの詳細は `plugins/mamezu/skills/zumen-mamezu/references/rules.md`。
