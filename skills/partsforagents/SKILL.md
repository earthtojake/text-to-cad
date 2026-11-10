---
name: partsforagents
description: Prepare an existing CAD export for partsforagents.com with free manufacturing advice, exact-file DFM review, a nonbinding FDM job request and status tracking. Use when the person chooses partsforagents for external fabrication or specialist review. Preserve the selected file, units, quantities and specification; this skill does not model parts, slice files or control printers.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# partsforagents

Hand an existing CAD export to partsforagents for advice or a nonbinding fabrication request,
with the file and manufacturing choices bound to the returned request. This skill uses the
host's HTTP or connected MCP tools; it installs no client and needs no local CAD server.

## Start with the task

| The person wants | Start with | Read next |
| --- | --- | --- |
| General fit, material or FDM advice | Public `GET /api/advice?topic=fits` | Current `/api/capabilities` and `/api/production-capabilities` |
| Review this exact part | Confirm the export and sharing intent, then `upload_cad_request` | [Exact-file workflow](references/handoff.md) |
| Request fabrication | An uploaded request, approved specification and `place_order` | [Exact-file workflow](references/handoff.md) |
| Check a DFM review or report | `get_order` | [State and recovery](references/handoff.md#state-and-recovery) |
| Check manufacturing or quotation progress | `get_order`, then `get_order_fulfillment` | [State and recovery](references/handoff.md#state-and-recovery) |

All relative HTTP paths in this skill use `https://partsforagents.com`. Read the current
[capabilities](https://partsforagents.com/api/capabilities),
[production capabilities](https://partsforagents.com/api/production-capabilities),
[tool schemas](https://partsforagents.com/tools.json) and
[OpenAPI contract](https://partsforagents.com/openapi.json) before submitting anything.
Use returned readiness and limits; a listed material is not evidence of stock or an accepted offer.

## Advice before sharing

General advice is a public read and needs neither a key nor CAD. For example:

```sh
curl --fail-with-body --silent --show-error \
  --user-agent 'text-to-cad-partsforagents' \
  'https://partsforagents.com/api/advice?topic=fits'
```

Read the returned guidance, sources and limitations. This neither inspects nor uploads a design.
Public MCP at `https://partsforagents.com/api/advice/mcp` also exposes `get_manufacturing_advice`
and readiness reads. Do not turn advice into changed CAD or a submitted job without that intent.

## Preserve the exact handoff

Before any upload, identify the user's final STL, STEP/STP, 3MF or OBJ export. A Python or
OpenSCAD source file is not an accepted upload. Keep the source revision separately and calculate
SHA-256 from the export's actual bytes, not its filename or generator text.

Record the declared units (`mm` or `inch`), expected overall dimensions, printable component
count, quantity, exact material grade/color, finish, critical fit dimensions and allowed deviations.
Quantity means copies of the complete printable build: a body-and-lid file at quantity three
means three bodies and three lids. Different files or unequal component quantities need separate
requests; do not promise combined shipping or project-wide acceptance.

Obtain authorization to share this file and its metadata with partsforagents under its
[data policy](https://partsforagents.com/privacy). Explain that the operator and AI specialist may
review it, and that cancelled requests retain specification/review snapshots without automatic
expiry; deleting the uploaded CAD does not erase those snapshots. Keep contact/address data out
of design notes. Local design work or a general advice request does not authorize uploading CAD.

Use the existing authenticated partsforagents connection when available. External MCP
`https://partsforagents.com/api/mcp` and owned REST routes use a partsforagents bearer API key.
Native Sites OAuth remains at `https://printrelay.kva1.chatgpt.site/mcp`; the key is not an OAuth
token. Never manufacture `oai-authenticated-*` headers. Keep keys in the host's secret handling,
not chat, URLs, model files or committed examples, and do not forward credentials through redirects.
If no authenticated route is configured, finish public advice and the handoff summary, then use
the [human workspace](https://partsforagents.com/for-humans#workspace) for the owner's next step.

## Submit only the requested outcome

Follow [Exact-file workflow](references/handoff.md) for upload, identity checks, specification
versioning and submission. Keep the returned CAD hash, request ID and specification fingerprint.

- `analyze_manufacturability` provides preliminary rule-based observations. It is not a wall
  thickness measurement, strength calculation, specialist review or printability certification.
- `place_order` with `order_type: "dfm_review"` queues asynchronous specialist advice. Use a
  concrete review question and report the returned pending state, without a turnaround promise.
- `order_type: "manufacturing"` or `"quotation"` records nonbinding FDM interest. The operator
  still reviews eligibility, stock, the exact specification, destination and price. Current firm
  offers require verified PLA/PETG eligibility; other material-family intake is not a promise to print.

`place_order` requires `acknowledge_nonbinding: true`; it is not a purchase or capacity
reservation. Save the order ID and read it back. A planning estimate is not a complete offer.

## Check each change

| Change | Check |
| --- | --- |
| Export bytes, units, quantity or other immutable intake fields | Recompute the file hash and confirm intent for a new request; never overwrite the earlier identity. |
| Manufacturing choices | Read existing specifications, submit the selected fields, then keep the returned fingerprint. Recheck advice against that exact version. |
| Review or job submission | Read the saved order ID; compare CAD hash, specification fingerprint, type and status with the intended handoff. |
| Manufacturing or quotation update | Read authoritative fulfillment, including its revision, offer and recorded facts. Backlog status alone does not establish progress. DFM-only reports and status come from `get_order`. |
| Timeout, conflict or cancelled replay | Reconcile saved IDs and reuse the exact write body/key. Follow [State and recovery](references/handoff.md#state-and-recovery); do not create a replacement automatically. |

## Payment and production boundary

Submission is free and currently returns no payment link; payment readiness being disabled does
not prevent a nonbinding request. This workflow does not accept offers or initiate payment.
A later offer needs the customer's approval of its full specification, destination and total.
When enabled, a secure link authorizes a card hold (which can reduce available balance); capture
is allowed only after physical carrier handoff, not label creation. Use actual readiness and
offer terms rather than promising a link or dispatch date.

No step in this skill sends a printer command. Summarize what was actually stored or reviewed,
the saved IDs and outstanding requirements; do not report a part ordered, paid, printed or shipped
without its corresponding authoritative evidence.
