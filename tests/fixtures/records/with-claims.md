---
date: 2026-05-14
type: decision
status: active
record_complete: true
context_path: [main-platform, auth-service]
people: []
tags: [infra]
decision: "Drop Redis for session storage"
claims:
  - id: c1
    content: "Session data is stored in PostgreSQL"
    status: active
  - id: c2
    content: "Redis is not used for sessions"
    status: tentative
    supersedes:
      file: 2026-02-10-redis-session-store.md
      claim: c1
---

## Rationale
PostgreSQL only.
