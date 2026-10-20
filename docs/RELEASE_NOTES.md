# Release Notes - Blood Donor Network (release/final)

## 1. Release Overview
This document summarizes the release readiness, architectural stack, configuration matrix, and known operational characteristics for the **AI Blood Donor Network** production release.

---

## 2. Gate Verification Summary

| Gate | Status | Description | Verification Method |
| :--- | :---: | :--- | :--- |
| **Security Configuration** | **PASS** | Strict Spring Security filter chain; anonymous requests to protected endpoints return 401; public endpoints return 200/404; Actuator locked down | Integration tests & automated curl matrix |
| **JWT & Rate Limiting** | **PASS** | Ephemeral HMAC-SHA256 JWT validation, IP-based sliding window rate limiter fail-closed on Redis outage | Vitest, Surefire & MockMvc test suites |
| **Database Migrations** | **PASS** | Flyway V1 & V2 baseline migrations, lower-case indexed email lookups, idempotent execution | Flyway validate-on-migrate against PostgreSQL 16 |
| **Input Sanitization** | **PASS** | LIKE wildcard escaping (`%`, `_`, `\`) across backend and AI search queries | Unit & integration tests |
| **Memory & Resource Tuning** | **PASS** | 512MB container memory ceiling, graceful shutdown (15s), Hikari connection pool tuned for serverless | Docker memory limits & load simulation |
| **Health Probes** | **PASS** | Deep `/actuator/health` and lightweight `/actuator/health/liveness` probes; AI service `/live` route | Actuator HTTP assertions & Render config |
| **Frontend Cold-Start UX** | **PASS** | Non-blocking exponential backoff retry on 502/503/504 with cold-start UI alert banner | Vitest component & service tests |
| **Static Assets & CSP** | **PASS** | Strict Content Security Policy (`default-src 'self'`), zero unsafe-inline in production | Playwright automated E2E audit |
| **Data Privacy & Masking** | **PASS** | Phone masking (`XX****XXXX`) across public donor search; explicit donor consent tracking | Vitest utils & backend DTO assertions |
| **Secret Sanitization** | **PASS** | Zero tracked secrets, `.gitignore` exclusion of credentials, sanitized sample configurations | Gitleaks scan & regex audit |

---

## 3. Technology Stack & Effective Versions

### Backend (Java / Spring Boot)
- **Framework**: Spring Boot 3.3.4
- **Runtime**: Java 21 LTS (Eclipse Temurin)
- **ORM / Persistence**: Hibernate 6.5.3.Final / Spring Data JPA
- **Servlet Container**: Apache Tomcat 10.1.30
- **Database Driver**: PostgreSQL JDBC Driver 42.7.4
- **Schema Migration**: Flyway Community 10.10.0
- **Connection Pool**: HikariCP 5.1.0

### Frontend (SPA / React)
- **Library**: React 18.3.1
- **Language**: TypeScript 5.5.3
- **Build Tool**: Vite 5.4.2
- **State Management**: Zustand 4.5.5
- **Routing**: React Router DOM 6.26.1
- **Styling**: TailwindCSS 3.4.11
- **Testing**: Vitest 4.1.11 & Playwright 1.47.0

### AI & Matching Microservice (Python)
- **Runtime**: Python 3.11 Slim
- **Framework**: FastAPI 0.115.0 / Starlette 0.38.6
- **Server**: Uvicorn 0.30.6
- **Database Client**: Psycopg2-binary 2.9.9 / SQLAlchemy 2.0.35
- **Cache Client**: Redis-py 5.0.8
- **Testing**: Pytest 8.3.3

---

## 4. Environment Variable Matrix

> **Note**: No secrets, production keys, or local file system paths are included here. All secret values must be provisioned via secret managers (e.g., Render Dashboard, Vercel Environment Variables).

| Variable Name | Target Service | Format / Type | Generator / Source | Required in Prod | Purpose |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `SPRING_PROFILES_ACTIVE` | Backend | String (`prod`) | Deployment Manifest | Yes | Activates production configuration |
| `SPRING_DATASOURCE_URL` | Backend | JDBC URL (`jdbc:postgresql://<HOST>:<PORT>/<DB>?sslmode=require`) | Cloud DB Provider (Neon / RDS) | Yes | Primary PostgreSQL JDBC connection |
| `SPRING_DATASOURCE_USERNAME` | Backend | String (identifier) | Cloud DB Provider | Yes | Application database user |
| `SPRING_DATASOURCE_PASSWORD` | Backend | String (credential) | Cloud DB Provider | Yes | Application database password |
| `FLYWAY_URL` | Backend | JDBC URL | Cloud DB Provider | Optional | Flyway migration connection if separate owner |
| `FLYWAY_USER` | Backend | String (identifier) | Cloud DB Provider | Optional | Flyway migration admin user |
| `FLYWAY_PASSWORD` | Backend | String (credential) | Cloud DB Provider | Optional | Flyway migration admin password |
| `SPRING_DATA_REDIS_HOST` | Backend | Hostname / IP | Cloud Cache Provider (Upstash / Redis) | Yes | Redis host for rate limiting |
| `SPRING_DATA_REDIS_PORT` | Backend | Integer (`6379`) | Cloud Cache Provider | Yes | Redis port |
| `SPRING_DATA_REDIS_PASSWORD` | Backend | String (credential) | Cloud Cache Provider | Yes | Redis authentication password |
| `JWT_SECRET` | Backend | 64+ char base64 string | `openssl rand -base64 64` | Yes | Signing key for HMAC-SHA256 JWT tokens |
| `JWT_EXPIRATION_MS` | Backend | Milliseconds (Integer) | Configuration Default (`900000`) | No | Access token validity (default: 15 min) |
| `JWT_REFRESH_EXPIRATION_MS` | Backend | Milliseconds (Integer) | Configuration Default (`604800000`) | No | Refresh token validity (default: 7 days) |
| `ADMIN_EMAIL` | Backend | Valid Email Address | System Operator | Yes | Initial system administrator account email |
| `ADMIN_PASSWORD` | Backend | Strong Password String | Secure Password Generator | Yes | Initial system administrator account password |
| `AI_SERVICE_URL` | Backend | HTTP URL (`https://<HOST>`) | Cloud Service Provider (Render) | Yes | Endpoint for AI donor ranking service |
| `CORS_ALLOWED_ORIGINS` | Backend | Comma-delimited URLs | Cloud Hosting Provider (Vercel) | Yes | Allowed origins for cross-origin browser requests |
| `VITE_API_BASE_URL` | Frontend | HTTP/HTTPS URL (`https://<HOST>/api`) | Build Configuration / Vercel Env | Yes | Base URL for REST API calls |
| `DATABASE_URL` | AI Service | PostgreSQL URL (`postgresql://<USER>:<PASS>@<HOST>/<DB>`) | Cloud DB Provider | Yes | Direct PostgreSQL connection for AI matching |
| `REDIS_URL` | AI Service | Redis URL (`redis://:<PASS>@<HOST>:<PORT>/0`) | Cloud Cache Provider | Yes | Redis connection for cache & rate limiting |
| `PORT` | All Services | Integer (`8080`, `8000`, `5173`) | Cloud Platform (`$PORT`) | Yes | HTTP listening port bound by platform |

---

## 5. Operational Characteristics & Known Limitations

1. **Free-Tier Cold Starts**:
   - On serverless/free cloud hosting (Render), backend and AI services scale to zero after inactivity.
   - Initial cold-start latency can range between 20 to 50 seconds.
   - **Mitigation**: The frontend includes a dedicated cold-start retry interceptor that retries idempotent GET requests at 2s, 4s, and 8s intervals and displays an informative notification banner after 5s of waiting.

2. **Serverless Database Connection Suspension**:
   - Neon PostgreSQL suspends compute instances after inactivity.
   - **Mitigation**: HikariCP is configured with `minimum-idle: 0`, `keepaliveTime: 0`, and `maxLifetime: 600000` (10 minutes) to cleanly let connections close and avoid stale socket errors upon wake-up.

3. **Graceful Degradation of AI Scoring**:
   - If the AI microservice is unavailable or encountering rate limits, the backend automatically falls back to deterministic geospatial search (Haversine formula + blood type compatibility matrix) without disrupting urgent donor requests.

4. **Security & Actuator Exposure**:
   - In production profile, Actuator `/actuator/env`, `/actuator/beans`, and `/actuator/configprops` are strictly disabled. Only `/actuator/health` and `/actuator/info` (sanitized build & git metadata only) are publicly accessible.
