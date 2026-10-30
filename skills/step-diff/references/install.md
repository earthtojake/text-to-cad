# Installing specify-core

`specify-core` is one self-contained binary per platform, published with each release of
[pzfreo/specify-core-rust](https://github.com/pzfreo/specify-core-rust/releases). Each archive
has a `.sha256` file beside it; check it before running the binary. Keep the binary in a cache
directory of its own, one per version, and reuse it.

Release used here: **v0.1.3**. A newer release on the releases page is used the same way.

| Platform | Archive |
| --- | --- |
| macOS, Apple silicon | `specify-core-v0.1.3-aarch64-apple-darwin.tar.gz` |
| Linux, x86-64 | `specify-core-v0.1.3-x86_64-unknown-linux-gnu.tar.gz` |
| Windows, x86-64 | `specify-core-v0.1.3-x86_64-pc-windows-msvc.zip` |

macOS and Linux:

```bash
v=v0.1.3; t=aarch64-apple-darwin   # or x86_64-unknown-linux-gnu
dir="$HOME/.cache/specify-core/$v"; mkdir -p "$dir" && cd "$dir"
base="https://github.com/pzfreo/specify-core-rust/releases/download/$v"
curl -fsSLO "$base/specify-core-$v-$t.tar.gz" -O "$base/specify-core-$v-$t.tar.gz.sha256"
shasum -a 256 -c "specify-core-$v-$t.tar.gz.sha256"   # Linux: sha256sum -c
tar xzf "specify-core-$v-$t.tar.gz"
"$dir/specify-core-$v-$t/specify-core" --help
```

Windows (PowerShell): download the `.zip` and its `.sha256` from the same release, compare
`(Get-FileHash specify-core-v0.1.3-x86_64-pc-windows-msvc.zip).Hash` with the file's hash,
expand it, and run `specify-core.exe` from the expanded folder.

Other platforms have no binary yet: tell the user, and offer the browser comparison at
<https://editor.draftwright.io/diff> instead.
