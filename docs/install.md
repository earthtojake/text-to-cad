# Installing text-to-cad

One command installs text-to-cad and its plugin in every agent app on your computer:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://www.texttocad.dev/install.ps1 | iex
```

It does five things, and nothing else:

1. Installs [uv](https://docs.astral.sh/uv/) if it is missing. Where uv is older than 0.9.0, it updates
   it, or installs a newer one beside it with uv's own installer.
2. Installs `cad`, the command text-to-cad runs on, as a uv tool, at the newest release, where no
   cad is installed. Where the cad there does not start, it installs it again. Where it installed
   cad and cad's folder is not on your PATH, it runs uv's own `uv tool update-shell`, which adds it
   for new terminals (on macOS and Linux in your shell's profile, on Windows in your user PATH).
   Setting `UV_NO_MODIFY_PATH` stops that.
3. Where cad was installed already, brings it up to date with its own `cad update`: the newest
   release of its major version ([Updating](#updating)). While cad's server is busy the update
   waits for it, 11 minutes at most. It says one line as it begins, and in its place one line of what
   came of it: the release cad was updated to, that it is the newest already, or why cad was not
   updated now, which never stops the run: cad updates itself.
4. Hands the agent apps to cad, by running `cad plugin install`. That installs or updates the
   plugin in each agent app it finds, with that app's own command (below), all but Kimi Code, which
   you install by hand; and removes what earlier releases of text-to-cad left in those apps. It
   prints one line per app.
5. Turns on the plugin's automatic updates, with cad's own `cad plugin update auto on`
   ([Updating](#updating)).

It takes no options and does not start cad's server. Run it again at any time to bring cad and the
plugin up to date in every app. To do step 4 alone, leaving cad and the plugin's automatic updates as
they are, run:

```bash
cad plugin install
```

In a terminal, `cad plugin install` builds the CAD logo before it starts on the apps, marks each
app's line, and keeps a live line under them that names the app it is setting up and the command it
is running. `NO_COLOR` turns that off. So do `TERM=dumb`, `CI`, and output that goes to a pipe or a
file, which get the plain lines alone.

cad 0.11.12 and 0.11.13 have no `cad plugin install`; there, `cad plugin update` updates the plugin.
Where the install command finds one of them and could not update it, or could not install cad at
all, it runs the newest release's instead, which uv downloads once and does not install: `uv tool
run cad@latest plugin install`.

Those two releases, and the move from 0.10.0 to 0.11.11 ([From an earlier
release](#from-an-earlier-release)), run the install command by themselves. Run by cad, it skips
step 3 and leaves your PATH as it is: only your own run updates cad or changes the PATH.

Where any app it found failed, cad keeps no release as the one the plugin is up to date for, and
runs `cad plugin install` again later where the plugin's automatic updates are on
([Updating](#updating)): at most three times for one release, an hour or more apart.

It removes only what is ours: a skill counts as ours only where its `SKILL.md` says it comes from
text-to-cad's repository, so a skill of yours with the same name is left as it is. A copy from a
plugin store (Codex's or Claude's) is never touched.

Your agent shows each model it makes in a viewer. In the Codex app that is a **CAD** tab beside the
thread; every other app opens it in its own browser, or gives you a link to open in yours.

On Windows, run it in Windows Terminal or PowerShell, not in a Windows Store app's shell such as
the Claude desktop app's: Windows can keep what such an app's commands write inside that app, where no
terminal and no other app finds it. The command names `www.texttocad.dev` because Windows
PowerShell 5.1 does not follow the redirect from `texttocad.dev`.

## What it sends

`cad plugin install` counts each run in cad's telemetry: who started it (you,
the install command or cad's server), how it ended, how many seconds it took, what the terminal was
shown (the logo, and in which colours), and how many agent apps it found on your computer and how many
of those failed, as numbers. cad names an agent app only where its install failed: by cad's own short
name for it (`claude`, `codex`, `cursor`, ...), with its seconds and one word for why (a command that
did not answer in time, a command that failed, no network, a mistake of cad's own, or anything else).
Which agent apps you have is never sent. Never a path, a message, or a version of an app.
It goes out as the rest of cad's telemetry does: under your random install ID, only after cad has
said in one line that it sends usage stats and crash reports, and never in CI.

The install command sends nothing itself where it ends with a cad that works. Where it fails with
no working cad to count the failure, it sends one anonymous report to `api.texttocad.dev`: a random
ID made for that one run and kept nowhere, the stage that failed (installing uv, downloading
`install.py`, running it, installing cad, running the plugin's step, or a crash of the script), an
exit status, your operating system and processor type, uv's version, and whether a person or cad
ran it. For a crash it adds the error's type and the function names and line numbers in the install
script where it happened, never a message or a path. When you run the command, it says so in one
line near its start, wherever it could send one.

Where cad itself runs the install command (0.11.12 and 0.11.13 do, and the move from 0.10.0 to
0.11.11), nobody reads its output, so it prints no such line. Such a run sends a report only where
cad's settings show that cad had already told you what it sends, or that you said yes, and never
for a failure before `install.py` runs.

To turn both off, set `DO_NOT_TRACK=1` or `CAD_TELEMETRY=0` where the command runs, for example:

```bash
curl -fsSL https://texttocad.dev/install.sh | DO_NOT_TRACK=1 sh
```

On Windows, in PowerShell, which keeps it for that window:

```powershell
$env:DO_NOT_TRACK = "1"; irm https://www.texttocad.dev/install.ps1 | iex
```

`cad telemetry off` turns cad's telemetry off for good, and the install command reads that choice
too. The [privacy policy](https://www.texttocad.dev/privacy-policy) has the details.

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
codex plugin marketplace add earthtojake/text-to-cad --ref latest --sparse .claude-plugin --sparse .codex-plugin --sparse skills --sparse codex.mcp.json
codex plugin add text-to-cad@earthtojake
```

The `--sparse` paths keep Codex to the plugin's files: without them it clones the whole repository, and
its `marketplace upgrade` can run out of time on a slow disk.

To update:

```bash
codex plugin marketplace upgrade earthtojake
codex plugin add text-to-cad@earthtojake
```

In the Codex app the plugin also brings the viewer: **CAD** in the sidebar, a **CAD** tab beside
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

To update: `devin plugins update text-to-cad`. Devin CLI takes a plugin only once you are signed in
(`devin auth login`): until then the install command skips it and says so.

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

cad updates itself to every new release of its major version (the first number: 0 in 0.12.3). While
its server runs, it looks for a new release about once an hour, and installs it once nothing has run
for a minute. To update it now:

```bash
cad update
```

That updates cad alone; the install command, run again, does the same and then updates the plugin.
A new major version never installs itself, because it may need changes on your side: `cad update` and `cad doctor` say when one is out, and this installs it:

```bash
cad update --major
```

The [migration guides](https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations) say what
changes. Automatic updates are on unless you turn them off. To see whether they are on, or to turn them
off or on:

```bash
cad update auto        # says whether they are on
cad update auto off
cad update auto on
```

A cad installed with `uv tool install cad` updates itself; one installed with pip into a project's
own Python never does. Setting `CAD_UPDATE_CHECK=0` (or `CI`) where cad runs turns the check off for
that process, and makes `cad update` refuse there too. You can also update cad with uv yourself:

```bash
cad server stop
uv tool upgrade cad
cad server start
```

Once cad has updated itself, uv keeps it inside its major version, so `uv tool upgrade cad` does too;
`uv tool install cad@latest` takes the newest of all.

### The plugin

The install command turns on the plugin's automatic updates as its last step: each time cad is
newer than the release the plugin is up to date for, cad runs `cad plugin install` once, in the
background, which puts the newest plugin in every agent app it finds. That holds however cad
got newer: by itself, by `cad update`, or by `uv tool upgrade cad` or `pipx upgrade cad`. It happens
the next time cad's server starts or looks after itself with nothing running. A run that fails (any
app failing counts, though the others went well), or that is still running after 15 minutes and is stopped (a minute later for certain, whatever it is
doing), is tried again an hour or more later: at most three runs for one release. To update the plugin now:

```bash
cad plugin install
```

That leaves cad as it is; the install command updates cad first, then runs `cad plugin install`.
(`cad plugin update`, the name 0.11.12 and 0.11.13 give it, still does the same.) One such run goes
at a time: a second waits for the first to end, and `cad update` typed while one is going says so and
updates nothing, so run it again afterwards.

To update one app alone, run the update command under its name. To see whether the plugin's
automatic updates are on, or to turn them off or on:

```bash
cad plugin update auto        # says whether they are on
cad plugin update auto off
cad plugin update auto on
```

They are off until the install command turns them on, or you do: `cad plugin install` alone never
changes them, and cad never changes your apps where you did not ask it to.

A copy from a plugin store (Codex's or Claude's) is updated by that store, on its own schedule. Its
skills may then be older than cad. That is fine: a command the skills used keeps working for at least
30 days after the skills stop using it.

### Staying on an older release

Turn automatic updates off, then install the release you want, for example 0.11.12:

```bash
cad update auto off
cad server stop
uv tool install cad==0.11.12
cad server start
```

Do not run the install command there: run by a person, it updates cad. `cad plugin install` (on
0.11.12 and 0.11.13, `cad plugin update`) brings the plugin up to date and leaves cad as it is. The
newest plugin's skills may ask for a newer cad.

### From an earlier release

A computer on 0.10.0 to 0.11.11 is brought over once, by the updater those releases shipped: it
installs the new cad with uv. Where the install command was used on that computer, it runs it once
more and turns on the plugin's automatic updates; where it was not, your apps are left as they are.
That run is done once cad is installed: an app that failed in it is tried again as on any computer
([The plugin](#the-plugin)), at most three times for one release.
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

- A network connection to install cad, and again the first time a model is built or a STEP or DXF is
  opened, when cad fetches the CAD kernel (OCP and build123d). cad itself is about 130 MB on disk; the kernel about 620 MB.
- On Linux, the system's OpenGL library, `libGL.so.1` (the `libgl1` package on Debian and Ubuntu).
- On Windows 11, Smart App Control turned off, or WSL. The CAD kernel's wheel ships an unsigned
  native module, which Smart App Control blocks: every `cad` command and `import build123d` then
  fails with `ImportError: DLL load failed while importing OCP`, and Event Viewer records Event ID
  3077 under CodeIntegrity › Operational. Smart App Control has no per-app exception; turning it
  off is under Settings › Privacy & security › Windows Security › App & browser control › Smart App
  Control settings, and once off it can be turned back on only by reinstalling Windows. Under WSL it
  does not apply.
