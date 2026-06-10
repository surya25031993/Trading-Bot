# Dockerfile for Hugging Face Spaces (Docker SDK).
# Free 16 GB RAM / 2 vCPU — comfortably runs xgboost + scikit-learn + scipy.

FROM python:3.11-slim

# System deps (curl_cffi needs libffi/openssl; lxml needs libxml; etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Yarn (Expo build needs it; we use it once at image build time)
RUN npm install -g yarn serve

# ---- Backend python deps ----
COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/vendor /app/backend/vendor
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
 && pip install --no-cache-dir --no-deps "emergentintegrations==0.2.0"

# ---- Frontend build (we ship the static bundle inside the image) ----
COPY frontend/package.json frontend/yarn.lock* /app/frontend/
WORKDIR /app/frontend
RUN yarn install --frozen-lockfile || yarn install

COPY frontend /app/frontend
# EXPO_PUBLIC_BACKEND_URL is empty so all /api/* calls go to the same origin
# that's serving the frontend (single-container deployment).
ENV EXPO_PUBLIC_BACKEND_URL=""
RUN yarn build:web

# ---- Backend source ----
COPY backend /app/backend
WORKDIR /app/backend

# HF Spaces injects PORT=7860
ENV PORT=7860
ENV SERVE_FRONTEND=1
ENV PYTHONUNBUFFERED=1

EXPOSE 7860

# Run FastAPI; serves /api/* AND the React Native Web bundle from /app/frontend/dist
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
