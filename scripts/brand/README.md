# Brand assets

The source SVGs live in `apps/docs/public/brand/`. Artwork authoring stays local;
ordinary builds consume the committed assets.

After updating the vectors, refresh the app and plugin icons from the repository root:

```sh
node scripts/brand/export-logos.mjs
```

The exporter uses sharp from the docs dependencies to write transparent PNGs,
PNG and ICO favicons for the docs site and viewer, shared UI wordmarks, and
Codex and Claude plugin icons. Commit the refreshed outputs together.

The animated SVGs play their own SMIL animation. Pages offer static SVGs for
reduced motion. Keep the separate loading icon assets unchanged; see
[their provenance](../../packages/ui/src/assets/README.md).
