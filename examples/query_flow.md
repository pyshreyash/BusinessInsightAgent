## Example Request Flow

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

