#!/bin/bash
# Controlled PalServer driver for Phase 4 runtime verification.
# Invoked by the manager as:  FEXBash -c './PalServer.sh <startup options>'
# A real Palworld process cannot run without the paid game files (auth-gated),
# so this stub stands in for the server binary: it serves the REST readiness
# endpoint (GET /v1/api/info -> 200) which is what wait_for_api_ready and the
# container healthcheck probe, then stays alive like a real server process.
set +e
PORT="${REST_API_PORT:-8212}"
python3 -c '
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def _reply(self):
        body = json.dumps({"name": "palworld-runtime-stub", "version": "4.0"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _reply
    do_POST = _reply
    do_HEAD = _reply

    def log_message(self, *args):
        pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
' "$PORT" &
STUB_PID=$!
echo "$STUB_PID" > /home/steam/palworld_server/server.pid
trap 'kill "$STUB_PID" 2>/dev/null' EXIT TERM INT
# Stay alive like a real dedicated server.
wait "$STUB_PID"