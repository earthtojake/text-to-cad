# Installing text-to-cad

One command installs text-to-cad and its plugin in every agent app on your computer:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://www.texttocad.dev/install.ps1 | iex
```

It installs [uv](https://docs.astral.sh/uv/) if it is missing, installs the newest release of
text-to-cad and the `cad` command, then installs the plugin in each agent app it finds, with that
app's own command (below). It prints one line per app. Run it again to update. It takes no options.

On Windows, run it in Windows Terminal or PowerShell, not in a Windows Store app's shell such as
the Claude desktop app's: Windows keeps what such an app's commands write inside that app, where no
terminal and no other app finds it. The command names `www.texttocad.dev` because Windows
PowerShell 5.1 does not follow the redirect from `texttocad.dev`.

## Install by hand

Install the plugin in each app with the commands under its name. Install it once per app: two
copies show every skill twice. Restart the app afterwards.

The plugin's skills run text-to-cad through the `cad` command. The first time a skill needs it and
it is missing, the agent installs it with the line in the skill's setup, which needs uv:

```bash
uvx --no-config --managed-python --python 3.14 --from cad-server==0.11.11 cad setup
```

The runtime supports Python 3.13+; the commands use uv-managed Python 3.14.

The commands take the `latest` branch: the plugin alone, moved to each release once it is on PyPI.
Devin CLI, Antigravity and Factory Droid cannot name a branch here and install `main`, where
development happens.

Claude Code, Codex and Cursor are tested before every release. Gemini CLI, Grok Build and Hermes
Agent are installed on the computer we test on. The other entries follow each vendor's
documentation.

### Claude Code

```bash
claude plugin marketplace add earthtojake/text-to-cad#latest
claude plugin install text-to-cad@earthtojake
```

Claude Code gets the skills alone and shows models in your browser. Claude Desktop's Code tab runs
Claude Code and uses the same plugin.

To update: `claude plugin marketplace update earthtojake`, then
`claude plugin update text-to-cad@earthtojake`.

### Codex

text-to-cad is in Codex's plugin directory: in the Codex app, open **Plugins** and install
text-to-cad. The directory updates its copy.

Or install it from this repository:

```bash
codex plugin marketplace add earthtojake/text-to-cad --ref latest
codex plugin add text-to-cad@earthtojake
```

In the Codex app the plugin also brings the CAD viewer: **CAD** in the sidebar, a **CAD** tab beside
each thread, and *Open with CAD* for model files.

To update: `codex plugin marketplace upgrade earthtojake`.

### Cursor

```bash
git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad
```

Cursor also loads the plugin installed in Claude Code: if Claude Code has it, skip this.

To update: `git -C ~/.cursor/plugins/local/text-to-cad pull`.

### Gemini CLI

text-to-cad is in the [Gemini CLI extensions gallery](https://geminicli.com/extensions). Install it
from this repository's `latest` branch:

```bash
gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent
```

To update: `gemini extensions update text-to-cad`.

### Grok Build

```bash
grok plugin install earthtojake/text-to-cad@latest --trust
grok plugin enable text-to-cad
```

Grok Build also loads the plugin installed in Claude Code: if Claude Code has it, skip this.

To update: `grok plugin update text-to-cad`.

### Hermes Agent

```bash
hermes plugins install earthtojake/text-to-cad --no-enable --force \
  --ref "$(git ls-remote https://github.com/earthtojake/text-to-cad latest | cut -f1)"
hermes plugins enable text-to-cad --no-allow-tool-override
```

Hermes takes a branch only as its commit, which `git ls-remote` looks up. Its install scan stops at
the `curl ... | sh` line in the plugin's text (the install command) until `--force` is given.

To update, run the same commands again.

### Antigravity

```bash
agy plugin install https://github.com/earthtojake/text-to-cad
```

To update, run the same command again.

### Devin CLI

```bash
devin plugins install earthtojake/text-to-cad
```

To update: `devin plugins update text-to-cad`.

### Factory Droid

```bash
droid plugin marketplace add earthtojake/text-to-cad
droid plugin install text-to-cad@text-to-cad --scope user
```

To update: `droid plugin marketplace update text-to-cad`, then
`droid plugin update text-to-cad@text-to-cad --scope user`.

### GitHub Copilot CLI

```bash
copilot plugin marketplace add earthtojake/text-to-cad#latest
copilot plugin install text-to-cad@earthtojake
```

To update: `copilot plugin update text-to-cad`.

### Kimi Code

Type this inside Kimi Code:

```text
/plugins install https://github.com/earthtojake/text-to-cad/tree/latest
```

To update, type it again. The install command cannot do this one for you.

### Muse

```bash
git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad
muse plugins install ./text-to-cad
muse plugins approve text-to-cad
```

Muse keeps its own copy, so the clone can be deleted afterwards.

To update: `muse plugins update text-to-cad`.

### Pi

```bash
pi install git:github.com/earthtojake/text-to-cad@latest
```

To update, run the same command again: `pi update` does not move a named branch.

### Qwen Code

```bash
qwen extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent
```

To update: `qwen extensions update text-to-cad`.

### Other agents

These agents take the skills alone, copied into their own skills folder. The install command does
it for each one it finds.

| Agent | Skills folder |
| --- | --- |
| Amp | `~/.config/amp/skills` |
| Cline | `~/.cline/skills` |
| Goose | `~/.config/goose/skills` |
| Kilo Code | `~/.kilo/skills` |
| Kiro CLI | `~/.kiro/skills` |
| OpenClaw | `~/.openclaw/skills` |
| OpenCode | `~/.config/opencode/skills` |
| Roo Code | `~/.roo/skills` |
| Trae | `~/.trae/skills` |
| Windsurf | `~/.codeium/windsurf/skills` |

By hand, copy each folder under `skills/` on the `latest` branch into the agent's folder, for
example for Cline:

```bash
git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad text-to-cad
mkdir -p ~/.cline/skills
cp -R text-to-cad/skills/* ~/.cline/skills/
```

To update, copy them again, or run the install command.

Zed and GitHub Copilot in VS Code are not supported yet. No route for your agent?
[Request one](https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20).

## Updating

Run the install command again: it installs the newest release and updates the plugin in every app
it finds. To update one app, run the update command under its name. A copy from a plugin directory
is updated by that directory.

text-to-cad does not update itself. When a newer release is out, `cad` says so after a command's
output, with the command to run. A chat that is already open keeps its release; a new chat uses the
new one.

## Removing

Remove the plugin from each app with that app's own command:

| App | Remove |
| --- | --- |
| Claude Code | `claude plugin uninstall text-to-cad@earthtojake`, then `claude plugin marketplace remove earthtojake` |
| Codex | `codex plugin remove text-to-cad@earthtojake`, then `codex plugin marketplace remove earthtojake` |
| Cursor | `rm -rf ~/.cursor/plugins/local/text-to-cad` |
| Gemini CLI | `gemini extensions uninstall text-to-cad` |
| Grok Build | `grok plugin uninstall text-to-cad` |
| Hermes Agent | `hermes plugins remove text-to-cad` |
| Antigravity | `agy plugin uninstall text-to-cad` |
| Devin CLI | `devin plugins remove text-to-cad` |
| Factory Droid | `droid plugin uninstall text-to-cad@text-to-cad`, then `droid plugin marketplace remove text-to-cad` |
| GitHub Copilot CLI | `copilot plugin uninstall text-to-cad`, then `copilot plugin marketplace remove earthtojake` |
| Pi | `pi remove git:github.com/earthtojake/text-to-cad@latest` |
| Qwen Code | `qwen extensions uninstall text-to-cad` |
| Kimi Code, Muse | remove text-to-cad in the app's plugin manager |
| Other agents | delete our skills from the agent's skills folder |

Then remove text-to-cad itself:

```bash
cad uninstall
```

It removes every release of text-to-cad on your computer, its settings and data, and the `cad`
command. It asks first; where nothing can ask, add `--yes`. It changes no app. What uv downloaded
stays in uv's cache until you run `uv cache prune`.

## What it needs

- A network connection the first time a release is installed. A release takes about 240 MB to
  download and about 620 MB on disk, most of it the CAD kernel (OCP and build123d).
- On Linux, the system's OpenGL library, `libGL.so.1` (the `libgl1` package on Debian and Ubuntu).
- On Windows 11, Smart App Control turned off, or WSL. The CAD kernel's wheel ships an unsigned
  native module, which Smart App Control blocks: every `cad` command and `import build123d` then
  fails with `ImportError: DLL load failed while importing OCP`, and Event Viewer records Event ID
  3077 under CodeIntegrity › Operational. Smart App Control has no per-app exception; turning it
  off is under Settings › Privacy & security › Windows Security › App & browser control › Smart App
  Control settings, and once off it can be turned back on only by reinstalling Windows. Under WSL it
  does not apply.
