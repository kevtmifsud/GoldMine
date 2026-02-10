#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting GoldMine development servers..."

# Generate sample data if not present
if [ ! -f "$PROJECT_DIR/data/structured/stocks.csv" ]; then
    echo "Generating sample data..."
    python3 "$SCRIPT_DIR/generate_sample_data.py"
fi

# Start backend
echo "Starting backend on port 8000..."
cd "$PROJECT_DIR/backend"
source .venv/bin/activate 2>/dev/null || true
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on port 5173..."
cd "$PROJECT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

cleanup() {
    echo ""
    echo "Stopping servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait
}
trap cleanup EXIT INT TERM

wait
