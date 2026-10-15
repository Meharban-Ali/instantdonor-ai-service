# Blood Donor AI Service

High-performance, secure FastAPI microservice providing intelligent donor matching and blood demand forecasting for the Blood Donor Network platform.

---

## 1. Donor Matching Architecture: Deterministic Rule-Based MCDA

> **Architectural Note:**  
> The donor matching engine utilizes **100% deterministic rule-based Multi-Criteria Decision Analysis (MCDA)** implemented in `utils/scoring.py`.  
> There is **no binary ML model file (`.pkl` / `.joblib`)** and **no untrusted deserialization**. All scoring algorithms are fully deterministic, auditable, explainable, and testable without external model dependencies.

### Scoring Formula
The composite donor score $S \in [0.0, 1.0]$ is computed as:
$$S = (0.35 \times S_{\text{dist}}) + (0.30 \times S_{\text{compat}}) + (0.20 \times S_{\text{rel}}) + (0.15 \times S_{\text{urg}})$$

Where:
- **$S_{\text{dist}}$ (Distance Score):** Proximity computed using the Great-Circle Haversine formula over geographic coordinates $(\text{lat}, \text{lng})$. Normalizes distance relative to the requested search radius.
- **$S_{\text{compat}}$ (Compatibility Score):** Exact ABO & Rh(D) compatibility matrix. Exact match = `1.0`, compatible universal donor (e.g. O- to A+) = `0.8`, incompatible = `0.0`.
- **$S_{\text{rel}}$ (Reliability Score):** Normalized donor historical reliability and attendance record (scale `0.0 - 1.0`).
- **$S_{\text{urg}}$ (Urgency Multiplier):** Dynamic prioritization depending on `CRITICAL`, `URGENT`, or `NORMAL` request levels.

---

## 2. API Endpoints

| Endpoint | Method | Auth Required | Description |
| :--- | :---: | :---: | :--- |
| `/health` | `GET` | No | Component health check (`database`, `redis`). Returns 200 (healthy/degraded) or 503 (unhealthy). |
| `/api/v1/match-donors` | `POST` | `X-API-KEY` | Matches and ranks compatible donors using deterministic MCDA. |
| `/api/v1/predict-demand` | `POST` | `X-API-KEY` | Forecasts blood unit demand using statistical trend analysis over historical blood requests. |

---

## 3. Security & Hardening Controls
- **API Key Authentication:** Constant-time header verification (`secrets.compare_digest`) via `X-API-KEY`.
- **Zero Deserialization Attack Surface:** Scikit-learn and joblib pickle loading have been completely removed.
- **Data Privacy & PII Protection:** The service does NOT store or expose donor names, phone numbers, email addresses, or exact geo-coordinates. Matches are identified purely by anonymous `donor_id` and `distance_km`.
- **Least-Privilege Database Access:** Read-only database user (`ai_service_ro`) with column-level `SELECT` grants only.
- **Non-Root Docker Execution:** Container runs under unprivileged user `appuser:appgroup` (UID/GID 10001).
