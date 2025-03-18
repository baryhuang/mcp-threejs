# --------
# Builder stage
# --------
FROM python:3.11-slim AS builder

# Install build tools and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libc6-dev \
    libffi-dev \
    libpq-dev \
    make \
    && rm -rf /var/lib/apt/lists/*

# Set working directory for builder
WORKDIR /app

# Copy the entire project first
COPY . /app/

# Upgrade pip and build wheels for all dependencies
RUN pip install --upgrade pip \
    && mkdir /wheels \
    && pip wheel --wheel-dir=/wheels -r requirements.txt

# --------
# Final runtime stage
# --------
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the entire project
COPY . /app/

# Copy the wheels built in the builder stage
COPY --from=builder /wheels /wheels

# Install Python dependencies from the local wheel cache
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# Set environment variables
ENV PYTHONPATH=/app/src
# Note: OAuth2 credentials should be passed at runtime:
# Example: docker run -e SKETCHFAB_ACCESS_TOKEN=token -e SKETCHFAB_REFRESH_TOKEN=refresh_token -e SKETCHFAB_CLIENT_ID=id -e SKETCHFAB_CLIENT_SECRET=secret mcp-server-threejs

# Expose port
EXPOSE 8000

# Run the server with OAuth2 credentials passed as arguments
ENTRYPOINT ["python", "src/mcp_server_threejs/server.py", \
            "--sketchfab_access_token=${SKETCHFAB_ACCESS_TOKEN}", \
            "--sketchfab_refresh_token=${SKETCHFAB_REFRESH_TOKEN}", \
            "--sketchfab_client_id=${SKETCHFAB_CLIENT_ID}", \
            "--sketchfab_client_secret=${SKETCHFAB_CLIENT_SECRET}"]
