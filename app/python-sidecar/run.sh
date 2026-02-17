#!/bin/bash
# Run the Claudetini backend sidecar

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the python-sidecar directory
cd "$SCRIPT_DIR"

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run the server
echo "Starting Claudetini backend on port 9876..."
python -m src.api.server --port 9876
