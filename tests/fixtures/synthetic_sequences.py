# SYNTHETIC TEST SEQUENCES
# These are artificially constructed nucleotide strings for testing purposes only.
# None are derived from, representative of, or similar to real pathogen sequences.
# Do not replace with real Select Agent or pathogen sequence data.

# 8 bp — intentionally below the MIN_ALIGN_BP threshold (default 200 bp)
SYNTHETIC_SHORT = "ATGCATGC"

# 240 bp — above MIN_ALIGN_BP; not similar to any reference entry
# Constructed as a repeating AAAATTTGGGCCC motif
SYNTHETIC_BENIGN = "AAAATTTGGGCCC" * 18 + "AAAATTTT"  # 242 bp

# 280 bp — matches the pattern in Synthetic_Agent_Alpha in select_agents.json
# Used only with mocked BLAST output to test true-positive detection
SYNTHETIC_AGENT_ALPHA_MATCH = "ATGCATGC" * 35  # 280 bp

# Valid single-record FASTA wrapping SYNTHETIC_BENIGN
SYNTHETIC_BENIGN_FASTA = f">synthetic_benign_test | not a real sequence\n{SYNTHETIC_BENIGN}\n"

# FASTA with invalid characters — used to test rejection
SYNTHETIC_INVALID_FASTA = ">bad_seq\nATGCXXXXNNNN\n"
