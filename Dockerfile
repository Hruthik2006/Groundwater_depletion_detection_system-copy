# AI-Driven Groundwater Depletion Prediction and Sustainable Extraction
# Optimization System — one-command container build.
#
#   docker compose up --build
#
# then open http://localhost:8000 (dashboard) and http://localhost:8000/admin
#
# The default mode is the offline synthetic benchmark. For live Earth
# Engine mode, authenticate on the host first (earthengine authenticate)
# and start with:  GW_MODE=realtime docker compose up --build
# (compose mounts your ~/.config/earthengine credentials and passes
# GEE_PROJECT_ID through; see docker-compose.yml).
FROM python:3.12-slim

WORKDIR /app

# System libraries some wheels need at runtime (torch / osqp / scipy).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# GW_MODE selects the data channel: synthetic (default) | realtime | dwlr
ENV GW_MODE=synthetic
CMD ["sh", "-c", "python main.py ${GW_MODE}"]
