# gui.py 仕様書

## 1. 概要

Hitomi Organizer の GUI モジュール。`tkinter` と `tkinterdnd2` を使用し、Drag & Drop による `.cbz` ファイルの整理機能を提供します。

## 2. 依存関係

| モジュール | 用途 |
|---|---|
| `tkinter` / `ttk` | GUI フレームワーク |
| `tkinterdnd2` | Drag & Drop 機能 |
| `threading` | 非同期処理 (UI フリーズ防止) |
| `subprocess` | 外部スクリプト実行 (`clean_duplicates.py`) |
| `.db_manager` | データベース操作 |
| `.file_organizer` | ファイル整理ロジック |

## 3. 設定

```python
DEFAULT_CONFIG = {
    "output_dir": r"T:\organized_h_manga"
}
```

## 4. クラス構成

### 4.1 `AliasManager(tk.Toplevel)`

作者名のエイリアス（別名→正規名）を管理するサブウィンドウ。

| メソッド | 機能 |
|---|---|
| `create_widgets()` | UI 構築 (入力フォーム) |
| `add_alias()` | エイリアスを DB に登録 |

### 4.2 `OrganizerApp(TkinterDnD.Tk)`

メインアプリケーションウィンドウ。

#### 主要属性

| 属性 | 型 | 説明 |
|---|---|---|
| `db` | `DBManager` | データベース接続 |
| `organizer` | `FileOrganizer` | ファイル整理ロジック |
| `files_map` | `dict` | `{path: item_id}` マッピング |
| `categories` | `list` | カテゴリ一覧 (DB から読込) |
| `base_dir` | `str` | 出力ディレクトリ |

#### UI 構成

```
+----------------------------------------------------------+
| Output Directory: [______] [Browse]  Category: [▼] [Apply]|
| Search (Everything): [____________] [Search & Add]        |
+----------------------------------------------------------+
| Files (Treeview)                                          |
| +------------------------------------------------------+ |
| | File             | Author      | Category | Status   | |
| +------------------------------------------------------+ |
| | example.cbz      | AuthorName  | Manga    | Pending  | |
| +------------------------------------------------------+ |
+----------------------------------------------------------+
| [Start Organize] [Clear List] [Clean Duplicates]          |
+----------------------------------------------------------+
| Log                                                       |
| > Processing...                                           |
+----------------------------------------------------------+
```

#### 主要メソッド

| メソッド | 機能 |
|---|---|
| `create_menu()` | メニューバー構築 (Tools > Manage Aliases) |
| `create_widgets()` | メインUI構築 |
| `drop_files(event)` | DnD イベントハンドラ |
| `add_file_to_tree(path)` | ファイルをリストに追加 (カテゴリ自動判定) |
| `on_double_click(event)` | カテゴリ列のインライン編集開始 |
| `edit_category(item_id, column)` | Combobox によるカテゴリ編集 |
| `check_and_add_category(name)` | 新規カテゴリを DB に追加 |
| `apply_category()` | 選択行にカテゴリを一括適用 |
| `clear_list()` | ファイルリストをクリア |
| `run_clean_duplicates()` | 重複削除スクリプト実行 |
| `start_processing_thread()` | ファイル整理処理を開始 |
| `process_files(base_path)` | 各ファイルを整理 (別スレッド) |
| `queue_log(msg)` | スレッドセーフなログ出力 |
| `queue_update_item(...)` | スレッドセーフな行ステータス更新 |

## 5. 機能詳細

### 5.1 ファイル追加 (Drag & Drop)

1. `.cbz` ファイル、またはフォルダをリストエリアにドロップ。
2. フォルダの場合、再帰的に `.cbz` を検索。
3. 各ファイルに対して:
    - `file_organizer.get_default_category_for_file()` でカテゴリと作者を推定。
    - Treeview に `[File, Author, Category, Status=Pending]` として追加。

### 5.2 カテゴリ編集

- **インライン編集**: Category 列をシングルクリック → Combobox 表示。
- **一括適用**: 複数行選択 → 上部ドロップダウンで選択 → `Apply to Selected`。
- **新規カテゴリ**: 未登録の値を入力すると自動的に DB へ保存。

### 5.3 ファイル整理 (`Start Organize`)

1. リスト内の全ファイルを順に処理。
2. `file_organizer.organize_file()` を呼び出し、ファイルを移動。
3. ステータスを更新:
    - `Done`: 移動成功
    - `Skipped`: 移動先に同名ファイルが存在
    - `Error`: その他のエラー

### 5.4 重複削除 (`Clean Duplicates`)

1. **ファイル選択時**: 選択されたファイルの Author を取得。
2. **未選択時**: リスト内の全ファイルからユニークな Author を収集。
3. 各 Author に対して `clean_duplicates.py --keyword "[Author]"` を実行。
4. 結果をログに出力。

### 5.5 ファイルを開く

- **ファイル参照**: `File` 列をダブルクリック → デフォルトアプリでファイルを開く。

### 5.6 リストのソート

- **ヘッダークリック**: 各列のタイトルをクリックすることで、その列を基準にソート。
- **トグル**: クリックするたびに昇順 (Ascending) / 降順 (Descending) を切り替え。

## 6. スレッド処理

長時間処理は別スレッドで実行し、UI のフリーズを防止。
`self.after(0, ...)` を使用してメインスレッドで UI を更新。

## 7. エントリーポイント

```python
if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
```


通常は `run_organizer.bat` 経由で起動。

### 5.7 ファイル検索 (Everything)

- **検索バー**: Output Directory の下に「Search (Everything)」と入力欄を追加。
- **Search & Add**: 入力されたキーワードと `.cbz` を条件に `es` コマンドを実行し、ヒットしたファイルをリストに追加する。
- **要件**: システム環境変数 PATH に `es.exe` が通っていること。

