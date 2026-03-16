# WF-00: Infrastructure & Environment Setup

## Purpose

This document covers all infrastructure that must be in place before any pipeline workflow (WF-01 through WF-05) can run. It is the starting point for implementation. Nothing else should be built until this is complete and verified.

This setup uses entirely free, managed services requiring no local installation, no command line infrastructure setup, and no cloud provider account. All services are accessible via web UI.

---

## Infrastructure Overview

| Component | What it is | Service |
|---|---|---|
| Relational database | Processing registry and pipeline run logs | Supabase (free tier) |
| Vector database | Chunk embeddings and metadata for semantic retrieval | Supabase pgvector (built into same instance) |
| Document storage | Raw text files organized by ticker | Google Drive |
| Secrets management | API keys and connection strings | .env file in pipeline runtime |
| Scheduler | Triggers daily pipeline run | Configured in pipeline code — no separate service needed initially |

---

## Step 1: Google Drive — Document Storage

Google Drive is used to store all raw text files. It is free up to 15GB, accessible via API, and requires no setup beyond a Google account you likely already have.

**Folder structure to create in Google Drive:**
```
/portfolio-intel/
  /documents/
    /AAPL/
      /earnings_transcript/
        Q4_2024_earnings_transcript.txt
      /10K/
        FY2024_10K.txt
    /MSFT/
      ...
```

This mirrors the structure defined in WF-01. The folder hierarchy encodes ticker and document type, which the pipeline reads to extract metadata without parsing file contents.

**Moving your existing local files:**
Since you currently have text files stored locally on your Mac, the migration path is straightforward — recreate the folder structure above in Google Drive and upload your existing files. Google Drive desktop app (downloadable at drive.google.com) makes this a simple drag-and-drop from your local folders.

**Google Drive API access:**

The pipeline needs programmatic access to read files from Google Drive. To enable this:

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with your Google account
2. Create a new project — name it `portfolio-intel`
3. In the search bar, search for **Google Drive API** and enable it
4. Go to **APIs & Services → Credentials → Create Credentials → Service Account**
5. Name the service account `pipeline-worker`, click through the remaining steps
6. Once created, click the service account → **Keys** tab → **Add Key → JSON** — this downloads a key file to your Mac
7. In Google Drive, right-click the `/portfolio-intel/` folder → **Share** → paste the service account email (looks like `pipeline-worker@portfolio-intel.iam.gserviceaccount.com`) → set to **Viewer**

Store the path to the downloaded JSON key file as an environment variable in your pipeline (see Step 4).

**Storage note:** 15GB of free storage is sufficient for a large corpus of text files. Plain text is very compact — 15GB can hold hundreds of thousands of documents. If you eventually exceed this, Google One (100GB for $2.99/month) is the simplest upgrade path.

---

## Step 2: Supabase — Relational Database + Vector Database

Supabase provides a fully managed PostgreSQL database with the pgvector extension pre-installed. It has a web-based SQL editor and table viewer so no command line tools are needed. The free tier is sufficient to get started.

**Create a Supabase project:**

1. Go to [supabase.com](https://supabase.com) and sign up for a free account
2. Click **New Project**
3. Name it `portfolio-intel`
4. Set a strong database password and save it somewhere secure
5. Select the region closest to you
6. Wait approximately 2 minutes for the project to provision

**Find your connection details:**

Once the project is created, go to **Settings → Database** and note:
- **Host**: `db.xxxxxxxxxxxx.supabase.co`
- **Database**: `postgres`
- **Port**: `5432`
- **User**: `postgres`
- **Password**: the password you set above

Your full connection string:
```
postgresql://postgres:{password}@db.{ref}.supabase.co:5432/postgres
```

**Enable pgvector:**

In the Supabase dashboard, go to **SQL Editor** and run:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

pgvector is pre-installed on Supabase — this command simply activates it for your project.

---

## Step 3: Database Schema Initialization

In the Supabase **SQL Editor**, paste and run all of the following. You can run it all at once.

### Processing Registry
```sql
CREATE TABLE processing_registry (
    document_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker                VARCHAR(20) NOT NULL,
    document_type         VARCHAR(50),
    file_path             TEXT NOT NULL UNIQUE,
    file_hash             VARCHAR(64) NOT NULL,
    first_processed_at    TIMESTAMP,
    last_processed_at     TIMESTAMP,
    processing_status     VARCHAR(20) DEFAULT 'pending'
                          CHECK (processing_status IN
                          ('pending','processing','complete','failed','archived')),
    worker_id             VARCHAR(100),
    processing_started_at TIMESTAMP,
    chunk_count           INTEGER,
    classification_method VARCHAR(20),
    error_message         TEXT,
    created_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_registry_status ON processing_registry (processing_status);
CREATE INDEX idx_registry_ticker ON processing_registry (ticker);
CREATE INDEX idx_registry_hash   ON processing_registry (file_hash);
```

### Chunks + Embeddings
```sql
CREATE TABLE chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES processing_registry(document_id),
    ticker          VARCHAR(20) NOT NULL,
    document_type   VARCHAR(50),
    section_name    TEXT,
    section_type    VARCHAR(50),
    fiscal_period   VARCHAR(20),
    filing_date     DATE,
    chunk_sequence  INTEGER,
    page_reference  INTEGER,
    word_count      INTEGER,
    chunk_text      TEXT NOT NULL,
    embedding       vector(3072),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_ticker        ON chunks (ticker);
CREATE INDEX idx_chunks_document_id   ON chunks (document_id);
CREATE INDEX idx_chunks_document_type ON chunks (document_type);
CREATE INDEX idx_chunks_section_type  ON chunks (section_type);
CREATE INDEX idx_chunks_filing_date   ON chunks (filing_date);
CREATE INDEX idx_chunks_active        ON chunks (is_active);
CREATE INDEX idx_chunks_ticker_type   ON chunks (ticker, document_type, filing_date);

-- IMPORTANT: Do not create the vector search index yet.
-- Only run this after the initial corpus of embeddings is fully loaded.
-- Creating it on an empty table and then loading data is much slower.
--
-- CREATE INDEX idx_chunks_embedding
--     ON chunks USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);
```

### Pipeline Run Logs
```sql
CREATE TABLE pipeline_runs (
    run_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_started_at       TIMESTAMP DEFAULT NOW(),
    run_completed_at     TIMESTAMP,
    run_type             VARCHAR(20) DEFAULT 'incremental'
                         CHECK (run_type IN ('incremental','full')),
    documents_scanned    INTEGER,
    documents_queued     INTEGER,
    documents_succeeded  INTEGER,
    documents_failed     INTEGER,
    chunks_generated     INTEGER,
    estimated_cost_usd   NUMERIC(10,4),
    run_duration_seconds INTEGER,
    status               VARCHAR(20) DEFAULT 'running'
                         CHECK (status IN ('running','complete','failed')),
    notes                TEXT
);
```

Verify all three tables were created by checking the **Table Editor** tab in the Supabase dashboard — you should see `processing_registry`, `chunks`, and `pipeline_runs` listed.

---

## Step 4: API Keys & Environment Variables

The pipeline requires the following credentials at runtime. Store these in a `.env` file in your project root. This file should never be committed to version control — add `.env` to your `.gitignore`.

```bash
# Supabase / PostgreSQL
DATABASE_URL=postgresql://postgres:{password}@db.{ref}.supabase.co:5432/postgres

# Google Drive
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/service-account-key.json
GOOGLE_DRIVE_ROOT_FOLDER_ID={folder id of /portfolio-intel/ in Google Drive}

# Embedding model (OpenAI)
OPENAI_API_KEY=sk-...

# Claude API (Anthropic) — used only for document classification fallback
ANTHROPIC_API_KEY=sk-ant-...

# Pipeline configuration
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSIONS=3072
WORKER_CONCURRENCY=10
```

**Finding your Google Drive folder ID:** Open the `/portfolio-intel/` folder in Google Drive in your browser. The folder ID is the string at the end of the URL:
```
https://drive.google.com/drive/folders/{THIS_IS_YOUR_FOLDER_ID}
```

---

## Step 5: Supabase Free Tier Limits

| Limit | Free tier | Notes |
|---|---|---|
| Database storage | 500MB | Sufficient for development and small corpus |
| Rows | Unlimited | No row limit |
| Simultaneous connections | 60 | More than enough for this pipeline |
| Projects | 2 active | One is sufficient |

**Storage planning for embeddings:** Each embedding vector at 3072 dimensions uses approximately 12KB of storage. At 100 chunks per document across 10,000 documents, that is roughly 12GB — well beyond the free tier. Two options to manage this:

- **Reduce dimensions to 1536** — OpenAI's `text-embedding-3-large` supports flexible dimensions. 1536 dimensions cuts storage in half with minimal quality loss and is a reasonable default for this use case. Update `EMBEDDING_DIMENSIONS=1536` in your `.env` and update the schema: `embedding vector(1536)`.
- **Upgrade to Supabase Pro** — $25/month, includes 8GB storage, $0.125/GB beyond that. The right move when you begin loading a full corpus.

**Recommended approach:** Use 1536 dimensions and the free tier during development and initial testing. Upgrade to Pro when loading the full corpus at scale.

---

## Verification Checklist

Before running any pipeline workflow, verify each item:

- [ ] Google Drive folder structure `/portfolio-intel/documents/` created
- [ ] Existing local text files uploaded into the correct folder structure
- [ ] Google Drive API enabled in Google Cloud Console
- [ ] Service account created and JSON key file downloaded to your Mac
- [ ] `/portfolio-intel/` folder shared with the service account email
- [ ] Supabase project created and connection string saved
- [ ] pgvector extension enabled (`CREATE EXTENSION IF NOT EXISTS vector` ran without error)
- [ ] All three database tables visible in Supabase Table Editor
- [ ] `.env` file created with all required variables
- [ ] `.env` added to `.gitignore`
- [ ] Pipeline can connect to Supabase database (test connection)
- [ ] Pipeline can list files in Google Drive root folder (test API access)

---

## Cost Summary

| Service | Cost |
|---|---|
| Supabase free tier | $0 |
| Supabase Pro (when scaling) | $25/month |
| Google Drive storage | $0 up to 15GB |
| Google Drive API | $0 |
| OpenAI embeddings (text-embedding-3-large, 1536 dims) | ~$0.065 per million tokens |
| Anthropic Claude API (classification fallback only) | Minimal |
| **Total to get started** | **$0** |
