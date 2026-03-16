# WF-03: Semantic Chunking & Section Metadata

## Purpose

This is the most consequential workflow in Mode 1. The quality of chunking directly determines the quality of retrieval in Mode 2. A poorly chunked document produces incomplete or misleading answers regardless of how good the LLM is. A well-chunked document with rich metadata enables precise, fast, low-cost retrieval.

The goal is to split each document into chunks that represent complete, self-contained ideas, and tag each chunk with metadata that allows filtered retrieval.

---

## Core Chunking Principles

**A chunk should represent a complete thought.** Half a risk factor, or a margin discussion split across two chunks, degrades retrieval quality. When in doubt, keep related content together.

**Respect the document's natural structure.** Financial documents have well-defined sections. Use those boundaries — don't impose arbitrary size limits that cut across them.

**Size limits are a safety net, not a primary splitter.** If a section is naturally 800 tokens, keep it as one chunk. Only split if a section is so long that it would dominate the context window when retrieved.

**Chunk size target**: 400–1000 tokens per chunk. Below 400 tokens risks losing context. Above 1000 tokens risks retrieving too much irrelevant content alongside what the user needs.

---

## Chunking Templates by Document Type

### Template A: Earnings Transcript

Earnings transcripts have a highly consistent structure across all companies. Use this structure as the primary chunking boundary:

| Section | Description | Chunk strategy |
|---|---|---|
| Operator introduction | Boilerplate call opening | Single small chunk or discard |
| CEO prepared remarks | Strategic overview, business highlights | Chunk by natural paragraph breaks, keep together where possible |
| CFO prepared remarks | Financial results, guidance, segment discussion | Chunk by topic (revenue, margins, guidance, segment) — this is the highest-value section |
| Q&A — analyst questions | Individual analyst question turns | Each question + immediate answer = one chunk |
| Q&A — management answers | Continuation of Q&A | Paired with preceding question chunk |
| Closing remarks | Boilerplate | Single chunk or discard |

**Key insight for transcripts**: The CFO prepared remarks section is where most financial metric discussions live. Q&A sections often contain more granular elaboration. These two sections should be preserved with high fidelity.

### Template B: 10-K Annual Filing

10-Ks are long (often 100+ pages) and highly structured with standardized SEC section headings:

| SEC Section | Chunk strategy |
|---|---|
| Business Overview (Item 1) | Chunk by subsection (products, markets, competition, etc.) |
| Risk Factors (Item 1A) | Each individual risk factor = one chunk |
| MD&A (Item 7) | Chunk by topic (results of operations, liquidity, segment discussion, outlook) |
| Financial Statements (Item 8) | Largely handled by structured DB — minimal chunking needed |
| Quantitative Disclosures (Item 7A) | Single chunk per disclosure type |

**Key insight for 10-Ks**: Risk Factors and MD&A are the highest-value sections for retrieval. Financial statement tables are redundant with structured DB data and can be deprioritized or skipped entirely.

### Template C: 10-Q Quarterly Filing

Similar to 10-K but shorter. Apply the same MD&A and Risk Factor logic. Focus on:
- MD&A — results vs. prior quarter and prior year
- Any new or updated risk factors
- Management outlook language

### Template D: 8-K Material Event Filing

8-Ks are short and event-specific. Often the entire filing is 1-3 chunks:
- Event description (what happened)
- Financial impact if disclosed
- Exhibit content if relevant (e.g., press release text)

### Template E: Investor Day Presentation

These vary significantly by company. Treat as a series of speaker segments, similar to earnings transcript Q&A logic. Each speaker's topic = one chunk.

---

## Section Metadata Schema

Every chunk stored in the vector DB must carry the following metadata:

| Field | Description | Example |
|---|---|---|
| `chunk_id` | Unique identifier for this chunk | `uuid` |
| `document_id` | Foreign key to processing registry | links to WF-01 record |
| `ticker` | Ticker symbol | `AAPL` |
| `document_type` | From WF-02 classification | `earnings_transcript` |
| `fiscal_period` | Period the document covers | `Q4_2024` |
| `filing_date` | Date document was filed or published | `2025-01-30` |
| `section_name` | Human-readable section label | `CFO Prepared Remarks` |
| `section_type` | Controlled vocabulary type | `cfo_remarks` |
| `chunk_sequence` | Order of chunk within document | `14` |
| `page_reference` | Page number in source document if available | `8` |
| `word_count` | Word count of chunk | `412` |

### Controlled Vocabulary for `section_type`

Using a controlled vocabulary (not free text) for section_type enables precise metadata filtering in Mode 2:

```
ceo_remarks
cfo_remarks
qa_exchange
risk_factors
mda_results
mda_outlook
mda_liquidity
mda_segments
business_overview
financial_statements
event_description
unknown_section
```

---

## Handling Ambiguous Section Boundaries

Some documents — especially older transcripts or inconsistently formatted filings — don't have clean section headers. In these cases:

1. Look for speaker attribution patterns (`OPERATOR:`, `CEO:`, analyst names) for transcripts
2. Look for capitalized headings or numbered items for filings
3. Fall back to paragraph-based chunking with a 600-token target size
4. Tag these chunks as `section_type: unknown_section` so retrieval quality can be monitored

---

## What NOT to Chunk

Some content adds noise to retrieval without value:

- Boilerplate legal disclaimers (forward-looking statements warnings, safe harbor language)
- Operator introduction scripts
- Financial statement tables (already in structured DB)
- Repetitive reconciliation tables (GAAP to non-GAAP) unless the narrative around them is meaningful
- Table of contents

These can be identified by keyword matching and excluded before chunking begins.

---

## Output

For each document, a list of chunks each containing:
- Chunk text (cleaned, boilerplate removed)
- Full metadata as defined above
- Ready for embedding generation in WF-04

---

## Key Considerations

**Chunking is not reversible cheaply.** If chunking logic is improved later, documents need to be re-chunked and re-embedded. Getting the strategy right upfront saves significant cost. Invest time here before processing at scale.

**Test on representative documents first.** Before running the pipeline at scale, manually review chunking output on 2-3 documents of each type. Check that chunks are semantically complete and that metadata is accurate.

**Chunk overlap.** A small overlap between adjacent chunks (e.g., last 50 tokens of chunk N repeated as first 50 tokens of chunk N+1) can improve retrieval for content that spans boundaries. This is optional but worth considering for long narrative sections like MD&A.
