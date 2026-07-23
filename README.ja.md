[English](README.md) | [简体中文](README.zh-CN.md) | **日本語**

<div align="center">

<img src="assets/text-to-cad-demo.gif" alt="CAD スキルが CAD ジオメトリを生成してプレビューするデモ" width="100%">

<br>

<pre>
 ██████╗ █████╗ ██████╗       ███████╗██╗  ██╗██╗██╗     ██╗     ███████╗
██╔════╝██╔══██╗██╔══██╗      ██╔════╝██║ ██╔╝██║██║     ██║     ██╔════╝
██║     ███████║██║  ██║      ███████╗█████╔╝ ██║██║     ██║     ███████╗
██║     ██╔══██║██║  ██║      ╚════██║██╔═██╗ ██║██║     ██║     ╚════██║
╚██████╗██║  ██║██████╔╝      ███████║██║  ██╗██║███████╗███████╗███████║
 ╚═════╝╚═╝  ╚═╝╚═════╝       ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝
</pre>

CAD、ロボティクス、ハードウェア設計エージェント向けのスキルライブラリ

[ドキュメント](https://www.cadskills.xyz) | [デモ](https://demo.cadskills.xyz)

[![Discord に参加](https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5FGB9DwJYU)
[![GitHub stars](https://img.shields.io/github/stars/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Stars)](https://github.com/earthtojake/text-to-cad/stargazers)
[![ライセンス：MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![@earthtojake をフォロー](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=for-the-badge&logo=x)](https://x.com/earthtojake)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](skills/cad/requirements.txt)
[![STEP](https://img.shields.io/badge/STEP-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![STL](https://img.shields.io/badge/STL-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![3MF](https://img.shields.io/badge/3MF-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![URDF](https://img.shields.io/badge/URDF-Robots-6B46C1?style=for-the-badge)](skills/urdf/SKILL.md)
[![SDF](https://img.shields.io/badge/SDF-Simulation-6B46C1?style=for-the-badge)](skills/sdf/SKILL.md)
[![SRDF](https://img.shields.io/badge/SRDF-MoveIt2-6B46C1?style=for-the-badge)](skills/srdf/SKILL.md)

</div>

# CAD スキル

CAD Skills は、ローカルプロジェクトのファイルから CAD およびロボット記述の成果物を
生成、検査、調達、スライスし、引き渡すためのエージェントスキル
ライブラリです。

## 🧰 スキル

このライブラリをインストールすると、CAD、製造、ロボット記述ファイル、
シミュレーション、ローカルレビューに特化したワークフローをエージェントに追加できます。

| スキル       | 概要                                                                                                                                                         | ソース                                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| CAD          | 自然言語または画像による要求から CAD モデルを作成・編集します。STEP を主な出力とし、STL、3MF、GLB へのエクスポートも選択できます。                           | [skills/cad](skills/cad/SKILL.md)                   |
| CAD Viewer   | CAD、G-code、ロボットファイルをローカルブラウザーでプレビューします。                                                                                        | [skills/cad-viewer](skills/cad-viewer/SKILL.md)     |
| step.parts   | ねじ、ベアリング、モーター、コネクターなど、市販の STEP 部品を検索します。                                                                                   | [skills/step-parts](skills/step-parts/SKILL.md)     |
| DXF          | Python ソースまたは CAD ジオメトリから、輪郭、テンプレート、ガスケット、カットレイアウトなどの 2D DXF 図面を作成します。                                    | [skills/dxf](skills/dxf/SKILL.md)                   |
| URDF         | link、joint、limit、inertial、mesh を含むロボット構造ファイルを作成します。                                                                                   | [skills/urdf](skills/urdf/SKILL.md)                 |
| SRDF         | URDF に MoveIt のプランニンググループ、エンドエフェクター、ポーズ、衝突ルールを追加します。                                                                  | [skills/srdf](skills/srdf/SKILL.md)                 |
| SDF          | frame、物理特性、センサー、ライトを含むシミュレーターモデルとワールドを作成します。                                                                           | [skills/sdf](skills/sdf/SKILL.md)                   |
| SendCutSend  | SendCutSend にアップロードする前に DXF と STEP ファイルを検査します。                                                                                         | [skills/sendcutsend](skills/sendcutsend/SKILL.md)   |
| G-code       | 実際のスライサー CLI を使って、対応するメッシュファイルを検証済みでプリンタープロファイル付きの FDM `.gcode` にスライスします。                             | [skills/gcode](skills/gcode/SKILL.md)               |
| Bambu Labs   | 検証済みの `.gcode` をドライラン、アップロードし、ローカルの Bambu Lab 印刷ジョブを慎重に開始します。                                                         | [skills/bambu-labs](skills/bambu-labs/SKILL.md)     |
| Implicit CAD | GLSL 符号付き距離場と CAD Viewer のレイマーチレンダリングを使用して、ブラウザーで動作する暗黙的 CAD モデルを作成します。実験的な機能です。                   | [skills/implicit-cad](skills/implicit-cad/SKILL.md) |

## 💻 インストール

本番環境で使用する場合は、`main` からインストールまたはクローンしてください。このブランチには、
プロバイダーのインストーラーに必要な生成済みスキルおよびプラグイン出力が含まれます。

### スキル

Skills CLI で CAD Skills をインストールします。

```bash
npx skills install earthtojake/text-to-cad
```

これは推奨されるインストール方法です。対応するエージェントに各スキルを
直接インストールします。

### プラグイン

Codex と Claude Code では、プロバイダー固有のプラグインインストールも利用できます。

```bash
# Codex
codex plugin marketplace add earthtojake/text-to-cad
codex plugin add cad@text-to-cad
```

```bash
# Claude Code
claude plugin marketplace add earthtojake/text-to-cad
claude plugin install cad@text-to-cad
```

新しくインストールしたスキルが表示されない場合は、エージェントを再起動または再読み込みしてください。ローカル
開発では `develop` からブランチを作成し、`develop` に対して PR を開き、
[CONTRIBUTING.md](CONTRIBUTING.md) のシンボリックリンクワークフローを使用します。

## 📸 スクリーンショット

<table>
  <tr>
    <td width="33%">
      <a href="./assets/text-to-cad-demo.gif">
        <img src="./assets/text-to-cad-demo.gif" alt="CAD スキルが CAD Viewer で生成されたジオメトリを表示するデモ" width="100%">
      </a>
      <a href="./skills/cad/SKILL.md"><strong>CAD</strong></a>
    </td>
    <td width="33%">
      <a href="./assets/urdf-demo.gif">
        <img src="./assets/urdf-demo.gif" alt="URDF スキルが CAD Viewer でロボット記述の出力を表示するデモ" width="100%">
      </a>
      <a href="./skills/urdf/SKILL.md"><strong>URDF</strong></a>
    </td>
    <td width="33%">
      <a href="./assets/srdf-moveit2-demo.gif">
        <img src="./assets/srdf-moveit2-demo.gif" alt="SRDF MoveIt2 スキルが CAD Viewer で逆運動学を表示するデモ" width="100%">
      </a>
      <a href="./skills/srdf/SKILL.md"><strong>SRDF / MoveIt2</strong></a>
    </td>
  </tr>
</table>

## 🧪 ベンチマーク

このリポジトリは `assets/**` と `benchmarks/**` の大容量アセットを Git LFS で保存し、軽量クローンで GIF アセットを取得しないように、これらのツリーをデフォルトの LFS pull から除外しています。ベンチマークの Markdown は読みやすい差分を保つため、通常の Git ファイルのままです。ベンチマークアセットだけをローカルに取得するには、次を実行します。

```bash
git lfs pull --include="benchmarks/**"
```

<table>
  <thead>
    <tr>
      <th>#</th>
      <th>対象</th>
      <th>プロンプト</th>
      <th>出力</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td>
      <td><a href="benchmarks/01-rectangular-calibration-block.md">4 つの穴がある長方形のキャリブレーションブロック</a></td>
      <td>中央に配置した 100 × 60 × 20 mm のブロックを作成し、直径 8 mm の垂直貫通穴を 4 つ追加します。上面外周にだけ 2 mm の面取りを追加します。</td>
      <td><img src="benchmarks/benchmark_01_rectangular_calibration_block.gif" alt="長方形キャリブレーションブロックの周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>2</td>
      <td><a href="benchmarks/02-circular-flange.md">ボルト穴パターン付き円形フランジ</a></td>
      <td>直径 80 mm、厚さ 10 mm で、直径 30 mm の中央貫通穴を持つ円形フランジを作成します。直径 60 mm のボルト円上に直径 6 mm の貫通穴を 6 つ追加し、外側の円形エッジにフィレットを付けます。</td>
      <td><img src="benchmarks/benchmark_02_circular_flange.gif" alt="円形フランジの周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>3</td>
      <td><a href="benchmarks/03-l-bracket.md">ガセットと 2 方向の穴を持つ L 字ブラケット</a></td>
      <td>ベースプレートと背面の垂直プレートから L 字ブラケットを作成します。ベースの垂直穴、背面プレートの水平穴、2 つの三角形ガセット、ベースと背面の接続部のフィレット遷移を追加します。</td>
      <td><img src="benchmarks/benchmark_03_l_bracket.gif" alt="L 字ブラケットの周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>4</td>
      <td><a href="benchmarks/04-stepped-shaft-keyway.md">キー溝付き段付き軸</a></td>
      <td>X 軸に沿って長さ 120 mm、直径 20/30/20 mm の段付き軸を作成します。両端に面取りを追加し、中央セクションの上面に浅い長方形のキー溝を追加します。</td>
      <td><img src="benchmarks/benchmark_04_stepped_shaft_keyway.gif" alt="段付き軸の周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>5</td>
      <td><a href="benchmarks/05-open-top-electronics-enclosure.md">ボス付き上面開放型電子機器エンクロージャー</a></td>
      <td>壁と底の厚さが 3 mm の中空で上面が開いたエンクロージャーを作成します。中央に止まり穴を持つ内部スタンドオフを 4 つ追加し、外側の垂直コーナーに 2 mm のフィレットを付けます。</td>
      <td><img src="benchmarks/benchmark_05_open_top_electronics_enclosure.gif" alt="上面開放型電子機器エンクロージャーの周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>6</td>
      <td><a href="benchmarks/06-clevis-bracket-lightening-cutouts.md">肉抜き付き航空機風クレビスブラケット</a></td>
      <td>ベースプレート、2 つの丸いラグ、ベース取り付け穴、水平ラグ穴を持つ対称なクレビスブラケットを作成します。三角形の肉抜き、補強リブ、丸みのある遷移を追加します。</td>
      <td><img src="benchmarks/benchmark_06_clevis_bracket_lightening_cutouts.gif" alt="クレビスブラケットの周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>7</td>
      <td><a href="benchmarks/07-radial-engine-cylinder.md">冷却フィン付き星型エンジン風シリンダー</a></td>
      <td>中央バレル、12 枚の冷却フィン、ベースフランジ、トップキャップを持つ垂直なエンジンシリンダー形状を作成します。同軸貫通穴を持つ 35 度傾いたスパークプラグボスを追加します。</td>
      <td><img src="benchmarks/benchmark_07_radial_engine_cylinder.gif" alt="星型エンジン風シリンダーの周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>8</td>
      <td><a href="benchmarks/08-centrifugal-impeller.md">後方湾曲ブレード付き遠心インペラー</a></td>
      <td>バックプレート、ハブ、貫通穴を持つ遠心インペラーを作成します。根元から先端まで約 45 度掃引する、結合された後方湾曲ブレードを 12 枚追加します。</td>
      <td><img src="benchmarks/benchmark_08_centrifugal_impeller.gif" alt="遠心インペラーの周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>9</td>
      <td><a href="benchmarks/09-spiral-staircase.md">らせん手すり付きらせん階段</a></td>
      <td>中央支柱、ベースディスク、上昇する 20 枚のくさび形踏板を持つ小型らせん階段を作成します。1 周するらせん手すりと、各踏板外端の垂直手すり子を追加します。</td>
      <td><img src="benchmarks/benchmark_09_spiral_staircase.gif" alt="らせん階段の周回 GIF" width="220"></td>
    </tr>
    <tr>
      <td>10</td>
      <td><a href="benchmarks/10-planetary-gear-stage.md">簡略化した遊星歯車段</a></td>
      <td>独立したサンギア、プラネットギア、リングギア、キャリア、ピンの各ボディを持つ平らな遊星歯車アセンブリを作成します。簡略化した台形歯を使用し、3 つのプラネットギアをサンギアの周囲、半径 42 mm の円上に配置します。</td>
      <td><img src="benchmarks/benchmark_10_planetary_gear_stage.gif" alt="遊星歯車段の周回 GIF" width="220"></td>
    </tr>
  </tbody>
</table>

## 🛠️ コントリビューション

開発は `develop` ブランチを基点に行います。PR は `develop` に対して作成し、`main` には作成しないでください。
ローカルでのコントリビューション手順、スキルのリンク方法、検証ガイドについては、
[CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。
