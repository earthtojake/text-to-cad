---
title: Contributing
description: How to take part in text-to-cad, where the code lives, how to set up a development checkout, and the guides for common changes.
---

text-to-cad is MIT-licensed and built in the open. Here is how to take part and where to start.

## Ways to take part

- **Bugs and plugin requests**: [open an issue](https://github.com/earthtojake/text-to-cad/issues/new). A bug report with the model script and the output of `cad doctor --check` is the fastest to fix. An agent app without a plugin gets one on request.
- **Questions, ideas and what you made**: the [Discord](https://discord.gg/5FGB9DwJYU). Say what the skills got wrong too, because that is what improves them.
- **Code, skills and models**: a new skill goes in `skills/`, an example model in `models/`, and fixes go anywhere.
- **Security problems**: report them privately, as [SECURITY.md](repo:SECURITY.md) says.

## Where the code lives

- `skills/`: the agent skills and their references. The skills are the product.
- `packages/`: the published Python distributions (`cad`, the library; `cad-server`, the server and the `cad` command; `cad-mcp`, the shim an agent app starts) and the shared JavaScript packages.
- `apps/`: the viewer's web client (`apps/web`), the CAD app (`apps/mcp`), this documentation site (`apps/docs`) and the API behind the site (`apps/api`).
- `models/`: example models, each built with `python model.py`.
- `tests/`: the test suites for the skills, the packages, the viewer and repository-wide policy.
- `docs/`: the install guide, the contributing guides and the migration guides.

How the pieces fit together is written for contributors in the repository: [AGENTS.md](repo:AGENTS.md) maps the tree and its rules, the [engine README](repo:packages/cad-server/src/cad_server/engine/README.md) covers the server's daemon, its workers, documents and exports, each package's README holds its own laws (start with [the library's](repo:packages/cad/README.md)), and [SECURITY.md](repo:SECURITY.md) draws the trust boundary.

## Setting up a checkout

Branch from `main` and open pull requests against `main`. External contributors fork the repository first. In outline:

1. Clone the repository and create a branch.
2. Create a Python 3.14 virtual environment and install `requirements-dev.txt`.
3. Install Node.js 22 if you work on the viewer, the shared packages or the docs site.
4. Run the smallest check that covers your change, such as `scripts/test/test-python.sh` with the test paths you changed.
5. To try skills and the plugin in an agent app, use `scripts/install/dev_install.py <host>`.

[CONTRIBUTING.md](repo:CONTRIBUTING.md) has the exact commands, the per-platform set-up and how to test in each agent app. A change that touches the plugin, the skills or the CAD app should keep Claude Code, Codex and Cursor working. An agent working in the repository starts at [AGENTS.md](repo:AGENTS.md).

Releases are made by the maintainers. Do not change `VERSION` in a normal pull request.

## Guides in the repository

These are written for whoever changes the repository, an agent as often as a person, so they live there and open on GitHub.

- [Writing a skill](repo:docs/contributing/writing-a-skill.md): add a workflow for your agent.
- [Adding a document type](repo:docs/contributing/adding-a-document-type.md): teach text-to-cad a new kind of file.
- [Adding an integration](repo:docs/contributing/adding-an-integration.md): connect a tool text-to-cad runs for you.
- [Testing](repo:docs/contributing/testing.md): the rules for tests, adding one, and reading a red CI run.
