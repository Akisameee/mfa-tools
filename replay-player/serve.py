"""Serve the replay locally, including its inline playback controls."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    handler = partial(
        SimpleHTTPRequestHandler, directory=str(Path(__file__).resolve().parent)
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Player: http://127.0.0.1:{args.port}/", flush=True)
    server.serve_forever()
