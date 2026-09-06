"""One-off reconnaissance tool - NOT part of the CLI.

Attaches to your already-open, already-logged-in Chrome (via
--remote-debugging-port) and logs network responses and WebSocket frames
related to the draft, so we can find out what mechanism ESPN's own page
actually uses to get live pick updates (since the public mDraftDetail
REST view does not reflect picks until the draft fully completes -
confirmed live against a throwaway league).

Usage:
    1. Quit and relaunch Chrome with: open -a "Google Chrome" --args --remote-debugging-port=9222
    2. Open the ESPN draft room in that Chrome window.
    3. python3 scripts/capture_draft_traffic.py
    4. Let a few picks happen (yours or autopicked), watch the output.
    5. Ctrl+C when you've seen enough.
"""

import sys
import time

from playwright.sync_api import sync_playwright

KEYWORDS = ("draft", "pick", "communication", "kona", "espn")


def looks_relevant(url: str) -> bool:
    lowered = url.lower()
    return "espn.com" in lowered and any(k in lowered for k in KEYWORDS)


def main():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"Could not attach to Chrome on port 9222: {e}")
            print('Did you relaunch Chrome with: open -a "Google Chrome" --args --remote-debugging-port=9222 ?')
            sys.exit(1)

        page = None
        for context in browser.contexts:
            for pg in context.pages:
                if "fantasy.espn.com" in pg.url and "draft" in pg.url:
                    page = pg
                    break
            if page:
                break

        if not page:
            print("Could not find an open ESPN draft tab across any Chrome window.")
            print("Open the draft room in this Chrome instance and try again.")
            sys.exit(1)

        print(f"Attached to: {page.url}\n")

        def on_response(response):
            if looks_relevant(response.url):
                print(f"[HTTP {response.status}] {response.request.method} {response.url}")

        def on_websocket(ws):
            print(f"[WEBSOCKET OPENED] {ws.url}")
            ws.on("framereceived", lambda payload: print(f"[WS RECV] {str(payload)[:500]}"))
            ws.on("framesent", lambda payload: print(f"[WS SENT] {str(payload)[:300]}"))

        page.on("response", on_response)
        page.on("websocket", on_websocket)

        print("Listening for draft-related network activity. Let a few picks happen, then Ctrl+C.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
