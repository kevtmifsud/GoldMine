# Portfolio Intelligence Platform — Architecture Overview

## Purpose

This document provides a high-level map of all workflows and data specifications for the Portfolio Intelligence Platform. It is the entry point for any implementation work. Read this first, then follow the linked documents in build order.

---

## Platform Summary

The platform ingests financial documents across thousands of tickers, processes them into a queryable knowledge base, and exposes that knowledge to a team of portfolio managers and analysts through a chat interface embedded in the Goldmine application.

**Tech stack:**
- Frontend: React + TypeScript + Vite (Goldmine — existing application)
- Backend API: Python + FastAPI + Pydantic v2 + Uvicorn
- Database: Supabase (PostgreSQL + pgvector) — single database for all data
- Document storage: Google Drive
- LLM: Anthropic Claude API (Haiku for classification/compression, Sonnet for generation)
- Embeddings: OpenAI text-embedding-3-large at 1536 dimensions

---

## Two Modes

**Mode 1 — Document Processing Pipeline**
Offline, automated, runs daily. Ingests raw text documents from Google Drive, chunks them semantically, generates embeddings, and stores everything in Supabase. Does the expensive work once so Mode 2 is fast and cheap.

**Mode 2 — Interactive User Sessions**
Online, user-facing. Analysts send messages through Goldmine, the FastAPI backend classifies the query, retrieves relevant context, and streams a sourced answer back. All conversations, insights, and validated answers are persisted in Supabase.

---

## Data Sources

### Text Documents (Google Drive)
Unstructured qualitative documents stored as .txt files. Currently earnings transcripts only.

```
/transcripts/{ticker}/{filename}.txt
```

All documents at this path level are classified as `earnings_transcript`. When additional document types are added, a document type subfolder layer will be introduced.

### Structured Financial Data (Google Drive CSVs → Supabase)
Clean financial figures across all tickers in CSV format, loaded into Supabase structured tables for SQL querying in Mode 2.

```
/structured_data/
  quarterly_income_statement.csv
  annual_income_statement.csv
  quarterly_balance_sheet.csv
  annual_balance_sheet.csv
  quarterly_cash_flows.csv
  annual_cash_flows.csv
```

---

## Mode 1 Workflows — Build in This Order

### [WF-00: Infrastructure & Environment Setup](./WF-00_Infrastructure_Setup.md)
One-time setup. Google Drive organization, Supabase project creation, pgvector activation, schema initialization, API keys. Start here before anything else.

### [WF-01: Document Ingestion & Change Detection](./WF-01_Document_Ingestion.md)
Daily scan of Google Drive `/transcripts/` folder. Content hashing, change detection, job queue population.

### [WF-02: Document Classification](./WF-02_Document_Classification.md)
Classifies each document by type. Current structure: all documents under `/transcripts/{ticker}/` classify as `earnings_transcript` via path rule. Built to support additional document types when subfolder structure is introduced.

### [WF-03: Semantic Chunking & Section Metadata](./WF-03_Chunking_and_Metadata.md)
Splits documents into semantically meaningful chunks. Section-level metadata tagging. Core determinant of retrieval quality in Mode 2.

### [WF-04: Embedding Generation & Vector Storage](./WF-04_Embedding_and_Storage.md)
Generates 1536-dimension embeddings per chunk using OpenAI. Stores in Supabase chunks table with full metadata.

### [WF-05: Pipeline Orchestration & Job Management](./WF-05_Pipeline_Orchestration.md)
End-to-end batch job management. Parallelism, job queue, error handling, retries, cost tracking, daily scheduling via Mac cron.

---

## Mode 2 Workflows — Build in This Order

### [WF-06: Query Classifier](./WF-06_Query_Classifier.md)
First step on every user message. Claude Haiku classifies query type, extracts tickers, periods, and topic. Returns structured Pydantic model.

### [WF-07: Ticker Resolution](./WF-07_Ticker_Resolution.md)
Expands list references and group descriptors into concrete ticker arrays. Pure SQL — no API calls.

### [WF-08: Retrieval Orchestration](./WF-08_Retrieval_Orchestration.md)
Routes to correct retrieval strategy per query type. Screening cache check. Q&A library lookup. Parallel cross-ticker retrieval. Two-stage Haiku pre-filter for screening.

### [WF-09: Response Generation](./WF-09_Response_Generation.md)
Assembles context within token budget. Enforces sourcing requirements. Calls Claude Sonnet with streaming. Emits metadata event after stream completes.

### [WF-10: Session & Conversation Management](./WF-10_Session_Management.md)
Session history assembly, rolling summary compression, conversation lifecycle, auto-titling, history search embedding.

### [WF-11: Q&A Library Management](./WF-11_QA_Library.md)
Library entry lifecycle, validation workflow, retrieval with similarity threshold and validation weighting, staleness flagging, deduplication.

### [WF-12: Sharing & Permissions](./WF-12_Sharing_Permissions.md)
Privacy model, conversation and insight sharing, Supabase row-level security policies, history page data access.

---

## Data & Schema Documents

### [DS-01: Structured Financial Data](./DS-01_Structured_Financial_Data.md)
CSV source description, Supabase table schemas for income statement / balance sheet / cash flows, tickers master table, fiscal period alignment requirements.

### [DS-02: Mode 2 Database Schema](./DS-02_Mode2_Schema.md)
All Supabase tables for Mode 2: users, conversations, sessions, messages, feedback, Q&A library, insights, sharing, screening cache, cost events, pricing, and model config. Includes seed data for model_config and api_pricing.

### [DS-03: API Endpoint Specifications](./DS-03_API_Endpoints.md)
Complete FastAPI endpoint contract between Goldmine and the Mode 2 backend. Request/response schemas, SSE streaming format, error format.

### [DS-04: Cost Management & Model Versioning](./DS-04_Cost_Management.md)
Cost tracking architecture, model selection at runtime, switching models without code changes, monitoring queries, soft budget alerts.

---

## Key Design Principles

**Private by default.** All analyst content is private unless explicitly shared. The Q&A library is the only team-wide content layer.

**Every claim must be sourced.** Claude is instructed on every call to cite ticker, document type, period, and section for every factual statement. No unsourced claims.

**Model config drives model selection.** No model names are hardcoded. Switching models requires one row update in `model_config` — no code changes, no redeployment.

**Cost is logged on every API call.** Every LLM and embedding call emits a cost event with model, tokens, cost, user, and query type. The platform always knows what things cost and who caused the cost.

**Two data sources, two query paths.** Numerical questions hit Supabase structured tables directly — no LLM retrieval needed. Qualitative questions hit the vector DB. Hybrid questions use both.

**The platform compounds with usage.** Every validated answer enters the Q&A library. Every session is searchable. The more the team uses it, the more valuable it becomes.

**Never discard.** All documents, chunks, embeddings, messages, and cost events are retained permanently. Soft deletes only.

---

## Full Document Index

| File | Type | Description |
|---|---|---|
| `00_MASTER_ARCHITECTURE.md` | Index | This file |
| `WF-00_Infrastructure_Setup.md` | Workflow | One-time infrastructure setup |
| `WF-01_Document_Ingestion.md` | Workflow | Document ingestion and change detection |
| `WF-02_Document_Classification.md` | Workflow | Document type classification |
| `WF-03_Chunking_and_Metadata.md` | Workflow | Semantic chunking and metadata |
| `WF-04_Embedding_and_Storage.md` | Workflow | Embedding generation and vector storage |
| `WF-05_Pipeline_Orchestration.md` | Workflow | Pipeline orchestration and job management |
| `WF-06_Query_Classifier.md` | Workflow | User query classification |
| `WF-07_Ticker_Resolution.md` | Workflow | Ticker list and group resolution |
| `WF-08_Retrieval_Orchestration.md` | Workflow | Retrieval routing and context assembly |
| `WF-09_Response_Generation.md` | Workflow | Response generation and streaming |
| `WF-10_Session_Management.md` | Workflow | Session history and conversation management |
| `WF-11_QA_Library.md` | Workflow | Q&A library lifecycle and retrieval |
| `WF-12_Sharing_Permissions.md` | Workflow | Sharing model and row-level security |
| `DS-01_Structured_Financial_Data.md` | Data | CSV source and Supabase financial tables |
| `DS-02_Mode2_Schema.md` | Data | All Mode 2 Supabase table definitions |
| `DS-03_API_Endpoints.md` | Data | FastAPI endpoint specifications |
| `DS-04_Cost_Management.md` | Data | Cost tracking and model versioning |
