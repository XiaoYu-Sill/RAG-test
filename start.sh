#!/bin/bash
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Starting server..."
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
