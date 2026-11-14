# Documentation and code relationship API

The relationship API adds persistent links to generated documentation without changing the existing generation, sync, or template request contracts.

## Identifiers and lifecycle

- A generated document receives an opaque UUID (`documentId`) in addition to the existing AI `jobId`.
- Code entity IDs are UUIDs persisted per repository. Their stable key is derived from repository, source path, entity type, and qualified name; line numbers are metadata and can change without changing identity.
- An entity that disappears from an analyzed file is marked inactive. Existing links remain stored but inactive entities are omitted from results. If the same entity returns, its ID and links become available again.
- Repository deletion cascades to its documents, entities, and links. Existing documents and source snapshots are not rewritten by this feature.

## Endpoints

All endpoints require the authenticated `X-User-Id` forwarded by the backend-for-frontend.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/repositories/{repositoryId}/code-entities` | List active analyzed entities and GitHub source links. |
| `GET` | `/api/repositories/{repositoryId}/documentation` | List generated documents in the repository. |
| `GET` | `/api/documentation/{documentId}` | Read a generated document snapshot. |
| `GET` | `/api/documentation/{documentId}/code-entities` | Read code linked from a document. |
| `PUT` | `/api/documentation/{documentId}/code-entities` | Replace links with `{ "codeEntityIds": ["..."] }`; an empty list removes all links. |
| `GET` | `/api/documentation/code-entities/{entityId}/documents` | Read documents linked to a code entity. |

Document and entity ownership is checked against the connected repository. Link updates reject missing, inactive, or cross-repository entity IDs and deduplicate repeated IDs.



