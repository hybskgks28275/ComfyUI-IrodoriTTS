# ComfyUI-IrodoriTTS

Irodori-TTS-v4.1-SmallとIrodori-TTS-v4-Large、および両モデルの公式量子化版に対応するComfyUIカスタムノードです。
ComfyUI V3 API（`ComfyExtension` / `io.ComfyNode` / `define_schema`）形式で実装しています。
既存ワークフローのノードID・入力名・設定順は維持しているため、作り直しは不要です。

| mode | 入力 |
| --- | --- |
| `text` | 読み上げテキスト |
| `text_caption` | 読み上げテキスト＋キャプション（参照音声不要） |
| `text_reference` | 読み上げテキスト＋参照音声 |
| `text_caption_reference` | 読み上げテキスト＋キャプション＋参照音声 |

日本語の音声を48 kHz・モノラルのComfyUI `AUDIO`として出力します。
参照音声の書き起こしは不要です。学習、LoRA、Speaker Inversion、モデルを量子化する処理、旧モデル用のノードはありません。

## 表示言語

標準表示は英語です。ComfyUIの設定 → Locale → Languageで「日本語」を選ぶと、ノード名、項目名、説明、絵文字パネル、参照音声の選択・並べ替え、メモリ解放ボタンと状態表示が日本語になります。その他の言語は英語へフォールバックします。言語変更は表示中の独自パネルにも反映します。

読み上げテキスト、キャプション、モデル名、ファイル名、ワークフローの入力キーは変更しません。Python側のエラー文は英語です。標準HTML音声プレーヤー内部の再生・音量などの操作名はブラウザー側の言語設定に従います。

更新後はComfyUIを再起動し、ブラウザーを再読み込みしてください。ノード定義の翻訳は`locales/en/nodeDefs.json`と`locales/ja/nodeDefs.json`、独自UIの言語判定は`web/i18n.js`で管理します。

## インストール

### 必要な環境

- Python 3.10以上で動作するComfyUI
- V3 API（`comfy_api.latest`）の`MultiCombo`・`MultiType`に対応するComfyUI
- Git（依存パッケージの取得に使用）
- GPUで生成する場合はCUDA対応のPyTorchとNVIDIA GPU。通常版はCPUでも実行できますが、生成に時間がかかります。
- 量子化版を使用する場合は、後述する量子化方式ごとのGPU要件を満たす環境

以下の`ComfyUI/`は、`main.py`と`custom_nodes/`があるComfyUI本体のディレクトリを指します。実際のインストール先に読み替えてください。

### カスタムノードと依存パッケージの配置

1. このリポジトリを取得し、`ComfyUI/custom_nodes/ComfyUI-IrodoriTTS/`に配置します。ダウンロードしたZIPを展開する場合も、同ディレクトリ直下に`__init__.py`と`requirements.txt`がある構成にしてください。
2. **ComfyUIが使用しているPython環境**で、カスタムノードのディレクトリから以下を実行します。venvを使用している場合は、その環境を有効にしてから実行してください。

```sh
python -m pip install -r requirements.txt
```

公式量子化モデルも使用する場合は、追加で以下を実行します。

```sh
python -m pip install -r requirements-quantized.txt
```

Windowsポータブル版では、ポータブル版のルート（`python_embeded/`と`ComfyUI/`があるディレクトリ）から同梱Pythonを指定できます。

```powershell
./python_embeded/python.exe -m pip install -r ./ComfyUI/custom_nodes/ComfyUI-IrodoriTTS/requirements.txt
# 量子化モデルを使用する場合のみ
./python_embeded/python.exe -m pip install -r ./ComfyUI/custom_nodes/ComfyUI-IrodoriTTS/requirements-quantized.txt
```

インストール後はComfyUIを再起動し、ブラウザーを再読み込みしてください。

## 使用方法

サンプルワークフローは、このリポジトリの`examples/`にあります。使用したいJSONファイルをComfyUIの画面へドラッグ＆ドロップするか、ワークフローを開く機能で読み込んでください。
すべてのサンプルは通常版`Irodori-TTS-v4.1-Small`を使用し、生成音声を`Irodori TTS Save Audio`で保存・試聴します。
以下の説明では入力キーを使用し、ボタン名は英語表示と日本語表示を併記します。
Generateノードでは`text` → **Show emojis（絵文字を表示）** → `model_name`の順に配置しています。**Show emojis（絵文字を表示）**を押すと、ノードの右側に別パネルが開き、45種類の絵文字を表示言語に応じたラベル付きで選択できます。ノードのサイズは変わりません。初期状態では一覧を非表示にしています。
`text`欄で挿入位置をクリックしてから絵文字ボタンを押すと、その位置へ挿入します。選択中の文字がある場合は置換し、位置を指定していない場合は末尾へ追加します。連続入力と、text欄のCtrl+Zによる取り消しにも対応します。
**Hide emojis（絵文字を隠す）**、パネルの**Close（閉じる）**、またはEscキーで一覧を閉じられます。パネルはノードの移動・ズームに追従し、画面端では画面内へ位置を調整します。従来表示／Nodes 2.0の両方に対応しています。更新後はブラウザーをCtrl+F5で再読み込みしてください。

| ワークフロー | 用途 |
| --- | --- |
| `01_text.json` | テキストのみ |
| `06_text_caption.json` | テキスト＋キャプション（音声不要） |
| `02_text_reference.json` | テキスト＋参照音声（1件／複数件） |
| `03_text_caption_reference.json` | テキスト＋キャプション＋参照音声（1件／複数件） |

`04_multi_reference.json`／`05_multi_caption_reference.json`は複数参照音声用の例です。02／03と同じ統一入力を使います。

1. 使用するワークフローを開き、`text`に読み上げる日本語を入力します。
2. キャプションを使うモードでは`caption`に「穏やかに、少し楽しそうに話す」などの話し方を入力します。
3. 参照モードでは下記のローダーで音声ファイルを選択します。
4. `Irodori TTS Save Audio`の保存先・ファイル名・形式を指定して実行します。音声は保存され、同じノード内で試聴できます。

### 参照音声の選択（1件／複数件共通）

音声をComfyUIの入力ディレクトリ内の`irodori_references/`へ配置してください。標準構成では`ComfyUI/input/irodori_references/`です。フォルダーがない場合は作成してください。

**Irodori TTS Load Reference Audios**の`files`を開き、一覧のチェックボックスで1件または複数件を選択します。
Nodes 2.0では**Select reference audio (multiple files allowed)（参照音声を選択・複数可）**を開きます。ファイル名で絞り込み、チェックボックスで選択できます。
サブフォルダー内の音声も一覧に表示されます。ファイルを追加したら**Refresh audio file list（音声ファイル一覧を更新）**を押してください。
選択を外すと参照対象から除外されます。ファイル自体は削除しません。
選択した音声は**Reference order (top to bottom)（参照順序・上から使用）**に番号付きで表示されます。各行の **↑／↓** で並べ替えられます。
上から1番、2番…の順に連結して参照に使用します。変更した順序はワークフローに保存され、再読み込み後も維持されます。
新しく選択した音声は末尾に追加され、選択を外した音声は順序一覧からも除外されます。

ローダー出力を生成ノードの**`reference_audio`**へ接続します。1件／複数件で入力端子を分けません。
標準の`Load Audio`のAUDIO出力も、この同じ端子へ接続できます。
各ファイルを個別にモノラル化・音量正規化・エンコードし、参照潜在表現を指定順に結合します。
異なる長さやサンプルレートを混在できます。公式ランタイムと同じ合計120秒の参照上限を使用します。
選択済みファイルが削除された場合はエラーで通知し、別のファイルに自動置換しません。

ノード検索名は **Irodori TTS Generate**、カテゴリは`audio/Irodori TTS`です。
`model_name`で`Irodori-TTS-v4.1-Small`／`Irodori-TTS-v4-Large`または各量子化版を選択します。
既存ワークフローでこの項目がない場合はSmallを使います。どちらのモデルも4つの生成モードに対応します。
Largeはモデルファイル約13.2 GB、BF16の重みだけで約6.1 GiBを使用します。
VRAMを節約する場合は、対応GPUで`precision=bf16`・`codec_device=cpu`を使用できます。FP32では重みだけで約12.3 GiBとなり、
VRAMに収まらない場合はDynamic VRAMによる転送・退避が必要です。

### 公式量子化モデル

`model_name`で、例えば`Irodori-TTS-v4-Large-Quantized/int8-weight-only`を選択します。
Smallも同様に`Irodori-TTS-v4.1-Small-Quantized/種類`を選べます。
量子化版はCUDA専用で、`precision`の表示値にかかわらずBF16で計算します。
通常版の`precision`設定と既存ワークフローはそのまま使用できます。

| 種類 | 特徴 | 必要なGPU |
| --- | --- | --- |
| `int8-weight-only` | INT8重み、BF16計算。公式の汎用推奨版 | BF16対応NVIDIA CUDA |
| `int8-dynamic` | INT8重みと動的INT8活性値 | BF16対応NVIDIA CUDA |
| `int4-weight-only` | INT4重み、BF16計算。最小サイズ | Ampere以降（CC 8.0以上） |
| `float8-weight-only` | FP8重み、BF16活性値 | Ada以降（CC 8.9以上） |
| `float8-dynamic` | FP8重みと動的FP8活性値 | Ada以降（CC 8.9以上） |

量子化方式のGPU要件を満たさない場合やCPUを指定した場合は、モデル取得前に理由を表示します。
量子化版でも4モード・複数参照・順序指定・モデル再利用・任意アンロードを使用できます。
モデルの種類や量子化方式を変えると、保持中のモデルを解放して切り替えます。
量子化方式による生成速度はGPUや実行環境によって異なります。量子化版を使用する場合は、サンプルの`model_name`を使用したい量子化モデルへ変更してください。FP8の実生成は未検証です。

以下は通常版と共通の入力条件です。
`text`と`text_caption`では参照音声を使用しません。`text`と`text_reference`ではcaptionを使用しません。
参照モードで音声未接続、またはキャプションを使うモードでcaptionが空の場合は入力エラーになります。

### 以前のバージョンからの更新

ComfyUIを再起動し、ブラウザーも再読み込みしてください。更新済みワークフローを開き直すと新しい入力構成になります。
手元で編集した旧ワークフローは生成ノードと参照ローダーを追加し直し、`reference_audio`へ接続してください。
以前の2つの参照端子を同時に使っていた場合は、参照ローダーの一覧で対象ファイルをまとめて選択します。
既存の参照ファイルはそのまま利用できます。参照入力の更新だけなら新規パッケージは不要です。
量子化版を使用する場合は、上記のtorchao追加手順を実行してください。

## 主な設定

| 設定 | 初期値／動作 |
| --- | --- |
| `steps` | 40。拡散のステップ数 |
| `seed` | 0。同じ入力・実行環境・seedで再現。右側の生成後動作で固定／ランダムを選択 |
| `cfg_text` | 3.0。読み上げテキストの誘導強度 |
| `cfg_reference` | 5.0。参照音声の誘導強度 |
| `cfg_caption` | 3.0。captionの誘導強度 |
| `seconds` | 0で自動予測。正の値で生成する秒数を指定（UI上限30秒） |
| `duration_scale` | 1.0。自動予測の長さを倍率調整。seconds指定時は使われません |
| `device` | autoでCUDAを優先、CUDAがなければCPU |
| `precision` | fp32。bf16も選択可能（対応CUDA GPUのみ。量子化ではありません） |
| `codec_device` | cpu。参照音声のエンコード／生成音声のデコードをCPUで行いVRAMを節約 |
| `allow_download` | true。不足したモデルファイルを実行時に取得 |
| `unload_after_generate` | false。モデルを保持して次回の生成に再利用。trueで生成後に解放 |
| `model_name` | Irodori-TTS-v4.1-Small。Small／Largeを選択 |
| `dynamic_vram` | true。ComfyUI本体のDynamic VRAMが有効なCUDA環境では、TTSモデルの重みを必要に応じて転送・退避 |

生成ノードの数値入力は、従来表示の左右矢印、Nodes 2.0の−／＋を押し続けると連続して増減します。
短いクリックは1段階、約0.35秒の長押し後は約0.075秒ごとに1段階変更します。
整数・小数それぞれの刻み幅と上下限を守り、ボタンを離す、矢印から外れる、Escapeを押す、または画面のフォーカスが外れると停止します。
数値の直接入力と中央からのドラッグ操作も使えます。Irodori TTS生成ノードだけに適用し、従来表示とNodes 2.0の両方に対応します。
UI拡張の更新後はブラウザーをCtrl+F5で再読み込みしてください。

長文の自動分割は実装していません。長い原稿は文単位などに分けてください。
テキストのトークン長、参照上限、末尾のトリミング、音量正規化は公式推論の設定に従います。
各参照音声は1バッチのみ、ステレオは平均してモノラル化し、サンプルレートは公式コーデック側で変換します。
公式モデルの参照上限は120秒です。参照の短さやcaptionとの矛盾は音声品質に影響します。

本ノードはデフォルトでTTSモデルとコーデックを保持し、
同じmodel_name・device・precision・codec_device・実際のDynamic VRAM使用状態での次回生成に再利用します。text・seed・mode・参照音声・captionを変えてもモデルの再ロードは不要です。
キャッシュはノード間で共有する1セットだけで、モデル・デバイス・精度を変えた場合は古いモデルを解放してからロードします。
`unload_after_generate=true`では保持済みモデルも利用したうえで生成後に解放します。推論エラー・キャンセル時もキャッシュを破棄します。

Generateノード下部の**Release memory（メモリ解放）**ボタンでも、生成せずに保持中のTTSモデルとコーデックを解放できます。
従来表示・Nodes 2.0の両方に対応し、全Irodori Generateノードで共有しているキャッシュが対象です。
生成済みの音声は残り、次回の実生成ではモデルを再ロードします。生成・読み込み中は解放せず案内を表示するため、
完了またはキャンセル後に押してください。解放中・完了・保持なし・失敗の結果をボタン下に表示します。
更新後はComfyUIを再起動し、ブラウザーをCtrl+F5で再読み込みしてください。ノードの作り直しは不要です。

Dynamic VRAM使用時は、TTS本体とテキスト／captionエンコーダーをCPU上で準備し、ComfyUIの`ModelPatcherDynamic`で管理します。
通常版と量子化版の両方が対象で、量子化された重みは圧縮形式を維持して転送します。他モデルの一括アンロードは行わず、
ComfyUIがVRAMの空きに応じて重みを退避します。退避後もモデルファイルを読み直さず再利用できます。
コーデックはこの管理の対象外で、従来どおり`codec_device`に配置します。VRAMを節約する場合は既定の`cpu`を使用してください。
CPU側にはモデルを保持するためRAMが必要です。Dynamic VRAMも、すべての入力でメモリ不足を防ぐものではありません。

ComfyUI起動ログの`DynamicVRAM support detected and enabled`で本体の有効状態を確認できます。
`dynamic_vram=false`、本体で無効、またはCPU実行の場合は従来方式です。この場合は生成前にComfyUI管理の他モデルをアンロードし、
TTSモデルはComfyUIの自動退避の対象外となります。保持したTTSとコーデックはRelease memory（メモリ解放）ボタン、または`unload_after_generate=true`で解放できます。
ノードの設定だけでComfyUI本体のDynamic VRAMを有効化することはありません。
既存ワークフローで省略した場合も`unload_after_generate=false`、`dynamic_vram=true`になります。
キャンセルはサンプリングの各ステップと推論の段階間で確認します。
モデルのダウンロード／ロードとコーデックの処理中は、その処理が戻るまでキャンセルが反映されない場合があります。

## モデル配置とネットワーク

通常の配置先は以下です。

```text
ComfyUI/models/irodori_tts/
  Irodori-TTS-v4.1-Small/
    model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Irodori-TTS-v4-Large/
    model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Irodori-TTS-v4-Large-Quantized/
    int8-weight-only/model.safetensors
    int4-weight-only/model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Irodori-TTS-v4.1-Small-Quantized/
    int8-weight-only/model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Semantic-DACVAE-Japanese-32dim/
    weights.pth
```

モデルの保存先はComfyUIが使用するモデルディレクトリの`irodori_tts/`です。モデルディレクトリを移動・リンクしている場合は、その設定に応じた場所に保存されます。
初回取得はSmall＋コーデックで合計約3.5 GB。Largeを選択した場合はLargeの重み約13.2 GBと同梱トークナイザーを取得します。
選択したモデルだけをダウンロードし、コーデックは共通のファイルを使用します。モデル・コーデックは固定リビジョンから取得します。
量子化版も選択したサブフォルダーの重みだけを取得し、トークナイザーは同じモデルの各量子化方式で共有します。
量子化モデルの重みはSmallで約813～906 MiB、Largeで約2,818～3,665 MiBです。
配置済みなら本ノードのモデル解決処理はネットワークアクセスしません。`allow_download=false`で不足時もダウンロードを禁止できます。
参照音声はローカルの一時WAVとして処理後に削除します。外部へ送信しません。

SilentCipherは必須依存に含めていません。未導入時は公式ランタイムが警告を出し、透かしなしで生成します。
別途導入済みの環境では公式ランタイムがSilentCipherを利用し、そのモデルを初回取得する場合があります。

## 検証

ComfyUIが使用するPython環境を有効にし、このリポジトリのディレクトリから実行します。`<ComfyUI本体のパス>`は`main.py`があるディレクトリの絶対パスに置き換えてください。

PowerShellの場合：

```powershell
$comfyRoot = '<ComfyUI本体のパス>'
$env:PYTHONPATH = $comfyRoot
python -m unittest discover -s tests -p 'test_*.py'
python tests/smoke_generate.py --comfy-root "$comfyRoot" --output-dir ./work/smoke
python tests/smoke_dynamic_vram.py --comfy-root "$comfyRoot" --model-name Irodori-TTS-v4.1-Small --output-dir ./work/dynamic-smoke
```

Bashの場合：

```bash
comfy_root='<ComfyUI本体のパス>'
PYTHONPATH="$comfy_root" python -m unittest discover -s tests -p 'test_*.py'
python tests/smoke_generate.py --comfy-root "$comfy_root" --output-dir ./work/smoke
python tests/smoke_dynamic_vram.py --comfy-root "$comfy_root" --model-name Irodori-TTS-v4.1-Small --output-dir ./work/dynamic-smoke
```

ポータブル版などvenvを有効にしない構成では、`python`をComfyUIが使用するPython実行ファイルに置き換えてください。PowerShellで引用符付きの実行ファイルパスを使う場合は、先頭に`&`を付けて呼び出します。スモークテストは実際にモデルをロードして音声を生成するため、モデルファイルと十分なメモリが必要です。Dynamic VRAM用テストには対応するCUDA環境が必要です。

スモークテストでは4モードを実行し、48 kHzの非無音・有限値のAUDIO出力を検証します。
参照テストは最初の合成音声を24 kHz・ステレオ化して使用します。
Dynamic VRAM用テストでは、CPU準備・GPU生成・重みの退避・モデルの再利用・生成後の解放を確認します。

## 出典・ライセンス

- [公式モデル](https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small)
- [Large公式モデル](https://huggingface.co/Aratako/Irodori-TTS-v4-Large)（モデルライセンス：Gemma）
- [Small公式量子化モデル](https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small-Quantized)（MIT）
- [Large公式量子化モデル](https://huggingface.co/Aratako/Irodori-TTS-v4-Large-Quantized)（Gemma）
- [公式推論コード](https://github.com/Aratako/Irodori-TTS)
- [音声コーデック](https://huggingface.co/Aratako/Semantic-DACVAE-Japanese-32dim)

ノードのコードはMITライセンスです。同梱コードの出典・変更点は`THIRD_PARTY.md`に記載しています。
モデルと依存ライブラリはそれぞれのライセンス・モデルカードに従います。


## 音声の保存・試聴

`Irodori TTS Save Audio`へGenerateの`audio`を接続します。保存後はノード内のプレーヤーで試聴でき、音声出力を別ノードへ接続することもできます。試聴は標準HTMLの`<audio controls>`を使用し、プレーヤー内で再生・シーク・音量・ミュートを操作できます。独立した音量スライダーは表示しません。音量操作は再生音量だけに反映し、保存ファイル・AUDIO出力には影響しません。従来表示／Nodes 2.0とも同じHTMLプレーヤーを使用します。音量操作の表示方法はブラウザーとプレーヤーの幅によって変わります。`examples/`内のすべてのサンプルに保存ノードを接続しています。

| 設定 | 内容 |
| --- | --- |
| `filename_prefix` | ファイル名の接頭辞。既定値 `Irodori_{yyyymmddhhmmss}` |
| `directory` | ComfyUIの`output/audio`からの相対ディレクトリ。既定値 `{yyyymmdd}`。空欄なら直下、`project/{yyyymmdd}`のような階層も指定可能 |
| `format` | `wav` / `mp3` / `flac` |
| `bitrate` | MP3の64／96／128／160／192／256／320 kbps。WAV・FLACでは使用しません |
| `bit_depth` | WAV・FLACの16／24bit。MP3では使用しません |

ファイル名とディレクトリの`{yyyymmddhhmmss}`・`{yyyymmdd}`・`{hhmmss}`を、保存ノードが実行された時点のローカル日時へ置換します。波括弧なしの同じ文字列も置換できます。バッチ内は同じ日時を使用します。
例：`output/audio/20260929/Irodori_20260929153045_00001.wav`。既存ファイルを上書きせず、連番を増やして保存します。

WAVのビットレートはサンプルレート・チャンネル数・ビット深度から決まり、FLACでは音声内容によって変わるため、固定ビットレート指定はMP3のみです。サンプルレートとチャンネル数は入力を維持します。MP3は対応レート（8～48 kHzの標準レート）のみ使用でき、32 kHz未満は160 kbps以下を指定してください。モノラル／ステレオと音声バッチに対応しています。
同じ入力を再実行した際、ComfyUIのキャッシュにより保存が省略される場合があります。再保存するには接頭辞などの入力を変更してください。

新ノードを認識させるため、追加後はComfyUIを再起動し、ブラウザーを再読み込みしてください。ComfyUIに付属するPyAVと既存のsoundfileを使うため、追加パッケージは不要です。


## モデル一覧を手動で追加・変更する

カスタムノード直下の`models.json`を編集し、**ComfyUIを再起動してブラウザーを再読み込み**してください。Generateの`model_name`はこのファイルの`models`順に表示されます。Pythonコードの変更は不要です。

通常版は`models`配列へ次のような項目を追加します（URLは使用する実際のリポジトリに置き換えてください）。

```json
{
  "model_name": "My-Irodori-Model",
  "url": "https://huggingface.co/OWNER/REPOSITORY"
}
```

- `model_name`：ノードの選択名兼ローカル保存フォルダー名。既存の名前と重複させず、`/`や`\`は含めないでください。
- `url`：Hugging FaceモデルリポジトリのトップURL。`/tree/main`やファイルのURLは使用しません。
- `revision`（省略可能）：コミットID・タグ・ブランチ。省略時は`main`。既存モデルは従来のコミットIDを維持しています。
- `default_model`：既定の選択名。量子化版を既定にする場合は展開後の`モデル名/方式`を指定します。

量子化版には`variants`を追加します。

```json
{
  "model_name": "My-Irodori-Quantized",
  "url": "https://huggingface.co/OWNER/REPOSITORY",
  "revision": "main",
  "variants": ["int8-weight-only", "int8-dynamic", "int4-weight-only"]
}
```

対応方式は`int8-weight-only`、`int8-dynamic`、`int4-weight-only`、`float8-weight-only`、`float8-dynamic`です。指定した方式のみが`My-Irodori-Quantized/int8-weight-only`のように表示されます。

追加するモデルは、このノードのIrodoriランタイムと互換性が必要です。通常版はリポジトリ直下に`model.safetensors`、量子化版は`方式/model.safetensors`、両方とも`tokenizer/`が必要です。任意のTTSモデルや、異なる構造の新バージョンが自動的に使えるわけではありません。

取得先は`models/irodori_tts/<model_name>/`です。既存ファイルが揃っている場合は再取得しないため、URLやrevisionを変更して別の重みを使う場合は、新しい`model_name`で追加してください。共通コーデックのURLとrevisionも`codec`項目へ移動しましたが、通常は変更不要です。
設定の形式・名前の重複・未対応方式などに問題がある場合は、起動ログに`models.json`のパスと理由を表示します。JSONではコメントや末尾の余分なカンマは使用できません。


## ソースの配置

- `__init__.py`：ComfyUIが読み込む入口とWebディレクトリの指定
- `src/nodes/`：生成・参照音声読み込み・音声保存のノード実装
- `src/modules/`：モデル設定読み込み、量子化、Dynamic VRAM、HTTPルートなどの補助コード
- `src/modules/vendor/`：同梱したIrodori推論ランタイムとライセンス
- `web/`：JavaScriptによるノードUI
- `locales/`：英語・日本語のノード定義翻訳
- `models.json`：手動編集するモデル一覧（ルート配置を維持）
- `tests/`：テスト・動作確認用Python/JavaScript
- `examples/`：サンプルワークフロー

構成変更後はComfyUIを再起動してください。
