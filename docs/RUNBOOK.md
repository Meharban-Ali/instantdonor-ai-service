# Operational Runbook: AI Donor Matching Service

## 1. Overview
- **Service:** FastAPI / Python 3.11 with Uvicorn
- **Database:** PostgreSQL 16 read-only role (`ai_service_ro`) with SSL
- **Cache:** Redis 7
- **Scoring:** Multi-Criteria Decision Analysis (MCDA) rule-based scoring (distance 40%, reliability 30%, eligibility 20%, response rate 10%)

## 2. Health Endpoints
- **Liveness:** `GET /live` (Lightweight alive check, no DB or Redis queries, used by Render health checks)
- **Deep Health:** `GET /health` (Checks DB and Redis connectivity; exposes `app_version` and `commit` SHA)
- **Readiness:** `GET /health/ready` (Returns 200 if DB is connected, 503 if DB is down)

## 3. Incident Playbook
### A. 401 Unauthorized
Verify `AI_SERVICE_API_KEY` header matches between Backend and AI Service.

### B. Database Query Timeouts
Check PostgreSQL SSL configuration and connection parameters:
- `DB_URL="postgresql+psycopg2://ai_service_ro:***@ep-***.neon.tech/blood_donor_db?sslmode=require"`
- Check table grants: `ai_service_ro` must have SELECT grants on `donor_profiles`, `blood_requests`, `users`.

### C. Scaling
Memory profile is low (~120–180MB). Fits comfortably in Render 512MB free/starter tier.
