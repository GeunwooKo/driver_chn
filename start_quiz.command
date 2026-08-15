#!/bin/bash
cd "$(dirname "$0")"
PORT=8934

# kill any previous instance on this port
lsof -ti:$PORT -sTCP:LISTEN | xargs -r kill 2>/dev/null

python3 -m http.server $PORT &
SERVER_PID=$!

sleep 1
open "http://localhost:$PORT/index.html"

echo ""
echo "퀴즈 앱이 실행되었습니다: http://localhost:$PORT/index.html"
echo "이 창을 닫으면 서버가 종료됩니다. (종료하려면 Ctrl+C)"
wait $SERVER_PID
