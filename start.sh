#!/bin/bash
set -e

echo "Installing Python dependencies..."
pip install -r requirements.txt

# Download frontend libraries locally (avoids CDN dependency / SRI issues)
LIBS_DIR="frontend/libs"
mkdir -p "$LIBS_DIR"

if [ ! -f "$LIBS_DIR/marked.min.js" ]; then
    echo "Downloading marked.js..."
    curl -fsSL "https://cdn.jsdelivr.net/npm/marked@9.1.6/marked.min.js" -o "$LIBS_DIR/marked.min.js"
fi

if [ ! -f "$LIBS_DIR/highlight.min.js" ]; then
    echo "Downloading highlight.js..."
    curl -fsSL "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js" -o "$LIBS_DIR/highlight.min.js"
fi

echo "Starting server..."
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
