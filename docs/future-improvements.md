# Future Improvements

Ideas and proposals that are intentionally out of current implementation scope but worth tracking.

## Person alias management

### Problem

The graph currently stores people by a single canonical `Person.name`. If the same individual appears under different forms (for example, `Rudy` vs `Rodolfo Suarez`), Yanka can create separate `Person` nodes and split decision history across identities.

### Why this matters

- Retrieval by person becomes incomplete or inconsistent.
- Graph relationships (`involves`) fragment across duplicate identities.
- Supersession/conflict context that depends on decision-makers loses signal.

### Proposed direction

1. Add alias-aware person resolution during ingest.
2. Keep one canonical person node, store known alternatives in `Person.aliases`.
3. Resolve incoming names through:
   - exact canonical match,
   - exact alias match,
   - normalization pass (case, whitespace, punctuation),
   - optional LLM-assisted disambiguation only when ambiguous.
4. Provide a deterministic tie-break rule (prefer existing canonical when confidence is high).

### Suggested implementation slices

1. **Alias registry primitives**
   - Read/write helpers for person aliases in graph.
   - Matching utilities with normalization.
2. **Ingest integration**
   - Update person linking flow to use alias resolution before creating nodes.
3. **Backfill command**
   - Merge duplicate person nodes and rewrite affected `involves` edges.
4. **Operator controls**
   - Add a CLI/admin path to review and manually approve uncertain merges.

### Safety and UX notes

- Never auto-merge low-confidence collisions without user confirmation.
- Preserve an audit trail for merges (who/when/why).
- Keep retrieval transparent by surfacing canonical name + matched alias when relevant.

