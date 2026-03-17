"""WF-03: Semantic Chunking & Section Metadata.

Parses earnings transcripts (tabular format) into semantically meaningful chunks
with section-level metadata. Each chunk represents a complete thought with
speaker attribution and section classification.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from .config import MIN_CHUNK_TOKENS, MAX_CHUNK_TOKENS, TARGET_CHUNK_TOKENS


@dataclass
class Paragraph:
    number: int
    speaker: str
    content: str


@dataclass
class Chunk:
    chunk_text: str
    section_name: str
    section_type: str
    chunk_sequence: int
    word_count: int
    speaker: str = ""


# ---- Boilerplate patterns to skip ----
BOILERPLATE_PATTERNS = [
    r"forward[\-\s]looking\s+statements?",
    r"safe\s+harbor",
    r"this\s+call\s+(?:is\s+being|will\s+be)\s+recorded",
    r"please\s+(?:limit|restrict)\s+(?:yourself|yourselves)\s+to",
    r"(?:operator,?\s+)?(?:may\s+we|can\s+we)\s+have\s+the\s+(?:first|next)\s+question",
]

# ---- Speaker role classification ----
OPERATOR_NAMES = {"operator"}

CEO_TITLES = {"ceo", "chief executive", "president"}
CFO_TITLES = {"cfo", "chief financial", "finance"}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~0.75 tokens per word for English."""
    return int(len(text.split()) * 1.33)


def _is_boilerplate(text: str) -> bool:
    lower = text.lower()
    for pattern in BOILERPLATE_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


# ---------------------------------------------------------------------------
# Parse tabular transcript format
# ---------------------------------------------------------------------------
def parse_transcript_table(text: str) -> list[Paragraph]:
    """Parse a pipe-delimited transcript table into paragraphs."""
    paragraphs: list[Paragraph] = []

    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Skip header/separator rows
        if line.startswith("|---") or line.startswith("|   paragraph") or "===" in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        # parts[0] is empty (before first |), parts[-1] is empty (after last |)
        parts = [p for p in parts if p]

        if len(parts) < 3:
            continue

        try:
            num = int(parts[0])
        except ValueError:
            continue

        speaker = parts[1].strip()
        content = parts[2].strip()

        if not content:
            continue

        paragraphs.append(Paragraph(number=num, speaker=speaker, content=content))

    return paragraphs


# ---------------------------------------------------------------------------
# Identify speaker roles and sections
# ---------------------------------------------------------------------------
def _classify_speaker_role(speaker: str, known_roles: dict[str, str]) -> str:
    """Return a role for a speaker based on cached knowledge."""
    if speaker in known_roles:
        return known_roles[speaker]
    lower = speaker.lower()
    if lower in OPERATOR_NAMES:
        return "operator"
    return "unknown"


def _detect_qa_start(paragraphs: list[Paragraph]) -> int:
    """Find the paragraph index where Q&A begins.

    Q&A starts after the prepared remarks, typically signaled by the operator
    introducing the first analyst question or the IR person handing off.
    Heuristic: look for a paragraph by Operator after paragraph 3+ that contains
    'question' or 'Q&A', or the first analyst question (a non-executive, non-operator
    speaker after the prepared remarks block).
    """
    # Identify the first few speakers (they're the executives)
    exec_speakers = set()
    for p in paragraphs[:6]:
        if p.speaker.lower() != "operator":
            exec_speakers.add(p.speaker)

    # Find first non-exec, non-operator speaker after paragraph 3
    for i, p in enumerate(paragraphs):
        if i < 3:
            continue
        if p.speaker.lower() == "operator" and re.search(r"question|Q\s*&\s*A", p.content, re.I):
            return i
        if p.speaker not in exec_speakers and p.speaker.lower() != "operator" and i >= 3:
            return i

    # Fallback: assume Q&A starts at 60% through
    return max(3, int(len(paragraphs) * 0.6))


def _identify_exec_roles(paragraphs: list[Paragraph], qa_start: int) -> dict[str, str]:
    """Identify CEO and CFO from prepared remarks speakers and content.

    Strategy:
    1. First non-operator speaker = IR moderator
    2. Check IR moderator's intro for "CEO <name>" / "CFO <name>" patterns
    3. Fall back to positional assignment: after IR, next is CEO, then CFO
    """
    roles: dict[str, str] = {}

    for p in paragraphs[:qa_start]:
        if p.speaker.lower() == "operator":
            roles[p.speaker] = "operator"

    # The first paragraph by a non-operator is often the IR person who introduces others
    non_op_speakers = [p.speaker for p in paragraphs[:qa_start] if p.speaker.lower() != "operator"]
    unique_speakers = list(dict.fromkeys(non_op_speakers))  # preserve order, dedupe

    if not unique_speakers:
        return roles

    # First non-operator is usually IR/moderator
    ir_speaker = unique_speakers[0]
    roles[ir_speaker] = "ir_moderator"

    # Try to match names from the IR moderator's introduction to CEO/CFO titles
    ir_content = ""
    for p in paragraphs[:qa_start]:
        if p.speaker == ir_speaker:
            ir_content += " " + p.content

    # Try to match speaker names from the IR introduction to CEO/CFO titles.
    # Use a two-pass approach: first find all title-name associations, then assign.
    ir_lower = ir_content.lower()
    speaker_scores: dict[str, dict[str, int]] = {}  # speaker -> {role -> proximity}

    for speaker in unique_speakers[1:]:
        if speaker in roles:
            continue
        last_name = speaker.split()[-1].lower() if speaker.split() else ""
        if not last_name:
            continue

        speaker_scores[speaker] = {}
        # Find the position of the last name in the IR text
        name_pos = ir_lower.find(last_name)
        if name_pos == -1:
            continue

        # Check proximity of each title to the name
        all_titles = [("ceo", t) for t in CEO_TITLES] + [("cfo", t) for t in CFO_TITLES]
        for role, title in all_titles:
            title_pos = ir_lower.find(title)
            if title_pos == -1:
                continue
            distance = abs(name_pos - title_pos)
            if distance < 80:
                if role not in speaker_scores[speaker] or distance < speaker_scores[speaker][role]:
                    speaker_scores[speaker][role] = distance

    # Assign roles by closest proximity, preventing duplicates
    assigned_roles: set[str] = set()
    # Build (distance, speaker, role) tuples and sort by distance
    candidates = []
    for speaker, scores in speaker_scores.items():
        for role, distance in scores.items():
            candidates.append((distance, speaker, role))
    candidates.sort()

    for _, speaker, role in candidates:
        if speaker in roles or role in assigned_roles:
            continue
        roles[speaker] = role
        assigned_roles.add(role)

    # Fall back to positional assignment: after IR, next is CEO, then CFO
    unassigned = [s for s in unique_speakers if s not in roles]
    if unassigned and "ceo" not in roles.values():
        roles[unassigned[0]] = "ceo"
        unassigned = unassigned[1:]
    if unassigned and "cfo" not in roles.values():
        roles[unassigned[0]] = "cfo"
        unassigned = unassigned[1:]
    for s in unassigned:
        roles[s] = "executive"

    return roles


# ---------------------------------------------------------------------------
# Chunking logic
# ---------------------------------------------------------------------------
def _merge_paragraphs_into_chunks(
    paragraphs: list[Paragraph],
    section_name: str,
    section_type: str,
    start_seq: int,
) -> list[Chunk]:
    """Merge consecutive paragraphs into chunks within token budget."""
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    current_text = ""
    current_speaker = paragraphs[0].speaker
    seq = start_seq

    for p in paragraphs:
        p_tokens = _estimate_tokens(p.content)

        # If adding this paragraph would exceed max, flush current
        if current_text and _estimate_tokens(current_text) + p_tokens > MAX_CHUNK_TOKENS:
            wc = len(current_text.split())
            chunks.append(Chunk(
                chunk_text=current_text.strip(),
                section_name=section_name,
                section_type=section_type,
                chunk_sequence=seq,
                word_count=wc,
                speaker=current_speaker,
            ))
            seq += 1
            current_text = ""

        if not current_text:
            current_speaker = p.speaker

        current_text += f"\n{p.speaker}: {p.content}" if current_text else f"{p.speaker}: {p.content}"

    # Flush remaining
    if current_text.strip():
        wc = len(current_text.split())
        # Only create chunk if it has meaningful content
        if wc >= 20:
            chunks.append(Chunk(
                chunk_text=current_text.strip(),
                section_name=section_name,
                section_type=section_type,
                chunk_sequence=seq,
                word_count=wc,
                speaker=current_speaker,
            ))
            seq += 1

    return chunks


def _chunk_qa_section(
    paragraphs: list[Paragraph],
    exec_speakers: set[str],
    start_seq: int,
) -> list[Chunk]:
    """Chunk Q&A section: pair analyst questions with management answers."""
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    seq = start_seq

    # Group into exchanges: analyst question(s) + management answer(s)
    current_exchange: list[Paragraph] = []
    current_is_qa = False

    for p in paragraphs:
        is_exec = p.speaker in exec_speakers or p.speaker.lower() == "operator"
        is_analyst = not is_exec

        if is_analyst and current_exchange and any(
            pp.speaker in exec_speakers for pp in current_exchange
        ):
            # New analyst question after management answered — flush previous exchange
            text = "\n".join(f"{pp.speaker}: {pp.content}" for pp in current_exchange)
            wc = len(text.split())
            if wc >= 20:
                chunks.append(Chunk(
                    chunk_text=text,
                    section_name="Q&A Exchange",
                    section_type="qa_exchange",
                    chunk_sequence=seq,
                    word_count=wc,
                ))
                seq += 1
            current_exchange = []

        current_exchange.append(p)

    # Flush last exchange
    if current_exchange:
        text = "\n".join(f"{pp.speaker}: {pp.content}" for pp in current_exchange)
        wc = len(text.split())
        if wc >= 20:
            chunks.append(Chunk(
                chunk_text=text,
                section_name="Q&A Exchange",
                section_type="qa_exchange",
                chunk_sequence=seq,
                word_count=wc,
            ))

    # Split any oversized Q&A chunks
    final_chunks: list[Chunk] = []
    for c in chunks:
        if _estimate_tokens(c.chunk_text) > MAX_CHUNK_TOKENS:
            # Split by speaker turns
            lines = c.chunk_text.split("\n")
            mid = len(lines) // 2
            part1 = "\n".join(lines[:mid])
            part2 = "\n".join(lines[mid:])
            final_chunks.append(Chunk(
                chunk_text=part1,
                section_name=c.section_name,
                section_type=c.section_type,
                chunk_sequence=c.chunk_sequence,
                word_count=len(part1.split()),
            ))
            final_chunks.append(Chunk(
                chunk_text=part2,
                section_name=c.section_name,
                section_type=c.section_type,
                chunk_sequence=c.chunk_sequence + 1,
                word_count=len(part2.split()),
            ))
        else:
            final_chunks.append(c)

    # Re-number sequences
    for i, c in enumerate(final_chunks):
        c.chunk_sequence = start_seq + i

    return final_chunks


# ---------------------------------------------------------------------------
# Main chunking entry point
# ---------------------------------------------------------------------------
def chunk_transcript(text: str) -> list[Chunk]:
    """Parse and chunk an earnings transcript.

    Returns a list of Chunks with section metadata.
    """
    paragraphs = parse_transcript_table(text)
    if not paragraphs:
        return []

    # Filter boilerplate
    paragraphs = [p for p in paragraphs if not _is_boilerplate(p.content)]

    # Detect Q&A boundary
    qa_start_idx = _detect_qa_start(paragraphs)

    # Identify executive roles
    exec_roles = _identify_exec_roles(paragraphs, qa_start_idx)

    # Split into prepared remarks and Q&A
    prepared = paragraphs[:qa_start_idx]
    qa = paragraphs[qa_start_idx:]

    chunks: list[Chunk] = []
    seq = 0

    # ---- Chunk prepared remarks by speaker ----
    current_speaker = ""
    current_paragraphs: list[Paragraph] = []

    for p in prepared:
        role = exec_roles.get(p.speaker, "executive")

        if p.speaker != current_speaker and current_paragraphs:
            # Flush previous speaker's paragraphs
            prev_role = exec_roles.get(current_speaker, "executive")
            section_name, section_type = _role_to_section(prev_role, current_speaker)
            new_chunks = _merge_paragraphs_into_chunks(
                current_paragraphs, section_name, section_type, seq
            )
            chunks.extend(new_chunks)
            seq += len(new_chunks)
            current_paragraphs = []

        current_speaker = p.speaker
        current_paragraphs.append(p)

    # Flush last prepared remarks speaker
    if current_paragraphs:
        role = exec_roles.get(current_speaker, "executive")
        section_name, section_type = _role_to_section(role, current_speaker)
        new_chunks = _merge_paragraphs_into_chunks(
            current_paragraphs, section_name, section_type, seq
        )
        chunks.extend(new_chunks)
        seq += len(new_chunks)

    # ---- Chunk Q&A section ----
    exec_speaker_set = {s for s, r in exec_roles.items() if r in ("ceo", "cfo", "executive", "ir_moderator")}
    qa_chunks = _chunk_qa_section(qa, exec_speaker_set, seq)
    chunks.extend(qa_chunks)

    return chunks


def _role_to_section(role: str, speaker: str) -> tuple[str, str]:
    """Map a speaker role to section_name and section_type."""
    if role == "ceo":
        return f"CEO Prepared Remarks ({speaker})", "ceo_remarks"
    elif role == "cfo":
        return f"CFO Prepared Remarks ({speaker})", "cfo_remarks"
    elif role == "operator":
        return "Operator", "operator"
    elif role == "ir_moderator":
        return f"IR Introduction ({speaker})", "operator"
    else:
        return f"Executive Remarks ({speaker})", "ceo_remarks"
