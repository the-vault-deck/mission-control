r"""
mAIn St. Solutions — MC3 Bridge Server v1.2
============================================
Runs locally on http://localhost:7070
Gives Mission Control 3 read/write access to your filesystem.

START: python bridge.py
       Then open: http://localhost:7070/mc3

STOP:  Ctrl+C

Canonical paths (locked 20260310):
  Souls:      C:\Users\Tony\Desktop\soul-staging\souls\
  EODs:       C:\Users\Tony\Desktop\soul-staging\eod\
  Tools:      C:\Users\Tony\Desktop\soul-staging\tools\
  Directives: C:\Users\Tony\Desktop\soul-staging\directives\

MC3 HTML: place mission-control-3_8.html in the soul-staging\ root folder.
          Bridge will serve it at http://localhost:7070/mc3

Endpoints:
  GET  /mc3                — serve MC3 HTML (same origin = no CORS issues)
  GET  /health             — confirm bridge is running
  GET  /soul?agent=id      — serve soul file to MC3 on agent assign
  GET  /list-souls         — list all soul files on disk
  GET  /read-eod?agent=id  — read scoped EODs for agent
  GET  /fetch-file?name=   — fetch exact file by name
  POST /write-eod          — file an EOD memo to disk
  POST /write-soul-delta   — file a soul update proposal (FORGE reviews)
"""

import os
import json
import glob
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# ── CANONICAL PATHS — DO NOT CHANGE WITHOUT ATLAS APPROVAL ──────────────────
SOUL_STAGING   = r"C:\Users\Tony\Desktop\soul-staging"
SOUL_DIR       = os.path.join(SOUL_STAGING, "souls")
EOD_DIR        = os.path.join(SOUL_STAGING, "eod")
TOOLS_DIR      = os.path.join(SOUL_STAGING, "tools")
DIRECTIVES_DIR = os.path.join(SOUL_STAGING, "directives")
PORT           = 7070
ALLOWED_ORIGIN = "*"
# ────────────────────────────────────────────────────────────────────────────

def ensure_dirs():
    for d in [SOUL_DIR, EOD_DIR, TOOLS_DIR, DIRECTIVES_DIR]:
        os.makedirs(d, exist_ok=True)

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def cors_headers():
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

class BridgeHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {format % args}")

    def send_json(self, code, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode() if length else ""

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs     = parse_qs(parsed.query)
        path   = parsed.path

        # Serve MC3 HTML from soul-staging root (same-origin = no CORS issues)
        if path in ('/mc3', '/mc3/'):
            # Find the highest-versioned MC3 HTML in soul-staging root
            mc3_files = sorted(glob.glob(os.path.join(SOUL_STAGING, "mission-control-*.html")))
            mc3_file = mc3_files[-1] if mc3_files else None
            if mc3_file:
                with open(mc3_file, 'r', encoding='utf-8') as f:
                    html = f.read().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(html))
                self.end_headers()
                self.wfile.write(html)
            else:
                self.send_json(404, {"error": "MC3 HTML not found in soul-staging root"})
            return

        if path == "/health":
            self.send_json(200, {
                "status": "online",
                "server": "MC3 Bridge v1.1",
                "time": datetime.now().isoformat(),
                "paths": {"souls": SOUL_DIR, "eod": EOD_DIR}
            })

        elif path == "/soul":
            agent_id = qs.get("agent", [None])[0]
            if not agent_id:
                self.send_json(400, {"error": "agent param required"})
                return
            found = None
            for ext in [".csl", ".json", ".md"]:
                pattern = os.path.join(SOUL_DIR, f"SOUL_{agent_id.upper()}_V*{ext}")
                matches = glob.glob(pattern)
                if not matches:
                    matches = glob.glob(os.path.join(SOUL_DIR, f"{agent_id.lower()}{ext}"))
                if matches:
                    found = sorted(matches)[-1]
                    break
            if not found:
                self.send_json(404, {
                    "error": f"No soul file found for: {agent_id}",
                    "looked_in": SOUL_DIR,
                    "tip": f"Expected: SOUL_{agent_id.upper()}_V1_[DATE].csl"
                })
                return
            with open(found, "r", encoding="utf-8") as f:
                content = f.read()
            self.send_json(200, {"agent": agent_id, "soul": content, "file": os.path.basename(found)})

        elif path == "/list-souls":
            files = sorted(set(
                [os.path.basename(f) for f in
                 glob.glob(os.path.join(SOUL_DIR, "*.csl")) +
                 glob.glob(os.path.join(SOUL_DIR, "*.json"))]
            ))
            self.send_json(200, {"files": files, "count": len(files), "dir": SOUL_DIR})

        elif path == "/read-eod":
            agent_id = qs.get("agent", [None])[0]
            memos = []

            if agent_id:
                # Load 1: most recent EOD for this agent
                pattern = os.path.join(EOD_DIR, f"EOD_{agent_id.upper()}_*.csl")
                agent_files = sorted(glob.glob(pattern))
                if agent_files:
                    with open(agent_files[-1], "r", encoding="utf-8") as f:
                        memos.append({"file": os.path.basename(agent_files[-1]), "content": f.read()})

                # Load 2: most recent ALL_STAFF memo
                all_staff = sorted(glob.glob(os.path.join(EOD_DIR, "EOD_ALL_STAFF_*.csl")))
                if all_staff:
                    with open(all_staff[-1], "r", encoding="utf-8") as f:
                        memos.append({"file": os.path.basename(all_staff[-1]), "content": f.read()})
            else:
                # Fallback: no agent specified — return nothing
                pass

            self.send_json(200, {"agent": agent_id, "memos": memos, "count": len(memos)})

        elif path == "/fetch-file":
            filename = qs.get("name", [None])[0]
            if not filename:
                self.send_json(400, {"error": "name param required"})
                return
            # Search eod\ folder only (archive subfolders included via walk)
            found = None
            for root, dirs, files in os.walk(EOD_DIR):
                if filename in files:
                    found = os.path.join(root, filename)
                    break
            # Also check souls\ folder
            if not found:
                candidate = os.path.join(SOUL_DIR, filename)
                if os.path.exists(candidate):
                    found = candidate
            if not found:
                self.send_json(404, {"error": f"File not found: {filename}"})
                return
            with open(found, "r", encoding="utf-8") as f:
                content = f.read()
            self.send_json(200, {"file": filename, "path": found, "content": content})

        else:
            self.send_json(404, {"error": "Unknown endpoint", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        body   = self.read_body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON body"})
            return

        if path == "/write-eod":
            agent   = data.get("agent", "unknown").upper()
            content = data.get("content", "")
            date    = data.get("date", today_str()).replace("-", "")
            hhmm    = datetime.now().strftime("%H%M")
            if not content:
                self.send_json(400, {"error": "content required"})
                return
            filename = f"EOD_{agent}_{date}_{hhmm}.csl"
            filepath = os.path.join(EOD_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  OK EOD filed: {filepath}")
            self.send_json(200, {"status": "filed", "path": filepath, "file": filename})

        elif path == "/write-soul-delta":
            agent  = data.get("agent", "unknown").upper()
            delta  = data.get("delta", "")
            reason = data.get("reason", "No reason provided")
            date   = today_str().replace("-", "")
            hhmm   = datetime.now().strftime("%H%M")
            if not delta:
                self.send_json(400, {"error": "delta content required"})
                return
            filename = f"SOUL_DELTA_{agent}_{date}_{hhmm}.md"
            filepath = os.path.join(EOD_DIR, filename)
            proposal = f"""SOUL DELTA PROPOSAL
==================
Agent:  {agent}
Date:   {today_str()}
Reason: {reason}

PROPOSED CHANGES:
-----------------
{delta}

STATUS: PENDING FORGE REVIEW
NOTE: FORGE must canonize before soul file is updated. Do not apply directly.
"""
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(proposal)
            print(f"  OK Soul delta filed: {filepath}")
            self.send_json(200, {"status": "proposal_filed", "file": filename,
                                  "note": "FORGE review required"})

        else:
            self.send_json(404, {"error": "Unknown endpoint", "path": path})


def main():
    ensure_dirs()
    print("=" * 60)
    print("  mAIn St. Solutions — MC3 Bridge Server v1.1")
    print("=" * 60)
    print(f"  Soul staging:  {SOUL_STAGING}")
    print(f"  Souls:         {SOUL_DIR}")
    print(f"  EODs:          {EOD_DIR}")
    print(f"  Listening:     http://localhost:{PORT}")
    print("=" * 60)
    print("  Soul file naming convention:")
    print("    SOUL_[AGENT]_V[N]_[DATE].csl")
    print("    e.g.  SOUL_ATLAS_V4_20260310.csl")
    print("=" * 60)
    print("  Ctrl+C to stop\n")
    server = HTTPServer(("localhost", PORT), BridgeHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Bridge offline.")

if __name__ == "__main__":
    main()
