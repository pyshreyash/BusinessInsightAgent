# AI Business Insights Generation Agent

## Motivation
Leadership relies heavily on static BI dashboards with predefined metrics, which limits exploration and delays insight discovery. Decision-making becomes reactive and dependent on manual analysis.

This project implements an LLM-powered pipeline that turns a natural-language business question into:
1. Grounded SQL (must use metrics from the YAML semantic layer)
2. Deterministic SQL validation (before execution)
3. Executed query results (PostgreSQL)
4. Interpretable week-over-week insights (plain English)
5. Optional automated actions (console alert + optional webhook) when the insight indicates `drop`, `increase`, or `anomaly`

## Query API
`POST /api/query`

### Request
```json
{
  "question": "Why did revenue drop last week?"
}
```

### Response
```json
{
  "sql": "...",
  "result": [ { "...": "..." } ],
  "insight": "...",
  "assumptions": ["..."]
}
```

### Example call
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Why did revenue drop last week?"}'
```

### Example Request Flow

1. Client sends `POST /api/query` with `{ "question": "Why did revenue drop last week?" }`
2. LangGraph workflow runs nodes in order:
   - `planner` (builds metric + time comparison plan)
   - `retriever` (RAG context from FAISS)
   - `sql_generator` (uses semantic metric formula to build SQL)
   - `sql_validator` (deterministic: schema/columns/joins/metric-formula usage)
   - `executor` (runs SELECT against Postgres)
   - `analyzer` (week-over-week percent change -> insight + assumptions)
   - `action_trigger` (console alert + optional webhook when insight includes keywords)

3. Response includes:
   - `sql`
   - `result` (rows)
   - `insight`
   - `assumptions`

## How grounding works (semantic layer + RAG)
The Agent is designed to avoid “SQL hallucinations” by grounding and validation:
- Semantic layer is YAML-driven:
  - SQL generation is built from explicit metric definitions (formula/table/grain).
- RAG uses FAISS (local):
  - Retrieval documents are built from metric definitions, warehouse schema descriptions, and business rules from YAML.
- Deterministic SQL validation runs BEFORE execution:
  - Checks parseable SQL (via `sqlglot`)
  - Rejects `SELECT *`
  - Verifies tables and columns exist in the simulated schema
  - Enforces allowed join patterns (deterministic join checks)
  - Ensures the metric formula text from the semantic layer appears in the SQL

## Action layer
If the generated insight contains any of these keywords:
- `drop`
- `increase`
- `anomaly`

Then the Agent triggers:
- a console alert (`ALERT: ...`)
- an optional `WEBHOOK_URL` POST with `{ insight, keywords, result }`

## Key files
- App entrypoint: `app/main.py`
- API route: `app/api/routes/query.py`
- Agent workflow (LangGraph): `app/agents/workflow.py`
- Semantic layer:
  - config: `config/semantic_layer.yaml`
  - code: `app/semantic/loader.py`, `app/semantic/metrics.py`, `app/semantic/validator.py`
- RAG:
  - docs builder: `app/rag/doc_builder.py`
  - FAISS store: `app/rag/faiss_store.py`
  - retriever: `app/rag/retriever.py`
- SQL:
  - generator: `app/sql/generator.py`
  - validator: `app/sql/validation.py`
- DB:
  - connection + execution: `app/db/connection.py`
  - schema + join rules: `app/db/schema.py`
  - seed data: `app/db/seed.py`

## Limitations
- The `planner` is intentionally minimal: it currently supports a limited subset of questions (not full free-form analytics).
- The SQL generator currently builds a deterministic week-over-week time-series scaffold.
- The LLM refinement is best-effort and optional; deterministic validation remains the safety gate.

*Fun fact: The project is vibe-coded using Cursor :wink:*