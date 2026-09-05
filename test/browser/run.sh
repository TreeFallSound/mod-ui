#!/usr/bin/env bash
# Runs the browser smoke test of the SFZ builder island.
#
# serve.py gives /_smoke.html from test/browser/ and every other path from
# html/. Nothing is written into html/, because html/ is what deploy.sh sends
# to the device: an earlier version copied the page there and raced with rsync.
#
# The test needs headless Chrome. Without Chrome the script says so and stops
# with 0, so `make test` still passes on a machine that has no browser.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${SMOKE_PORT:-8899}"

CHROME=""
for candidate in \
    "${CHROME_BIN:-}" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "$(command -v google-chrome-stable 2>/dev/null)" \
    "$(command -v google-chrome 2>/dev/null)" \
    "$(command -v chromium 2>/dev/null)" \
    "$(command -v chromium-browser 2>/dev/null)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then CHROME="$candidate"; break; fi
done

if [ -z "$CHROME" ]; then
    echo "smoke: no headless Chrome on this machine, so the test did not run."
    echo "smoke: set CHROME_BIN to run it."
    exit 0
fi

cleanup() {
    [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null
    return 0
}
trap cleanup EXIT

python3 "$ROOT/test/browser/serve.py" "$PORT" &
SERVER_PID=$!

# Wait for the server to answer.
for _ in $(seq 1 40); do
    if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/_smoke.html" 2>/dev/null; then break; fi
    sleep 0.1
done

OUT="$("$CHROME" --headless --disable-gpu --no-sandbox \
        --virtual-time-budget=12000 \
        --dump-dom "http://127.0.0.1:$PORT/_smoke.html" 2>/dev/null \
      | python3 -c "
import sys, html, re
d = sys.stdin.read()
m = re.search(r'SMOKE_START(.*?)SMOKE_END', d, re.S)
print(html.unescape(m.group(1)).strip() if m else 'FAIL  the page did not run to the end')
")"

echo "$OUT"
if echo "$OUT" | grep -q '^FAIL'; then
    echo
    echo "smoke: FAILED"
    exit 1
fi
echo
echo "smoke: all checks passed"
