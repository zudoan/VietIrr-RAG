"""Serve the repository locally so the review UI can open source PDFs."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
import os

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
host, port = "127.0.0.1", args.port
print(f"Open http://{host}:{port}/research/vietirr_v4_3/QA_REVIEW_TOOL/index.html")
ThreadingHTTPServer((host, port), SimpleHTTPRequestHandler).serve_forever()
