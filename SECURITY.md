# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0.0 | :x:                |

## Reporting a Vulnerability

Please report potential security issues directly to:
- **Email:** `security@blooddonor.com` or `meharbanali7900@gmail.com`

Please include:
1. Affected endpoint or function.
2. Reproduction steps and attack scenario.
3. Relevant logs or payloads.

Acknowledgements will be sent within 24–48 hours.

## Policy
- Service runs with least-privilege database user `ai_service_ro` (read-only grants on necessary tables, no access to user passwords/credentials).
- Sensitive user data (phone numbers) is masked in matching outputs.
- API key authentication is strictly required on all non-health routes.
