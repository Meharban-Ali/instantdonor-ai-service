# Cloud Deployment Guide: Blood Donor Network
**Target Stack**: Vercel (Frontend Vite React SPA) + Render (Spring Boot 4.1.1 Backend & FastAPI AI Service) + Neon Serverless PostgreSQL 16 (PgBouncer Pooled + TLS) + Render Key Value (Redis 7)

---

## 1. Architecture Overview

```
                      ┌──────────────────────────────────────────┐
                      │          Browser / Mobile Web            │
                      └─────────────────────┬────────────────────┘
                                            │
                                            ▼
                      ┌──────────────────────────────────────────┐
                      │              Vercel Edge                 │
                      │       https://instantdonor.online        │
                      │       (Vite React SPA + vercel.json)     │
                      └─────────────────────┬────────────────────┘
                                            │ API Requests (CORS / Bearer)
                                            ▼
                      ┌──────────────────────────────────────────┐
                      │             Render Web Service           │
                      │     https://api.instantdonor.online      │
                      │     (Spring Boot 4.1.1 / Java 21)        │
                      └───────┬──────────────────────────┬───────┘
                              │                          │
        Internal HTTP + X-API-KEY                        │ JDBC TLS (sslmode=require)
                              ▼                          ▼
               ┌────────────────────────┐      ┌────────────────────────┐
               │   Render Web Service   │      │  Neon PostgreSQL 16    │
               │   FastAPI AI Service   │      │  (Serverless Pooled    │
               │   (Python 3.11 Docker) │      │   PgBouncer Endpoint)  │
               └──────────────┬─────────┘      └────────────────────────┘
                              │                          ▲
                              │ AsyncPG / Psycopg2       │
                              │ Read-Only (ai_service_ro)│
                              ▼                          │
               ┌────────────────────────┐                │
               │   Render Key Value     │────────────────┘
               │  (Redis 7 Token Black- │
               │   list & Rate Limit)   │
               └────────────────────────┘
```

---

## 2. Infrastructure Requirements & Pre-Deployment Checklist

### A. Neon Serverless PostgreSQL 16 Database
- **Provider**: Neon (https://neon.tech) — Serverless Postgres with automatic scale-to-zero.
- **Connection Requirements**:
  - Requires TLSv1.3 (`sslmode=require`).
  - **Connection URL Formats**:
    - **Backend Runtime (Pooled via PgBouncer)**:
      ```
      jdbc:postgresql://<ep-xxxx>-pooler.ap-southeast-1.aws.neon.tech:5432/neondb?sslmode=require&prepareThreshold=0
      ```
      *Note on `prepareThreshold=0`*: Mandatory when connecting through Neon's PgBouncer pooled endpoint in transaction mode. Disables server-side named prepared statement caching which causes `prepared statement does not exist` errors across connection pooling.
    - **Flyway Migrations (Direct Endpoint)**:
      ```
      FLYWAY_DB_URL=jdbc:postgresql://<ep-xxxx>.ap-southeast-1.aws.neon.tech:5432/neondb?sslmode=require
      ```
      *Direct endpoint* must be used for DDL migrations (`V1`, `V2`, `V3`) to execute transactional DDL without PgBouncer statement interception.
    - **AI Service Driver URL (Read-Only)**:
      ```
      DB_URL=postgresql+psycopg2://ai_service_ro:<password>@<ep-xxxx>-pooler.ap-southeast-1.aws.neon.tech:5432/neondb?sslmode=require
      ```
  - **Hikari Connection Pool Constraints**:
    Configure Backend with `DB_POOL_MAX=10` and `DB_POOL_MIN_IDLE=2` to avoid exhausting Neon pooled connections during scale-to-zero wakeups.
  - **Least Privilege Roles Initialization (`scripts/neon_roles.sql`)**:
    Run `scripts/neon_roles.sql` as superuser (`postgres` or `neondb_owner`) prior to application start.
    - `app_user`: Dedicated application role with DML (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) on operational tables.
    - `ai_service_ro`: Strict read-only service role with column-level grants on donor availability and location data; explicitly denied access to user passwords, phones, and email PII.

### B. Redis Instance (Render Key Value vs Managed Redis)
- **Render Key Value (Internal vs External Connection)**:
  - **Same Render Region / Internal Service**:
    - Use Render Internal Redis URL: `redis://red-xxxx:6379`.
    - No password and NO TLS (`REDIS_SSL=false`).
  - **Cross-Region or External Clients**:
    - Use Render External Redis URL: `rediss://default:<password>@oregon-keyvalue.render.com:6379`.
    - TLS enabled (`REDIS_SSL=true`).
- **Resilience Policy**:
  - `JwtAuthFilter` enforces a fail-closed policy with a 3000ms Redis timeout. If Redis is unreachable, authenticated requests safely fail with HTTP 503 rather than accepting unverified tokens.

### C. Email Service (Resend SMTP)
- **Render Free Tier Restriction**: Render blocks outbound connections on standard SMTP ports `25`, `465`, and `587` on free web services to prevent spam.
- **Solution**: Resend officially supports non-standard submission port `2587` (with STARTTLS) and port `2465` (with implicit TLS).
- **Configuration**:
  - `MAIL_HOST=smtp.resend.com`
  - `MAIL_PORT=2587`
  - `MAIL_USERNAME=resend`
  - `MAIL_PASSWORD=re_your_resend_api_key`
  - `MAIL_FROM_ADDRESS=noreply@instantdonor.online`
  - `MAIL_FROM_NAME="AI Blood Donor Network"`

---

## 3. Step-by-Step Deployment Procedure

### Step 1: Deploy AI Service on Render
1. In the Render Dashboard, select **New +** > **Web Service**.
2. Connect your Git repository (`ai-service` repository).
3. Select **Docker** environment and **Free** instance type.
4. Set **Health Check Path** to `/live` (lightweight, avoids waking DB on health polls).
5. Configure Environment Variables (see Section 4 Table).
6. Note the deployed public URL (e.g. `https://blood-donor-ai-service.onrender.com`).

### Step 2: Deploy Spring Boot Backend on Render
1. In the Render Dashboard, select **New +** > **Web Service**.
2. Connect your Git repository (`Backend` repository).
3. Select **Docker** environment and **Free** instance type (512MB RAM).
4. **Health Check Path**: `/actuator/health/liveness` (lightweight liveness group: ping + diskSpace).
5. **JVM Memory Optimization Flags** (already baked into `Dockerfile`):
   ```
   JAVA_OPTS="-XX:+UseContainerSupport -XX:MaxRAMPercentage=55.0 -XX:InitialRAMPercentage=40.0 -Xss512k -XX:+TieredCompilation -XX:TieredStopAtLevel=1 -XX:+ExitOnOutOfMemoryError"
   ```
6. Add custom domain `api.instantdonor.online` in Render service settings and add the CNAME record in your DNS registrar pointing to your Render service address.
7. Configure Environment Variables (see Section 4 Table).

### Step 3: Deploy Frontend on Vercel
1. In Vercel, select **Add New Project** and import the `Frontend` repository.
2. Select **Vite** Framework Preset.
3. Configure Build Settings:
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Set Environment Variable:
   - `VITE_API_BASE_URL`: `https://api.instantdonor.online/api`
5. Deploy. Vercel automatically applies [`vercel.json`](file:///vercel.json) rules:
   - Single Page Application (SPA) catch-all rewrite to `/index.html`.
   - Security headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
   - Content Security Policy: `connect-src 'self' https://api.instantdonor.online`.
   - Private indexing protection: `X-Robots-Tag: noindex, nofollow`.
6. Attach Custom Domain `instantdonor.online` and `www.instantdonor.online` in Vercel settings and configure DNS A/CNAME records.

---

## 4. Environment Variables Reference Tables

### Service 1: Spring Boot Backend (`api.instantdonor.online`)

| Variable | Required | Source / Provider | Description / Example |
| :--- | :---: | :--- | :--- |
| `SPRING_PROFILES_ACTIVE` | Yes | App Config | Must be `prod` |
| `PORT` | Auto | Render | Automatically assigned by Render (e.g. `10000`) |
| `DB_URL` | Yes | Neon Postgres | `jdbc:postgresql://<ep-xxxx>-pooler.ap-southeast-1.aws.neon.tech:5432/neondb?sslmode=require&prepareThreshold=0` |
| `FLYWAY_DB_URL` | Optional | Neon Direct | `jdbc:postgresql://<ep-xxxx>.ap-southeast-1.aws.neon.tech:5432/neondb?sslmode=require` (for direct DDL migrations) |
| `DB_USERNAME` | Yes | Neon Role | `app_user` (or `neondb_owner`) |
| `DB_PASSWORD` | Yes | Neon Role | Database user password |
| `DB_POOL_MAX` | Optional | Performance Tuning | Max Hikari connections (default `10`) |
| `DB_POOL_MIN_IDLE` | Optional | Performance Tuning | Min idle connections (default `0` for Neon scale-to-zero) |
| `REDIS_HOST` | Yes* | Redis Provider | Redis hostname (e.g. `red-xxxx.render.com`) |
| `REDIS_PORT` | Yes* | Redis Provider | Redis port (`6379`) |
| `REDIS_PASSWORD` | Optional | Redis Provider | Redis password (omit if Render internal Redis) |
| `REDIS_SSL` | Yes | Redis Provider | `false` for Render internal (`redis://`), `true` for external/Upstash (`rediss://`) |
| `REDIS_URL` | Optional | Redis Provider | Full URI format (`redis://...` internal or `rediss://...` external) |
| `ADMIN_EMAIL` | Yes* | App Config | Required in production when ADMIN_PASSWORD is set |
| `ADMIN_PASSWORD` | Optional | App Config | Default admin account password |
| `JWT_SECRET` | Yes | User Generated | Cryptographically secure string, min 48 chars (`openssl rand -hex 32`) |
| `JWT_EXPIRATION` | Optional | App Config | Access token validity in ms (`86400000` = 24h) |
| `JWT_REFRESH_EXPIRATION` | Optional | App Config | Refresh token validity in ms (`604800000` = 7d) |
| `FRONTEND_URL` | Yes | App Config | `https://instantdonor.online` |
| `CORS_ALLOWED_ORIGINS` | Yes | App Config | `https://instantdonor.online,https://www.instantdonor.online` |
| `AI_SERVICE_URL` | Yes | Render AI URL | `https://blood-donor-ai-service.onrender.com` |
| `AI_SERVICE_API_KEY` | Yes | User Generated | Shared secret matching `API_KEY` in AI service |
| `MAIL_HOST` | Optional | Resend | `smtp.resend.com` |
| `MAIL_PORT` | Optional | Resend | `2587` (bypasses Render free SMTP block) |
| `MAIL_USERNAME` | Optional | Resend | `resend` |
| `MAIL_PASSWORD` | Optional | Resend | Resend API Key (`re_...`) |
| `MAIL_FROM_ADDRESS` | Optional | App Config | `noreply@instantdonor.online` |
| `MAIL_FROM_NAME` | Optional | App Config | `AI Blood Donor Network` |
| `MAIL_REPLY_TO` | Optional | App Config | `support@instantdonor.online` |
| `TWILIO_ACCOUNT_SID` | Optional | Twilio | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Optional | Twilio | Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | Optional | Twilio | Twilio Phone Number |
| `TWILIO_MESSAGING_SERVICE_SID`| Optional | Twilio | Messaging Service SID |

### Service 2: FastAPI AI Service (`ai-service`)

| Variable | Required | Source / Provider | Description / Example |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | Yes | App Config | Must be `production` |
| `DEBUG` | Yes | App Config | Must be `false` (enforced at startup) |
| `PORT` | Auto | Render | Automatically assigned by Render |
| `API_KEY` | Yes | User Generated | Secret key for `X-API-KEY` verification (matches Backend) |
| `DB_URL` | Yes | Neon Postgres | `postgresql+psycopg2://ai_service_ro:pass@host:5432/neondb?sslmode=require` |
| `DB_POOL_SIZE` | Optional | App Config | Default `5` |
| `REDIS_HOST` | Yes | Redis Provider | Redis hostname |
| `REDIS_PORT` | Yes | Redis Provider | Redis port (`6379`) |
| `REDIS_PASSWORD` | Optional | Redis Provider | Redis auth password |
| `REDIS_SSL` | Yes | Redis Provider | `false` for Render internal, `true` for external/Upstash |
| `CORS_ORIGINS` | Optional | App Config | Empty or `["https://api.instantdonor.online"]` |

### Service 3: Frontend (`instantdonor.online`)

| Variable | Required | Source / Provider | Description / Example |
| :--- | :---: | :--- | :--- |
| `VITE_API_BASE_URL` | Yes | Build-Time (Vercel) | `https://api.instantdonor.online/api` |

---

## 5. Cold-Start & Free Tier Operational Notes

### A. Cold Start Timing by Component
| Service / Component | Typical Cold Start Time | Inactivity Sleep Trigger |
| :--- | :--- | :--- |
| **Backend (Spring Boot 4.1.1)** | 25–35 seconds | 15 minutes inactivity on Render free tier |
| **Neon PostgreSQL 16** | 1–3 seconds | 5 minutes inactivity (Serverless compute scale-to-zero) |
| **AI Service (FastAPI)** | 3–5 seconds | 15 minutes inactivity on Render free tier |
| **Render Key Value (Redis 7)** | Always warm | Dedicated managed instance |

### B. Mitigation Strategies Implemented
1. **Frontend Cold-Start Module (`coldStartRetry.ts` & `ColdStartBanner.tsx`)**:
   - Automatically intercepts idempotent `GET` API requests on network dropouts or HTTP `502`/`503`/`504`.
   - Executes up to 3 automatic retries with exponential backoff (2s, 4s, 8s).
   - If a request takes > 5 seconds, surfaces a friendly, non-blocking notification banner: *"Server is waking up (free hosting tier), this may take 30–60 seconds. Please wait..."*.
   - Decoupled from existing auth token refresh mechanisms to guarantee zero side-effects.

2. **Neon Scale-to-Zero Connection Preservation**:
   - HikariCP pool tuned with `minimum-idle=0`, `idle-timeout=300000ms`, `keepalive-time=0ms`, and `max-lifetime=1800000ms`. Connections gracefully drain when idle so Neon compute can scale down to zero without holding open TCP sockets.
   - `prepareThreshold=0` prevents prepared statement caching conflicts across PgBouncer transaction pooling.

3. **Lightweight Health Check Probes**:
   - Backend configured with `healthCheckPath: /actuator/health/liveness` (checks only `ping` and `diskSpace`), ensuring Render's routine health probes never artificially prevent Neon or Redis from idling.
   - AI Service configured with `healthCheckPath: /live` (lightweight process health check).

4. **AI Matching Fallback & Fault Tolerance**:
   - If the AI service is cold or offline when a blood request is dispatched, Backend's `AiDonorMatchingStrategy` retries 3 times before automatically falling back to deterministic rule-based database matching.
   - Tracks fallback frequency via Micrometer counter metric `ai.matching.fallback`.
   - Emergency notification workflows never fail or drop requests due to external service latency.
