#!/bin/bash

# Run Django tests locally
# This script sets up the environment and runs the tests

echo "Setting up test environment..."

# Set environment variables for testing
export HOST=localhost
export NAME=test_db
export PORT=5432
export DBUSER=postgres
export PASSWORD=postgres
export SSLMODE=disable
export CAMPUS="Test Campus"

# Check if we're in the right directory
if [ ! -f "evalink/manage.py" ]; then
    echo "Error: manage.py not found. Make sure you're in the project root directory."
    exit 1
fi

# Activate virtual environment if it exists
if [ -d "marsenv" ]; then
    echo "Activating virtual environment..."
    source marsenv/bin/activate
fi

# Install dependencies if needed
echo "Installing dependencies..."
pip install -r requirements.txt

# Run the tests
echo "Running Django tests..."
cd evalink
export DJANGO_SETTINGS_MODULE=evalink.test_settings
python manage.py test --verbosity=2

echo "Tests completed!"
