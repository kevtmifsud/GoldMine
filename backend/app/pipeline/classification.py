"""WF-02: Document Classification.

Classifies documents by type using path-based rules.
Currently all documents under /transcripts/{ticker}/ are earnings_transcript.
"""
from __future__ import annotations

from dataclasses import dataclass


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
