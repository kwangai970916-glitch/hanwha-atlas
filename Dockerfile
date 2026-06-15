# syntax=docker/dockerfile:1
# ============================================================
#  단일 서비스 배포 (Railway/Render/Fly 공통)
#  1) node 스테이지에서 React/Vite 프론트를 빌드(frontend/dist)
#  2) python 스테이지에서 FastAPI 가 API + 빌드된 프론트를 같은 오리진에서 서빙
#  → URL 1개 · CORS 불필요 · VITE_API_BASE 불필요
#  위원회는 벤더드 TradingAgents 가 없으므로 네이티브 엔진(in-process)으로 동작한다.
#  브리핑 PNG 는 Playwright 미설치 시 자동 생략(인터랙티브 카드는 정상).
# ============================================================

# ---------- Stage 1: build frontend ----------
FROM node:20-bookworm-slim AS frontend
WORKDIR /fe
COPY frontend/package.json ./
COPY frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# 라이브(비오프라인) 모드로 빌드 — VITE_OFFLINE 미설정 → 실제 API 호출
RUN npm run build

# ---------- Stage 2: python runtime ----------
FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    ATLAS_PNL_MOCK=1

# 의존성 레이어 먼저 (캐시 최적화)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 시황 리포트 PNG 렌더용 헤드리스 Chromium + 한글 폰트.
# best-effort: 설치 실패해도 빌드는 진행되고(|| true) PNG 만 생략된다(인터랙티브 카드는 정상).
RUN (python -m playwright install --with-deps chromium \
     || python -m playwright install chromium || true) \
 && (apt-get update \
     && apt-get install -y --no-install-recommends fonts-noto-cjk fonts-nanum \
     && rm -rf /var/lib/apt/lists/* || true)

# 백엔드 소스 + 빌드된 프론트 산출물
COPY backend/ backend/
COPY --from=frontend /fe/dist frontend/dist

EXPOSE 8000
# Railway/Render 가 주입하는 $PORT 를 사용, 없으면 8000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
