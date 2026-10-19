# 🧠 AI Blood Donor Matching Service

> Intelligent donor matching microservice using Multi-Criteria Decision Analysis (MCDA), built with FastAPI, Python 3.11, PostgreSQL (psycopg2/asyncpg), and Redis.

---

## 🎯 Features

- **Multi-Criteria Decision Analysis (MCDA):** Ranks candidate donors across 4 weighted factors:
  - **Distance (40%):** Haversine distance from patient to donor.
  - **Reliability (30%):** Historical response rate and verified attendance.
  - **Eligibility (20%):** Time elapsed since last donation.
  - **Response Rate (10%):** Acceptance frequency on urgent requests.
- **Privacy Protection:** Phone numbers masked in ranking outputs (`98****3210`).
- **PostgreSQL 16 & Neon Compatibility:** Reads from read-only role (`ai_service_ro`) with SSL support.
- **City Wildcard Safety:** ANSI SQL `ESCAPE '\'` protects city filtering against `%`, `_`, and `\` injection.
- **Observability:**
  - `GET /live`: Lightweight liveness probe (no DB/Redis touch, Render-safe).
  - `GET /health`: Deep status check exposing `version` and `commit` SHA.
  - `GET /health/ready`: Readiness probe checking database connectivity.

---

## 🛠️ Stack & Dependencies

- **Python:** 3.11
- **Framework:** FastAPI 0.115+, Starlette, Uvicorn
- **Database Driver:** SQLAlchemy 2.0+, psycopg2-binary 2.9+, asyncpg 0.29+
- **Cache:** Redis 7
- **Validation:** Pydantic v2

---

## ⚙️ Environment Variables

| Variable | Required in Prod | Default | Description |
|:---|:---:|:---|:---|
| `DB_URL` | **YES** | `None` | PostgreSQL connection URL (e.g. `postgresql+psycopg2://ai_service_ro:pass@ep-xyz.neon.tech/blood_donor_db?sslmode=require`). |
| `REDIS_HOST` | No | `localhost` | Redis server hostname. |
| `REDIS_PORT` | No | `6379` | Redis server port. |
| `AI_SERVICE_API_KEY` | **YES** | `None` | Shared API key required on matching endpoints (minimum 32 characters in prod). |
| `GIT_SHA` | No | `unknown` | Commit SHA injected at build/deployment time for `/health` traceability. |
| `ENVIRONMENT` | No | `development` | `development`, `staging`, or `production`. |

---

## 🚀 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server locally
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
pytest
```
