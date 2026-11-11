---
title: Document types
description: What a document type is in text-to-cad, how each one is named, and what an operation does to it.
---

A document type is what is in a file that text-to-cad shows: a STEP, a GLB, a KiCad board. Each type has one lowercase id, the same everywhere. In Python it is `cad.step`, on the command line `cad step`. The id for 3MF is `threemf`, because an id has to be a valid Python name.

One type, [`model`](/docs/document-types/model), has no file. It is a model built from code, held by the engine and addressed by its document id.

An operation is something you can do to a document of a type, such as `export`, `snapshot`, `inspect`, or a check like `dfm`, `drc` or `validate`. You run one as `cad <type> <operation>`. Each type's page lists its operations.

A file that text-to-cad only writes or checks, and never shows, is not a document type. An MJCF, MuJoCo's own model file, is the example: it belongs to the [MuJoCo](/docs/integrations/mujoco) integration.
