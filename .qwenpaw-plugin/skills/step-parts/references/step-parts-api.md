# step.parts API Reference

## Origins

Default to the API origin `https://api.step.parts`. Use a different origin only when the user supplies another hosted step.parts-compatible API domain. Static HTML pages live on `https://www.step.parts`; GLB and PNG preview URLs in API records point directly at Vercel Blob. STEP URLs are environment-aware and production records use commit-pinned GitHub LFS media. If the API domain does not resolve, treat the hosted service as unavailable and ask for a deployed origin when a live download is required.

## Machine Endpoints

| Endpoint | Use |
| --- | --- |
| `https://www.step.parts/llms.txt` | Human-readable agent guide with endpoint summary and examples. |
| `/v1/parts` | Search, filter, paginate, and retrieve absolute asset URLs. |
| `/v1/parts/{id}` | Fetch one enriched part record by stable id. |
| `/v1/catalog/schema` | JSON Schema, field semantics, result ordering, and family attribute meanings. |
| `/v1/catalog/parts.index.json` | Compact id/name/facet discovery index for cheap lookups before fetching details. |
| `/v1/openapi.json` | OpenAPI 3.1 contract for generating clients/tools. |

## `/v1/parts` Query Parameters

- `q`: tokenized metadata search across id, name, description, category, family, stepSource, productPage, tags, aliases, standard fields, attribute keys, and attribute values. Every token must match.
- `tag`, `category`, `family`, `standard`: repeatable filters. Values may also be comma-separated. Values within one facet are ORed, and selected facet fields are ANDed together.
- `page`: 1-based page number.
- `pageSize`: default `100`, max `500`.

Unfiltered results start with a fixed 100-part showcase, then continue in stable source catalog order. Filtered results are ordered by stable source catalog order.

Examples:

```text
https://api.step.parts/v1/parts?q=M3&tag=screw&page=2
https://api.step.parts/v1/parts?pageSize=100
https://api.step.parts/v1/parts?category=fastener&family=socket-head-cap-screw&standard=ISO%204762
https://api.step.parts/v1/parts?q=lengthMm%2012
```

## Response Fields

`/v1/parts` returns:

- `catalog`: part count, last modified timestamp, catalog checksum, and URLs for schema/OpenAPI.
- `items`: enriched part records with absolute `pageUrl`, `apiUrl`, `stepUrl`, `glbUrl`, and `pngUrl`.
- `page`, `pageSize`, `total`, `totalPages`, `hasNextPage`, `hasPreviousPage`.
- `facets`: available `tags`, `categories`, `families`, and `standards` with counts.
- `filters`: parsed active filters.

Each part record contains:

- `id`: stable snake_case identifier and asset filename base.
- `name`, `description`, `category`, `family`, `tags`, `aliases`.
- `standard`: optional `{ body, number, designation }`.
- `attributes`: family-specific scalar facts.
- `stepUrl`, `glbUrl`, `pngUrl`.
- `byteSize`, `sha256`.

## Asset URL Patterns

Use returned URLs when possible. Patterns are:

```text
https://www.step.parts/step/{id}.step
Use the absolute `glbUrl` and `pngUrl` returned by the API record. Preview assets are served from Vercel Blob.
https://www.step.parts/parts/{id}
```

The `/step/{id}.step` route serves local checked-out STEP bytes in local/dev mode and redirects to commit-pinned GitHub LFS media in production.

## Download And Verification

When downloading a STEP file:

1. Fetch a part record from `/v1/parts` or `/v1/parts/{id}`.
2. Download `stepUrl`.
3. Compare the file SHA-256 to the part record's `sha256` when it is not null.
4. Keep the original `.step` extension and preserve the source id in the filename unless the user asks otherwise.
