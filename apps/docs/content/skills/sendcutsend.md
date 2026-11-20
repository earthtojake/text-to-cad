---
title: sendcutsend
description: The sendcutsend skill checks DXF and STEP files against SendCutSend's published guidelines before you upload them, and does not talk to your account.
---

SendCutSend is an online service that laser cuts, routes and bends parts from files you upload. The `sendcutsend` skill is a pre-upload check of a DXF or STEP file against the guidelines SendCutSend publishes, and it gives you a report. It is not an official SendCutSend integration, it does not talk to your SendCutSend account, and SendCutSend's own upload and quote have the last word.

## How it works

The check starts from the order context: file type, process (laser cutting, CNC routing, bending, tapping, countersinking, hardware insertion, finishing), material or SKU, thickness, quantity, finish. Without it, your agent lists candidate materials and thicknesses from SendCutSend's data and asks you to choose before it gives a verdict.

SendCutSend's three published source files are fetched fresh each time: the ordering guide (workflow and file format rules), the catalog JSON (materials, thicknesses, size limits and services) and the specs JSON (engineering values such as hole, bridge and bend figures, joined to the catalog by exact SKU). They are treated as data that can change or have gaps, not as a stable API.

The measurements come from the actual upload file, not the script that made it. A model's upload is exported first with `cad model export <id> part.step` or `part.dxf`. `cad step inspect` gives a STEP's bodies, bounds and volume, or reads one face, such as a bend's cylinder and its radius. text-to-cad's own sheet-metal check runs on the file with the SKU's figures where the specs list them:

```bash
cad step inspect part.step 'face 9'
cad step dfm part.step --process sheet --material <material> --thickness <mm> --json
cad dxf dfm part.dxf --material <material> --thickness <mm> --json
```

The `dfm` check is text-to-cad's, not SendCutSend's ([manufacturing checks](/docs/cad#manufacturing-checks)); its measurements are compared with the cited requirements. For a DXF, the report's checks include units (`$INSUNITS` must be `1` for inches or `4` for mm, otherwise it is a scale error and nothing is rescaled), closed cut profiles, duplicate or overlapping geometry, unsupported text, dimensions or images, and the flange length on both sides of each bend line. For a STEP, they include readability, a solid body, units, bounding box, thickness and, where bending is in scope, bend radii against the SKU's tooling radius.

The report gives the file, the assumed order context, the source files and the date they were fetched, the measured facts, and a findings table. Each row has a status (pass, fail or need more info), the evidence, and a rule source that links to the document or JSON field path, or says "Direct file inspection". The verdict is "Ready to upload for this assumed context", "Needs edits before upload" or "Insufficient context to validate".

## Limits

- It states only limits the sources give. A missing, unparsable or `N/A` field makes a row "need more info", not a pass or a fail.
- It cannot say whether SendCutSend's upload will accept the file or what it will quote.
- A verdict is only as good as the order context. A different material, thickness or service changes the limits.
- It needs network access to fetch the three source files. If they cannot be fetched, the report says so and gives no ready verdict for the checks that depend on them.

## Ask for it

- "Check `bracket.dxf` against SendCutSend's guidelines for laser cutting. The material is 5052 aluminium, 0.063 in."
- "Is `housing.step` ready to upload to SendCutSend for CNC routing? Tell me what to change."

## The skill

The skill is [`sendcutsend`](repo:skills/sendcutsend/SKILL.md). Its references:

- [SendCutSend's official sources](repo:skills/sendcutsend/references/official-sources.md) and [the report template](repo:skills/sendcutsend/references/report-template.md)

Related pages: [manufacturing checks](/docs/cad#manufacturing-checks), [DXF profiles and flat patterns](/docs/cad#dxf-profiles-and-flat-patterns) for making a cut file, and [engineering-drawing](/docs/engineering-drawing).
