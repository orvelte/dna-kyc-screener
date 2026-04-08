"""Sequence screening via local BLAST against the Select Agent reference database.

Input normalisation handles three formats:
  - "raw"       — plain nucleotide string
  - "fasta"     — FASTA-formatted string (single record)
  - "accession" — GenBank accession fetched via NCBI Entrez efetch

The reference database is built from data/select_agents.json at module import.
Sequences in the JSON are used directly; accessions listed there are fetched
lazily and cached in-process.

Requires `blastn` to be installed and on PATH. A RuntimeError is raised at
screen time (not import time) if the binary is not found.
"""

import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import httpx
from Bio import SeqIO
from Bio.Blast import NCBIXML

import config
from api.schemas import SequenceResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reference database — built once at module import
# ---------------------------------------------------------------------------


def _load_reference_db(path: str) -> tuple[str, dict[str, str]]:
    """Load the Select Agent reference DB and build an in-memory FASTA string.

    Args:
        path: Path to select_agents.json.

    Returns:
        Tuple of (reference_fasta, id_to_organism) where reference_fasta is a
        multi-record FASTA string and id_to_organism maps sequence IDs to
        organism names.

    Raises:
        ValueError: If no sequences can be loaded from the file.
    """
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fasta_lines: list[str] = []
    id_to_organism: dict[str, str] = {}
    seq_index = 0

    for entry in data:
        organism = entry.get("organism", f"unknown_{seq_index}")
        for seq in entry.get("sequences", []):
            seq_id = f"ref_{seq_index}"
            fasta_lines.append(f">{seq_id} {organism}")
            fasta_lines.append(seq.strip().upper())
            id_to_organism[seq_id] = organism
            seq_index += 1

    if not id_to_organism:
        raise ValueError(f"No sequences loaded from {path}")

    logger.info("Loaded %d reference sequences from %s", len(id_to_organism), path)
    return "\n".join(fasta_lines) + "\n", id_to_organism


_REFERENCE_FASTA, _ID_TO_ORGANISM = _load_reference_db(config.SELECT_AGENTS_PATH)
_ACCESSION_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------


def _parse_raw(sequence: str) -> str:
    """Validate and return a raw nucleotide string.

    Args:
        sequence: Raw nucleotide string (ATGCN characters, case-insensitive).

    Returns:
        Uppercase stripped nucleotide string.

    Raises:
        ValueError: If the string is empty or contains non-nucleotide characters.
    """
    cleaned = sequence.strip().upper().replace(" ", "").replace("\n", "")
    if not cleaned:
        raise ValueError("Sequence must not be empty")
    invalid = set(cleaned) - set("ATGCNRYSWKMBDHV")
    if invalid:
        raise ValueError(f"Sequence contains invalid characters: {sorted(invalid)}")
    return cleaned


def _parse_fasta(sequence: str) -> str:
    """Extract the nucleotide string from a single-record FASTA input.

    Args:
        sequence: FASTA-formatted string.

    Returns:
        Uppercase nucleotide string of the first record.

    Raises:
        ValueError: If no valid FASTA record is found.
    """
    records = list(SeqIO.parse(io.StringIO(sequence), "fasta"))
    if not records:
        raise ValueError("No valid FASTA record found in input")
    seq_str = str(records[0].seq).upper()
    if not seq_str:
        raise ValueError("No valid FASTA record found in input — header present but sequence is empty")
    return seq_str


def _fetch_accession(accession: str) -> str:
    """Fetch a nucleotide sequence from NCBI Entrez by GenBank accession.

    Results are cached in-process for the lifetime of the module.

    Args:
        accession: GenBank accession string (e.g. "AE016879").

    Returns:
        Uppercase nucleotide string.

    Raises:
        httpx.HTTPError: If the Entrez request fails.
        ValueError: If the response cannot be parsed as FASTA.
    """
    accession = accession.strip()
    if accession in _ACCESSION_CACHE:
        logger.debug("Accession cache hit: %s", accession)
        return _ACCESSION_CACHE[accession]

    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=nucleotide&id={accession}&rettype=fasta&retmode=text"
    )
    logger.info("Fetching accession %s from Entrez", accession)
    response = httpx.get(url, timeout=30)
    response.raise_for_status()

    seq = _parse_fasta(response.text)
    _ACCESSION_CACHE[accession] = seq
    return seq


def _normalise_input(sequence: str, fmt: str) -> str:
    """Dispatch input normalisation based on format hint.

    Args:
        sequence: Raw input string from the API request.
        fmt: One of "raw", "fasta", or "accession".

    Returns:
        Uppercase nucleotide string ready for BLAST.

    Raises:
        ValueError: For invalid sequences or unknown format values.
    """
    if fmt == "raw":
        return _parse_raw(sequence)
    if fmt == "fasta":
        return _parse_fasta(sequence)
    if fmt == "accession":
        return _fetch_accession(sequence)
    raise ValueError(f"Unknown sequence format: {fmt!r}")


# ---------------------------------------------------------------------------
# BLAST runner
# ---------------------------------------------------------------------------


def _run_blast(
    query_seq: str,
    identity_threshold: float,
    min_align_bp: int,
) -> SequenceResult:
    """Run local blastn and return the best match against the reference DB.

    Uses the -subject flag to compare directly against a FASTA without
    requiring a pre-built BLAST database. Suitable for small reference sets.

    Args:
        query_seq: Normalised nucleotide string to screen.
        identity_threshold: Minimum percent identity to set flagged=True.
        min_align_bp: Minimum alignment length to consider a hit valid.

    Returns:
        SequenceResult with the best hit, or a zero-score result if no hits.

    Raises:
        RuntimeError: If blastn is not found on PATH.
    """
    if shutil.which("blastn") is None:
        raise RuntimeError(
            "blastn not found on PATH. Install BLAST+ to run sequence screening."
        )

    with (
        tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as query_fh,
        tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as subject_fh,
        tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as out_fh,
    ):
        query_path = query_fh.name
        subject_path = subject_fh.name
        out_path = out_fh.name

        query_fh.write(f">query\n{query_seq}\n")
        subject_fh.write(_REFERENCE_FASTA)

    try:
        proc = subprocess.run(
            [
                "blastn",
                "-query", query_path,
                "-subject", subject_path,
                "-outfmt", "5",
                "-out", out_path,
                "-dust", "no",
                "-word_size", "11",
            ],
            capture_output=True,
            text=True,
        )
        if proc.stderr:
            logger.debug("blastn stderr: %s", proc.stderr.strip())

        with open(out_path, encoding="utf-8") as fh:
            records = list(NCBIXML.parse(fh))

        return _parse_blast_records(records, identity_threshold, min_align_bp)

    finally:
        for p in (query_path, subject_path, out_path):
            Path(p).unlink(missing_ok=True)


def _parse_blast_records(
    records: list,
    identity_threshold: float,
    min_align_bp: int,
) -> SequenceResult:
    """Extract the best HSP from BLAST XML records.

    Iterates all hits and HSPs, applies the minimum alignment length filter,
    and returns the hit with the highest percent identity.

    Args:
        records: List of BLAST record objects from NCBIXML.parse.
        identity_threshold: Minimum percent identity to set flagged=True.
        min_align_bp: Minimum alignment length to consider a hit valid.

    Returns:
        SequenceResult with best hit, or zero-score result if no qualifying hits.
    """
    best_identity: float = 0.0
    best_organism: str | None = None

    for record in records:
        for alignment in record.alignments:
            # Extract seq_id from alignment title (format: "ref_N organism_name")
            title_parts = alignment.title.split(None, 1)
            seq_id = title_parts[0].lstrip(">")
            organism = _ID_TO_ORGANISM.get(seq_id, alignment.title)

            for hsp in alignment.hsps:
                if hsp.align_length < min_align_bp:
                    continue
                pct_identity = (hsp.identities / hsp.align_length) * 100.0
                if pct_identity > best_identity:
                    best_identity = pct_identity
                    best_organism = organism

    if best_identity == 0.0:
        logger.debug("Sequence screen: no qualifying BLAST hits")
        return SequenceResult(
            match_score=0.0,
            matched_organism=None,
            percent_identity=0.0,
            flagged=False,
        )

    flagged = best_identity >= identity_threshold
    match_score = round(best_identity / 100.0, 4)

    logger.debug(
        "Sequence screen: best_identity=%.2f%% organism=%r flagged=%s",
        best_identity,
        best_organism,
        flagged,
    )

    return SequenceResult(
        match_score=match_score,
        matched_organism=best_organism,
        percent_identity=round(best_identity, 2),
        flagged=flagged,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def screen_sequence(
    sequence: str,
    fmt: Literal["raw", "fasta", "accession"] = "raw",
    *,
    identity_threshold: float = config.SEQUENCE_IDENTITY_THRESHOLD,
    min_align_bp: int = config.SEQUENCE_MIN_ALIGN_BP,
) -> SequenceResult:
    """Screen a nucleotide sequence against the Select Agent reference database.

    Normalises the input, runs local BLAST, and returns the best match.
    Sequences shorter than min_align_bp cannot satisfy the alignment length
    requirement and will always return flagged=False.

    Args:
        sequence: Nucleotide input — raw string, FASTA, or GenBank accession.
        fmt: Format hint for the input string ("raw", "fasta", or "accession").
        identity_threshold: Percent identity at or above which the result is
                            flagged. Defaults to SEQUENCE_IDENTITY_THRESHOLD.
        min_align_bp: Minimum alignment length in bp for a hit to count.
                      Defaults to SEQUENCE_MIN_ALIGN_BP.

    Returns:
        SequenceResult with match_score, matched_organism, percent_identity,
        and flagged.

    Raises:
        ValueError: If the sequence is empty or malformed.
        RuntimeError: If blastn is not available on PATH.
        httpx.HTTPError: If an accession fetch fails.
    """
    query_seq = _normalise_input(sequence, fmt)

    if len(query_seq) < min_align_bp:
        logger.warning(
            "Query sequence length %d bp is below min_align_bp=%d — "
            "cannot satisfy alignment threshold, returning unflagged",
            len(query_seq),
            min_align_bp,
        )
        return SequenceResult(
            match_score=0.0,
            matched_organism=None,
            percent_identity=0.0,
            flagged=False,
        )

    return _run_blast(query_seq, identity_threshold, min_align_bp)
