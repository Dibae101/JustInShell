#!/bin/bash
# Development environment setup script

echo "Setting up development environment..."
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
