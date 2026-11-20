# API 1.1: contract documentation (WP3.1, specification only)

**Status:** specified and tested as a contract; **not served**. The Core still advertises only `1.0` (`SUPPORTED_VERSIONS = ("1.0",)`), a request for `1.1` is refused with `unsupported_version`, and none of the new endpoints exists on the running Core. Approved scope: PR #8 comments 7051135695, 7051242604, 7051300100, 7051339291; proposal `STAGE3_WP3_1_PROPOSAL.md` (v4).

## Files
| File | Role |
|---|---|
| `contracts/atlas-contracts.schema.json`, `contracts/openapi.yaml` | **API 1.0, frozen.** Byte-identical to the accepted baseline; their SHA-256 values are pinned in `tests/test_contracts_frozen.py`. |
| `contracts/atlas-contracts.1.1.delta.schema.json` | The 1.1 **source**: `x-overrides` (1.0 definitions it replaces), `x-additions` (new definitions) and their `$defs`. |
| `contracts/atlas-contracts.1.1.schema.json` | The 1.1 document: **generated** by `contracts.build_1_1(1.0 document, delta)` and committed so that OpenAPI references resolve; a test requires it to equal a fresh merge. Never edit it by hand. It keeps the 1.0 root metadata (including `$id`) as required, so it is distinguished by its file name. |
| `contracts/openapi-1.1.yaml` | The 1.1 OpenAPI document. |

## Version negotiation
- Request header `X-Atlas-Api-Version`. **Absent means 1.0.** `1.0` selects 1.0. `1.1` selects 1.1 only when `GET /v1/version` advertises it. Any other value (another version, empty, repeated, non-text) is refused with `unsupported_version`; nothing is guessed (`contracts.negotiate`, tested).
- **Echo.** In the 1.1 OpenAPI file only, every operation except `/v1/version` takes the optional `ApiVersion` parameter and every response carries `X-Atlas-Api-Version` with the version **applied**. A 1.1 client rejects a response whose echo is absent or different from the version it requested.
- **`/v1/version` is the exception:** it is the unversioned discovery call, never negotiated, never refused for its version header, has no echo, and answers `{api_version, supported}` as in 1.0.
- **Compatibility invariant (OpenAPI):** every 1.0 path and `operationId` is preserved. The only permitted differences on an existing operation are the `ApiVersion` parameter, the response echo header, the versioned error response, and schema references pointing at the 1.1 document. Three new paths are added and marked `x-atlas-status: specification-only; not served`.
- **Validation:** `contracts.validate(name, value)` means 1.0 and never applies a 1.1 requirement; `validate(name, value, version="1.1")` uses the 1.1 document.

## The merge (`contracts.build_1_1`)
A pure, deterministic operation. It deep-copies the 1.0 document, keeps its root metadata, replaces **only** the definitions named in `x-overrides`, adds the ones in `x-additions`, sorts the definition names and checks that every `$ref` resolves inside the document and every definition is a valid Draft 2020-12 schema. It raises on: a duplicate name; an override that 1.0 does not have; an addition that 1.0 already has; a name in both lists; a definition in neither list or a listed name without a definition; a dangling or foreign reference; an invalid schema. It never changes its input. A replaced `Locator` therefore applies wherever 1.0 references it (for example `EvidenceRef`).

## Contract diff (1.1 relative to 1.0)
| Type | Change |
|---|---|
| `Coverage` | new: state, searched, total or null, pending (closed categories), failed (closed reasons), as_of |
| `ModelDescriptor` | new: content-free `{model_id, role, runtime}` |
| `IndexStatus`, `ConsentRequest`, `ConsentState` | new (shapes only) |
| `AnswerEnvelope` | replaced: 1.0 fields plus `coverage` (**required**) and `model` (optional), with the rules below |
| `Locator` | replaced: the four 1.0 kinds unchanged, three strict new kinds |
| `Limitation`, `ErrorCode`, `SafeEvent` | replaced: only values and fields added |

### Coverage and limitations
`indexing_incomplete` is present **if and only if** `coverage.state` is `indexing`. `complete` requires empty `pending` and `failed`; `partial` requires something pending or failed and never carries `indexing_incomplete`.
| In `coverage` | Required in `limitations` | Converse (the limitation needs its cause) |
|---|---|---|
| `state = indexing` | `indexing_incomplete` | yes (the iff above) |
| `pending` has `attachments` | `attachment_pending` | yes |
| `pending` has `unsupported_source` | `source_unsupported` | yes |
| `pending` has `os_access` | `os_access_missing` | yes |
| `state = partial` and `pending` has `not_yet_indexed` | `partial_work` | no: Stage 2 uses `partial_work` for other partial work |
| `failed` is non-empty | `partial_work` | no (same reason) |
`searched = total` for `complete` cannot be expressed in a schema; it is an invariant for the coverage implementation package (pending test in `STAGE3_TRACEABILITY.md`).

### Locator kinds
| Kind | Required | Optional | Refused |
|---|---|---|---|
| `page`, `block`, `message_part`, `span_only` (1.0) | as in 1.0 | `quoted` on `message_part` only | any 1.1-only field other than that |
| `header_field` | `header` (`from`, `to`, `date`, `subject`, `message_id`), `authenticity` = `claimed` | none | everything else |
| `attachment_part` | `attachment_id` | `page` or `block` | everything else |
| `sheet_cell` | `sheet`, `cell` (A1 notation) | none | everything else |
`sheet` is the **index** of the sheet, never its name, because names are content of the owner and a locator must stay content-free. A header value is what the message says about itself (claimed, not authenticated).

## Signing (specification; the Core does not enforce it in WP3.1)
The applied version is part of the signed message for 1.1. LF is 0x0A; all fields are UTF-8; there is no trailing newline; a verifier refuses any field containing CR or LF.
- **1.0, unchanged:** `METHOD_UPPERCASE LF target LF timestamp LF nonce LF lowercase_hex(SHA-256(body))` (five fields).
- **1.1:** `1.1 LF METHOD_UPPERCASE LF target LF timestamp LF nonce LF lowercase_hex(SHA-256(body))` (six fields; the literal text `1.1` first).
The verifier builds the message from the version it **applies**, so stripping or changing the header on a request signed for 1.1, or adding `1.1` to one signed for 1.0, gives a different message and the signature fails. A six-field message can never equal a five-field one because no field contains LF. `/v1/version` keeps the 1.0 signing and has no version field. Enforcement belongs to the separately reviewed identity package.

**Known-answer vectors** (inputs: method `post`, target `/v1/tasks?after=0`, timestamp `1700000000`, nonce `abcdefgh12345678`, body `{"a":1}`; SHA-256 of the body `015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862`):
- 1.0 message (hex): `504f53540a2f76312f7461736b733f61667465723d300a313730303030303030300a616263646566676831323334353637380a30313561626437663563633537613264643934623735393066303461643830383432373339303565653333656335636562656165363232373661393766383632`
- 1.1 message (hex): `312e310a504f53540a2f76312f7461736b733f61667465723d300a313730303030303030300a616263646566676831323334353637380a30313561626437663563633537613264643934623735393066303461643830383432373339303565653333656335636562656165363232373661393766383632`
`tests/test_contracts_v11.py` checks both against a test-local reference function, and that the 1.0 message equals `identity.canonical`.

## What WP3.1 does not do
No consent, grant or revoke behaviour, owner-interactive enforcement, replay state, OS-access discovery, indexing, parsing, egress, model adapter, Mail processing, owner data, Mac-only work or new dependency; no change to the 1.0 files or to the runtime.
