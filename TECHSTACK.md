GoldMine Tech Stack
===================

Frontend
--------
- Framework: React 18.3 + TypeScript
- Routing: React Router 7
- Build: Vite 6
- Data Grid: AG Grid (Community)
- Charts: ECharts
- HTTP Client: Axios
- Markdown: react-markdown + remark-gfm
- Testing: Vitest + Testing Library
- State Management: React hooks only (no Redux/Zustand)
- Styling: Custom CSS with CSS variables, BEM naming convention
- UI Library: None — all custom components
- Excel Export: XLSX

Backend
-------
- Framework: FastAPI 0.115 + Uvicorn (ASGI)
- Language: Python 3.12
- Database: Supabase (PostgreSQL) via psycopg2 (sync) + asyncpg (async)
- Vector Search: pgvector (cosine similarity)
- Auth: JWT (python-jose, HS256, 8-hour token expiry)
- Financial Data: defeatbeta-api (sources from Hugging Face / Yahoo Finance)
- Data Processing: pandas
- Logging: structlog
- PDF Parsing: pypdf

Chatbot (Mode 2) Pipeline
--------------------------
The chatbot is a multi-stage streaming pipeline where each step uses a purpose-fit model:

- WF-06 Query Classifier: Extracts query type, tickers, fiscal periods, and topic from user input. Uses Claude Haiku for fast, low-cost classification.
- WF-07 Ticker Resolver: Expands ticker lists and handles aliases. Pure logic — no LLM call.
- WF-08 Retrieval: Hybrid retrieval combining vector search on document chunks (pgvector), structured SQL queries on financial_metrics, and Q&A library lookup for validated answers. Uses OpenAI text-embedding-3-large (1536 dimensions) for chunk embeddings.
- WF-09 Response Generator: Streams the final answer with enforced inline citations. Uses Claude Sonnet (claude-sonnet-4-20250514) with a custom system prompt that requires sourcing and format rules per query type.
- WF-10 Session Manager: Compresses conversation history every 10 turns and auto-generates conversation titles after the first exchange. Runs as a fire-and-forget async task using Claude.

Key architecture details:
- Streaming via SSE: Tokens, pipeline steps, errors, and metadata are all delivered as server-sent events for real-time UI updates.
- Runtime model config: Model assignments per component are stored in a model_config database table, not hardcoded, allowing hot-swapping without redeployment.
- Cost tracking: Every LLM API call is logged to api_cost_events with input/output token counts and USD cost.
- Citation system: Responses include inline citations in the format [TICKER | DocType | Period | Section] which the frontend parses into clickable links that navigate to transcripts, SEC filings, and financial data viewers.
- Dual embedding providers: Voyage AI (voyage-3, 1024 dimensions) for conversation history search; OpenAI (text-embedding-3-large, 1536 dimensions) for document chunk retrieval.

Document Processing Pipeline (Mode 1)
--------------------------------------
A 5-stage ingestion pipeline that processes raw documents into searchable, embedded chunks:

- WF-01 Ingestion: Scans Supabase for source documents, registers them in a processing registry with MD5 change detection.
- WF-02 Classification: Detects document type (earnings transcript, 10-K, etc.) using path-based rules.
- WF-03 Chunking: Semantic chunking with speaker attribution. Target 600 tokens per chunk (range: 200–1000).
- WF-04 Embedding: Generates embeddings via OpenAI text-embedding-3-large. Batch size of 50 with retry logic.
- WF-05 Orchestration: Coordinates stages 1–4, manages the processing queue, handles stuck jobs (2-hour timeout), and logs costs.

Data Sources in Supabase
-------------------------
- stocks: 503 tickers (S&P 500 universe) with company profiles
- financial_metrics: Income statement, balance sheet, and cash flow data (165 metrics per ticker)
- transcripts_list: Earnings call transcripts (2015–present, ~20K+ rows across 490+ tickers)
- sec_filings: SEC filings (10-K, 10-Q, 8-K, DEF 14A) with EDGAR primary document links
- stock_history: Historical price data
- chunks: Semantically chunked document segments with pgvector embeddings
- people: Executive officers with compensation data
- earnings_calendar: Upcoming and historical earnings dates
