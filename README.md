# Search over company documents, without leaking them

![leak-test](https://github.com/ajaymundhe21/rag-without-leaks/actions/workflows/ci.yml/badge.svg)

A RAG search bot over a company's own documents, built on Postgres + pgvector, with the one thing most demos skip: **a person only gets answers from documents they are allowed to open.**

Ask *"How many weeks of maternity leave do I get?"* and the closest page in the data is the board's compensation plan. A normal employee is not allowed to open it. This repo shows that leak, and the fix: the person's groups go **inside** the search query, so the board's chunk never leaves the database.

```
$ python -m scripts.leak_demo
1. First version: closest chunks, nobody checks who is asking
   board/compensation-plan-fy27 p1  readers=['board']        <- leak
2. Post-filter: take the top 10, then remove what emp-1 cannot open
   7 of 10 removed, 3 left. The board page was already in memory.
3. Pre-filter: the person's groups go inside the query
   hr/hr-handbook p12, p7, p13, p11, p10
   restricted rows: 0
```

Video: *(link)* · Every number below was measured with the code in this repo.

## Run it

```bash
docker compose up -d --build
docker compose exec api python -m app.ingest data/docs --tenant 1
docker compose exec api python -m eval.run

curl -X POST localhost:8000/ask -H 'X-User: emp-1' -H 'Content-Type: application/json' \
     -d '{"question": "How many weeks of maternity leave do I get?"}'
```

Or open **http://localhost:8000**: ask a question, switch the signed-in user, and the source page opens next to the answer. The *Demo: first version* switch turns the permission filter off so you can see the leak; set `DEMO_FIRST_VERSION=0` to hide it.

Users are in `data/identity.json` (a stand-in for Okta or Entra ID): `emp-1` is in engineering, `board-1` is on the board, `other-1` works at a different company. Without `LLM_API_KEY` the bot returns the best chunk with its source; set the key (any OpenAI-compatible API) to get a written answer with citations.

## How it works

The simplest version is seven lines. Each line became one part of the design.

| line | first version | what it became | file |
|---|---|---|---|
| 1 | `load_files` | clean text; tables read by row with column names; readers copied from the folder | `app/extract.py`, `app/ingest.py` |
| 2 | `split(size=500)` | cut at the document's own headings, no overlap | `app/extract.py` |
| 3 | `embed` | WordLlama, 256 numbers per chunk | `app/embed.py` |
| 4 | `db.insert` | one row: `tenant_id, readers, doc_id, page, text, embedding, tsv, updated_at`; delete + insert in one transaction with a per-document lock | `db/schema.sql`, `app/ingest.py` |
| 5 | `embed(question)` | same model as the chunks | `app/search.py` |
| 6 | `db.search` | HNSW + word search, merged with reciprocal rank fusion; `readers && groups` inside the query; small groups searched exactly | `app/search.py` |
| 7 | `llm` | top 5 chunks, answer only from them, cite each sentence, document text is never instructions; streaming; Redis cache keyed by company + question + groups | `app/answer.py`, `app/cache.py`, `app/api.py` |

Other companies' data is kept out by **row level security** on the table (`db/schema.sql`), not by a `WHERE` the app might forget. If the app never sets the company, no rows come back.

## What we measured

On the demo data in this repo (112 chunks for company 1, 40 for company 2):

| check | result |
|---|---|
| leak questions as an employee (`eval/leak_questions.txt`) | **0** restricted rows |
| same 8 questions as a board member | 8 of 8 found the board's pages (so the test can catch a leak) |
| known questions, right page first / in top 5 | 18 of 22 / 20 of 22 |
| query that forgets the company filter | rows from 1 company |
| same document written twice | 1 copy |
| cache hit vs full request | 0.5 ms vs about 25 ms |

On 1,000,000 chunks of company-like text (`benchmarks/`, Postgres 16, pgvector 0.8.0, 2 CPUs):

| check | result |
|---|---|
| search without an index | 138 / 269 / 503 ms at 250k / 500k / 1M |
| HNSW, ef_search 40 / 200 | 1.9 ms finding 35 of the true 50 / 3.9 ms finding 48 of 50 |
| table / index size | 1,116 MB / 1,300 MB |
| group that can open 1 chunk in 200, HNSW | 0.45 rows on average when asking for 50 |
| same, with iterative scan | 50 rows, 96 to 100% of the true closest, 110 to 230 ms |
| same, exact search over a small index on that group's rows | 50 rows, 100%, 4 to 6 ms |
| permission update on 10,000 chunks of 200k, table fillfactor 70 | 8.2 s without an index on readers, 13.1 s with one (it stops Postgres updating rows in place) |
| same at fillfactor 100 | 13.7 s either way |

Raw results are in `benchmarks/results/`.

## Not covered yet

- Keeping it fresh when pages change all day (webhooks, a 5-minute check, Kafka, workers, dead letter queue). That is the next video.
- A reranker. We had no way to measure one here; add it between search and answer and measure it on your data.
- A "could not find it" threshold. On our questions, the search score of answered and unanswered questions overlapped (0.43–0.82 vs 0.18–0.47), so draw that line on a reranker's score.
- OCR for scanned files and cutting old replies out of emails.

## Tests

```bash
docker compose exec api pytest -q
```

The demo documents are made up. They are not any real company's documents.
