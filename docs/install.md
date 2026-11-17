# Installing text-to-cad

One command installs text-to-cad and its plugin in every agent app on your computer:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://www.texttocad.dev/install.ps1 | iex
```

It does six things, and nothing else:

1. Installs [uv](https://docs.astral.sh/uv/) if it is missing. Where uv is older than 0.9.0, it updates
   it, or installs a newer one beside it with uv's own installer.
2. Installs `cad`, the command text-to-cad runs on, as a uv tool, at the newest release. Where cad
   is installed already, it leaves it as it is: cad updates itself. Where that cad does not start,
   it installs it again.
3. Installs or updates the plugin in each agent app it finds, with that app's own command (below),
   all but Kimi Code, which you install by hand. It prints one line per app.
4. Removes what earlier releases of text-to-cad left in those apps.
5. Where cad's folder is not on your PATH, runs uv's own `uv tool update-shell`, which adds it for
   new terminals (on macOS and Linux in your shell's profile, on Windows in your user PATH). Setting
   `UV_NO_MODIFY_PATH` stops that.
6. Turns on the plugin's automatic updates ([Updating](#updating)).

It takes no options and does not start anything. Run it again at any time to bring the plugin up
to date in every app.

It removes only what is ours: a skill counts as ours only where its `SKILL.md` says it comes from
text-to-cad's repository, so a skill of yours with the same name is left as it is. A copy from a
plugin store (Codex's or Claude's) is never touched.

Your agent shows each model it makes in a viewer. In the Codex app that is a **CAD** tab beside the
thread; every other app opens it in its own browser, or gives you a link to open in yours.

On Windows, run it in Windows Terminal or PowerShell, not in a Windows Store app's shell such as
the Claude desktop app's: Windows can keep what such an app's commands write inside that app, where no
terminal and no other app finds it. The command names `www.texttocad.dev` because Windows
PowerShell 5.1 does not follow the redirect from `texttocad.dev`.

## Install by hand

First install cad, which needs uv:

```bash
uv tool install cad
```

If uv says the `cad` executable already exists, add `--force` after `install`. cad updates itself
([Updating](#updating)). The runtime supports Python 3.11+.

Then install the plugin in each app with the commands under its name. Install it once per app: two
copies show every skill twice. Restart the app afterwards. The plugin's skills run text-to-cad
through the `cad` command; when it is missing, the skill tells your agent how to install it.

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

Claude Code shows models in its browser pane or your browser. Claude Desktop's Code tab runs Claude
Code and uses the same plugin. The install command adds it with the `claude` command; without that
command, add it in Claude Code's plugin manager with the two commands above.

To update:

```bash
claude plugin marketplace update earthtojake
claude plugin update text-to-cad@earthtojake
```

### Codex

#### Codex app

text-to-cad is in the [official Codex plugin directory](https://chatgpt.com/plugins/plugins_6ac32e7e1a74819193e1edd581a99966?open_in_app).

- In the Codex app, click **Plugins** in the sidebar.
- Find **text-to-cad**.
- Click the **+** next to it and follow the prompts.

#### Codex CLI

text-to-cad is in the [official Codex plugin directory](https://chatgpt.com/plugins/plugins_6ac32e7e1a74819193e1edd581a99966?open_in_app).

- Open the plugin search:

  ```text
  /plugins
  ```

- Search for text-to-cad:

  ```text
  text-to-cad
  ```

- Select **Install Plugin**.

The directory updates its copy.

#### From this repository

Or install it from this repository:

```bash
codex plugin marketplace add earthtojake/text-to-cad --ref latest
codex plugin add text-to-cad@earthtojake
```

To update:

```bash
codex plugin marketplace upgrade earthtojake
codex plugin add text-to-cad@earthtojake
```

In the Codex app the plugin also brings the CAD viewer: **CAD** in the sidebar, a **CAD** tab beside
each thread, and *Open with CAD* for model files. It is the only app that gets it.

### Cursor

```bash
git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad
```

Cursor also loads the plugin installed in Claude Code: if Claude Code has it, skip this. Cursor shows
models in its browser.

To update:

```bash
git -C ~/.cursor/plugins/local/text-to-cad pull
```

### Gemini CLI

```bash
gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent
```

To update:

```bash
gemini extensions update text-to-cad
```

### Grok Build

```bash
grok plugin install earthtojake/text-to-cad@latest --trust
grok plugin enable text-to-cad
```

Grok Build also loads the plugin installed in Claude Code: if Claude Code has it, skip this.

To update:

```bash
grok plugin update text-to-cad
```

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

To update:

```bash
copilot plugin update text-to-cad
```

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

To update:

```bash
muse plugins update text-to-cad
```

### Pi

```bash
pi install git:github.com/earthtojake/text-to-cad@latest
```

To update, run the same command again: `pi update` does not move a named branch.

### Qwen Code

```bash
qwen extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent
```

To update:

```bash
qwen extensions update text-to-cad
```

### Other agents

These agents take the skills alone, copied into their own skills folder. The install command does
it for each one it finds.

| Agent | Skills folder |
| --- | --- |
| Amp | `~/.config/amp/skills` |
| Cline | `~/.cline/skills` |
| Goose | `~/.config/goose/skills` |
| Hermes Agent | `~/.hermes/skills` (`$HERMES_HOME/skills` where that is set) |
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

Earlier releases installed a Hermes Agent plugin instead. The install command removes it; by hand,
run `hermes plugins remove text-to-cad`.

Zed and GitHub Copilot in VS Code are not supported yet. No route for your agent?
[Request one](https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20).

## Updating

cad and the plugin update separately.

### cad

cad updates itself. While its server runs, it looks for a new release about once an hour, and
installs it once nothing has run for a minute. To update it now:

```bash
cad update
```

That updates cad alone. Automatic updates are on unless you turn them off. To see whether they are
on, or to turn them off or on:

```bash
cad auto-update        # says whether they are on
cad auto-update off
cad auto-update on
```

Only a cad installed with `uv tool install` updates itself; one installed another way, such as with
pip into a project's own Python, never does. Setting `CAD_UPDATE_CHECK=0` where cad runs turns the
check off for that process. You can also update cad with uv yourself:

```bash
cad server stop
uv tool upgrade cad
cad server start
```

### The plugin

The install command turns on the plugin's automatic updates: each time cad updates itself, it then
runs the install command once, which puts the newest plugin in every agent app it finds. An update
you start with `cad update` does not. To update the plugin now, run the install command again, or:

```bash
cad plugin install
```

To update one app alone, run the update command under its name. To see whether the plugin's
automatic updates are on, or to turn them off or on:

```bash
cad plugin auto-update        # says whether they are on
cad plugin auto-update off
cad plugin auto-update on
```

They are off until the install command turns them on: cad never changes your apps where you did not
run it.

A copy from a plugin store (Codex's or Claude's) is updated by that store, on its own schedule. Its
skills may then be older than cad. That is fine: a command the skills used keeps working for at least
30 days after the skills stop using it.

### Staying on an older release

Turn automatic updates off, then install the release you want, for example 0.11.12:

```bash
cad auto-update off
cad server stop
uv tool install cad==0.11.12
cad server start
```

The install command leaves that cad as it is. It still puts the newest plugin in your apps, and its
skills may ask for a newer cad.

### From an earlier release

A computer on 0.10.0 to 0.11.11 is brought over once, by the updater those releases shipped: it
installs the new cad with uv. Where the install command was used on that computer, it runs it once
more and turns on the plugin's automatic updates; where it was not, your apps are left as they are.
From then on, both update as above. A computer on an older release moves when you run the install
command.

## Removing

Remove the plugin from each app with that app's own command:

| App | Remove |
| --- | --- |
| Claude Code | `claude plugin uninstall text-to-cad@earthtojake`, then `claude plugin marketplace remove earthtojake` |
| Codex | `codex plugin remove text-to-cad@earthtojake`, then `codex plugin marketplace remove earthtojake` |
| Cursor | `rm -rf ~/.cursor/plugins/local/text-to-cad` |
| Gemini CLI | `gemini extensions uninstall text-to-cad` |
| Grok Build | `grok plugin uninstall text-to-cad` |
| Antigravity | `agy plugin uninstall text-to-cad` |
| Devin CLI | `devin plugins remove text-to-cad` |
| Factory Droid | `droid plugin uninstall text-to-cad@text-to-cad`, then `droid plugin marketplace remove text-to-cad` |
| GitHub Copilot CLI | `copilot plugin uninstall text-to-cad`, then `copilot plugin marketplace remove earthtojake` |
| Pi | `pi remove git:github.com/earthtojake/text-to-cad@latest` |
| Qwen Code | `qwen extensions uninstall text-to-cad` |
| Kimi Code, Muse | remove text-to-cad in the app's plugin manager |
| Other agents | delete our skills from the agent's skills folder |

Then stop cad's server and remove cad:

```bash
cad server stop
uv tool uninstall cad
```

That removes the program. Your settings, Recents and the records of your models stay in two
folders, which you can delete by hand:

| | Data | Cache |
| --- | --- | --- |
| macOS | `~/Library/Application Support/cad` | `~/.cache/cad` |
| Linux | `~/.local/state/cad` | `~/.cache/cad` |
| Windows | `%USERPROFILE%\.local\state\cad` | `%USERPROFILE%\.cache\cad` |

`cad doctor` and `cad cache dir` print where they are on your computer; run them before you remove
cad. What uv downloaded stays in uv's cache until you run `uv cache prune`.

## What it needs

- A network connection to install cad, and again the first time a model is built, when cad fetches
  the CAD kernel (OCP and build123d). cad itself is about 110 MB on disk; the kernel about 620 MB.
- On Linux, the system's OpenGL library, `libGL.so.1` (the `libgl1` package on Debian and Ubuntu).
- On Windows 11, Smart App Control turned off, or WSL. The CAD kernel's wheel ships an unsigned
  native module, which Smart App Control blocks: every `cad` command and `import build123d` then
  fails with `ImportError: DLL load failed while importing OCP`, and Event Viewer records Event ID
  3077 under CodeIntegrity › Operational. Smart App Control has no per-app exception; turning it
  off is under Settings › Privacy & security › Windows Security › App & browser control › Smart App
  Control settings, and once off it can be turned back on only by reinstalling Windows. Under WSL it
  does not apply.
