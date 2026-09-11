# EDUNOVA AI — Research & Evidence Layer

## Principle
External career/company claims must carry **provenance**. EDUNOVA distinguishes:

| Label | Meaning |
|-------|---------|
| Verified fact | Linked to `EvidenceSource` with status `verified` |
| Derived analysis | Deterministic scoring from user profile + catalog |
| Model estimate | ML placement probability (synthetic educational dataset) |
| AI recommendation | LLM/local coach text — not a fact |
| User-provided | Self-reported skills/experience |

## Models
- `EvidenceSource` — title, URL, type, publisher, verification_status, last_verified_at, confidence
- `Company` / `CompanyRoleRequirement` — role-level requirements with optional evidence FK
- `LearningResource` — curated resources; unverified URLs must not be marked official
- `DataUpdateLog` / `ResearchSnapshot` — audit trail hooks

## Ethics
- Synthetic ML data ≠ real hiring outcomes
- No fabricated URLs or “currently requires” without dated evidence
- Compatibility estimates ≠ hiring guarantees
- Prefer official careers pages, O*NET, BLS, government education sources

## Admin
`/admin/companies` and `/admin/evidence` list research catalog (student cannot edit).
