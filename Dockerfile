FROM python:3.11-slim

WORKDIR /app

# Create a non-privileged user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -d /app -s /sbin/nologin appuser

# Upgrade build tools (pip, setuptools, wheel) to resolve CVEs
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements file
COPY requirements.txt .

# Install runtime dependencies only
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Set ownership of app directory to appuser
RUN chown -R appuser:appgroup /app

# Set user local bin path
ENV PATH="/app/.local/bin:${PATH}"

# Switch to non-privileged user
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
