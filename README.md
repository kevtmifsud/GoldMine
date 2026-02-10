# GoldMine — Investment Research CRM

An Investment Research CRM platform for Portfolio Managers and Research Analysts.

## Prerequisites

- Node.js 20 LTS
- Python 3.12+

## Quick Start

```bash
# 1. Clone and enter the project
cd GoldMine

# 2. Set up backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 3. Generate sample data
cd ..
python3 scripts/generate_sample_data.py

# 4. Start backend
cd backend
uvicorn app.main:app --reload --port 8000

# 5. In a new terminal, set up and start frontend
cd frontend
npm install
npm run dev

# Or use the dev script to start both:
./scripts/dev_start.sh
```

## Demo Users

| Username  | Password      | Role            |
|-----------|---------------|-----------------|
| analyst1  | analyst123    | Research Analyst |
| analyst2  | analyst456    | Research Analyst |
| pm1       | pm789         | Portfolio Manager|

## Architecture

- **Frontend:** React + TypeScript (Vite)
- **Backend:** Python + FastAPI
- **Data:** CSV-backed (swappable to Snowflake/Redshift)
- **File Storage:** Local filesystem (swappable to S3)
- **Auth:** JWT in httpOnly cookies

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/auth/login` | Login |
| POST | `/auth/logout` | Logout |
| GET | `/auth/me` | Current user info |
| GET | `/api/data/` | List datasets |
| GET | `/api/data/{dataset}` | Query dataset |
| GET | `/api/data/{dataset}/{id}` | Get single record |
| GET | `/api/files/` | List files |
| GET | `/api/files/{id}/metadata` | File metadata |
| GET | `/api/files/{id}` | Download file |
