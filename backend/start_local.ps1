$ErrorActionPreference = "Stop"

# Using default SQLite database for local demo
$env:DATABASE_URL = ""

Write-Host "Checking virtual environment..."
if (-Not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

Write-Host "Activating virtual environment..."
.\venv\Scripts\activate

Write-Host "Installing dependencies..."
pip install -r requirements.txt

Write-Host "Starting FastAPI server..."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
