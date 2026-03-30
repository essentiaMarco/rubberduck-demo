.PHONY: setup dev dev-backend dev-frontend test lint build clean docker-up docker-down

# ─── Setup ─────────────────────────────────────────────────
setup:
	@echo "Setting up Rubberduck..."
	cp -n .env.example .env || true
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install
	python -m spacy download en_core_web_sm
	@echo "Setup complete."

# ─── Development ───────────────────────────────────────────
dev:
	@echo "Starting backend and frontend..."
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && uvicorn src.rubberduck.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# ─── Testing ───────────────────────────────────────────────
test:
	cd backend && python -m pytest tests/ -v --tb=short

test-cov:
	cd backend && python -m pytest tests/ -v --cov=src/rubberduck --cov-report=html

# ─── Linting ───────────────────────────────────────────────
lint:
	cd backend && ruff check src/ tests/
	cd backend && ruff format --check src/ tests/

format:
	cd backend && ruff format src/ tests/

# ─── Build ─────────────────────────────────────────────────
build:
	cd frontend && npm run build

# ─── Docker ────────────────────────────────────────────────
docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

# ─── Clean ─────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.ruff_cache frontend/.next frontend/node_modules/.cache
