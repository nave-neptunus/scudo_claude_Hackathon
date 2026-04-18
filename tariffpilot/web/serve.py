#!/usr/bin/env python3
"""Serve the Espada operator console on localhost:3000."""
import http.server
import os
import webbrowser

PORT = 3000
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print(f"  Espada UI  → http://localhost:{PORT}")
print(f"  Requires backend running on http://localhost:8000")
print(f"  Start backend: cd backend && ./start.sh")
print()
webbrowser.open(f"http://localhost:{PORT}")
http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=PORT)
