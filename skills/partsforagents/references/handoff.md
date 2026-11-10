# Exact-file workflow

Use the live [tool schemas](https://partsforagents.com/tools.json) or
[OpenAPI contract](https://partsforagents.com/openapi.json). All HTTP paths below use
`https://partsforagents.com`. Required customer choices remain missing until supplied.

## Upload and specification

| Step | MCP tool | REST equivalent |
| --- | --- | --- |
| Upload authorized export | `upload_cad_request` | `POST /api/v1/requests` (multipart) |
| Verify stored identity | `get_cad_request` | `GET /api/v1/requests/{id}` |
| Inspect preliminary findings | `get_cad_preflight` | `GET /api/v1/requests/{id}/preflight` |
| Read specification versions | `get_manufacturing_specifications` | `GET /api/v1/requests/{id}/specification` |
| Pin selected manufacturing choices | `set_manufacturing_specification` | `PUT /api/v1/requests/{id}/specification` |
| Read exact-part rule-based advice | `analyze_manufacturability` | `GET /api/v1/requests/{id}/advice?spec_fingerprint=...` |

Upload requires the filename/bytes, email, material family, quantity, units, country/postal code,
`desired_speed`, `consent:true` and a saved idempotency key. MCP uses `file_base64`; REST uses a
multipart `file` and `consent=true`. Current size limits are 2 MiB decoded CAD for MCP or 10 MiB
for REST. Keep CAD bytes in the authorized transport, not chat. Required contact/location fields
also apply to DFM-only intake; a full street address is not needed for that review.

Compare returned `file_sha256` with the local SHA-256 and require `status:"received"` before
continuing. Save its request `id`. Current geometric preflight measures STL; accepting STEP,
3MF or OBJ does not establish that their geometry was parsed. Keep unmeasured facts unknown.

Read existing specifications before changing one. Set the selected `process`, `material_grade`,
`finish`, `color`, `manufacturing_options` and `required_arrival_at` (an agreed timestamp or
`null` for no deadline). MCP includes `request_id`; REST identifies it in the path. The response
contains `specification.spec_fingerprint` and the canonical specification: preserve both.

- `manufacturing_options:{"policy":"provider_standard"}` delegates settings only when chosen
  by the user. `policy:"specified"` requires `layer_height_mm`, `infill_percent` and `tolerances`;
  the first two may each be `"provider_standard"` when selected. Do not invent a fit tolerance.
- A manufacturing offer needs actual delivery details. Country/postal code inherit from intake;
  `destination` supplies recipient, street, city and region. Do not put the address in review notes.
- Multicolor needs the live 3MF object-mapping schema bound to the exact CAD hash. Do not infer
  object IDs or paint a multicolor meaning onto STL. This skill's simplest path is single-color FDM.

Call `analyze_manufacturability` with the saved request ID and exact `spec_fingerprint`.
Its observations are not the asynchronous specialist report. Optional budget estimates are not
required for review submission and must retain their assumptions and missing costs.

## Submit and track

Only for the user's actual submission intent, call `place_order` or `POST /api/v1/orders` with:

| Field | Value |
| --- | --- |
| `request_id`, `spec_fingerprint` | The exact returned identities, never invented |
| `order_type` | `dfm_review`, `quotation` or `manufacturing`, matching the user's intent |
| `acknowledge_nonbinding` | `true`, after explaining that submission is not a purchase |
| `review_notes` (optional) | The concrete question or requirements, without unnecessary personal data |
| Idempotency | A separate saved key: MCP `idempotency_key`, REST `Idempotency-Key` header |

Do not include the REST key in the JSON body. `max_total_minor`, if selected, is only a
USD-cent preference. No estimate or supplier quote is required; never fabricate their IDs.

Save `order.id`, `cad_sha256`, `spec_fingerprint`, `status` and replay indicator. Read `get_order`
(`GET /api/v1/orders/{id}`) for status and the report. For `manufacturing` or `quotation` only,
also read `get_order_fulfillment` (`GET /api/v1/orders/{id}/fulfillment`) for authoritative
offers, revision and fulfillment facts. DFM-only orders do not support the fulfillment route.
Check MCP `isError` and `structuredContent.ok` before consuming `structuredContent.data`.
A successful transport response is not proof of a successful business operation.

Initial submission returns `payment_required_on_submission:false` and `payment_link:null`.
`payment_link_status:"after_review_if_accepted"` is a future condition, not a URL or delivery
promise; DFM-only uses `"not_required"`. A queued review stays pending until a report exists.

## State and recovery

Save write bodies/keys and exact bytes privately before sending. Retry an uncertain upload or
order only with the identical body/key; if its ID was returned, read it first. If the original
bytes or intent cannot be recovered, stop for reconciliation. Do not generate a replacement key.
Identical specification PUTs reuse the normalized specification and need no idempotency header.

A backlog replay returns the same order even after cancellation. `409 active_order_exists`
provides an order ID to read; it is not permission to create another. On `401`, repair auth;
on `400/422`, correct fields; on `404/409`, reconcile ownership/state; on `413`, use a supported
size/path; on `429/503`, respect limits/backoff without replacing write identity. Do not switch
accounts to evade quotas. Poll pending specialist work no more often than every 30 minutes.

For manufacturing or quotation, backlog may still say `pending_review` after acceptance:
fulfillment revision, status and facts establish later progress. Cancelling backlog is not cancelling a supplier purchase or stopping a
printer. This skill does not operate either.
