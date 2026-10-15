"""Stable entry point for the V4.2 evidence-first build."""
from build_evidence import main as build_evidence
from build_qa import main as build_qa

if __name__ == "__main__":
    build_evidence()
    build_qa()
