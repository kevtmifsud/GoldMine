"""WF-02: Document Classification.

Classifies documents by type using path-based rules.
Currently all documents under /transcripts/{ticker}/ are earnings_transcript.

Supports explicit classification override for documents originating from
UI forms (analyst notes) or vendor feeds (sellside/buyside notes).  Set
``classification_method='explicit'`` on the DocumentJob to skip path rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ingestion import DocumentJob


@dataclass
class ClassificationResult:
    document_type: str
    chunking_template: str
    classification_method: str


# Path-based classification rules
SUBFOLDER_TYPES = {
    "earnings_transcript": ("earnings_transcript", "template_a"),
    "10K": ("10K", "template_b"),
    "10Q": ("10Q", "template_c"),
    "8K": ("8K", "template_d"),
    "investor_day": ("investor_day", "template_e"),
}

FILENAME_KEYWORDS = {
    "transcript": ("earnings_transcript", "template_a"),
    "earnings_call": ("earnings_transcript", "template_a"),
    "call": ("earnings_transcript", "template_a"),
    "10-K": ("10K", "template_b"),
    "10K": ("10K", "template_b"),
    "annual_report": ("10K", "template_b"),
    "10-Q": ("10Q", "template_c"),
    "10Q": ("10Q", "template_c"),
    "8-K": ("8K", "template_d"),
    "8K": ("8K", "template_d"),
    "investor_day": ("investor_day", "template_e"),
    "investor_presentation": ("investor_day", "template_e"),
}

# Explicit doc types supported via UI / vendor feeds.
# Maps doc_type → chunking template.
EXPLICIT_DOC_TYPES = {
    "analyst_note": "template_a",
    "sellside_note": "template_a",
    "buyside_note": "template_a",
}


def classify_job(job: DocumentJob) -> ClassificationResult:
    """Classify a DocumentJob, respecting explicit overrides.

    If ``job.classification_method == 'explicit'``, use the ``document_type``
    already set on the job (analyst_note, sellside_note, buyside_note, etc.)
    and skip path-based classification entirely.

    Otherwise, fall through to path-based ``classify_document()``.
    """
    if job.classification_method == "explicit":
        doc_type = job.document_type
        template = EXPLICIT_DOC_TYPES.get(doc_type, "template_a")
        return ClassificationResult(doc_type, template, "explicit")
    return classify_document(job.file_path)


def classify_document(file_path: str) -> ClassificationResult:
    """Classify a document based on its file path.

    Decision tree:
    1. Check for document_type subfolder
    2. If under /transcripts/{ticker}/ directly → earnings_transcript
    3. Keyword match on filename
    4. Default to unknown
    """
    parts = file_path.strip("/").split("/")

    # Step 1: Check for subfolder-based classification
    # Expected: /transcripts/{ticker}/{doc_type}/{filename}
    if len(parts) >= 4:
        subfolder = parts[2]
        if subfolder in SUBFOLDER_TYPES:
            doc_type, template = SUBFOLDER_TYPES[subfolder]
            return ClassificationResult(doc_type, template, "path")

    # Step 2: Direct under /transcripts/{ticker}/ → earnings_transcript
    if len(parts) == 3 and parts[0] == "transcripts":
        return ClassificationResult("earnings_transcript", "template_a", "path")

    # Step 3: Keyword fallback on filename
    filename = parts[-1].lower() if parts else ""
    for keyword, (doc_type, template) in FILENAME_KEYWORDS.items():
        if keyword.lower() in filename:
            return ClassificationResult(doc_type, template, "filename")

    # Step 4: Unknown
    return ClassificationResult("unknown", "none", "unknown")
