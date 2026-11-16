.PHONY: ajuda instalar seed api web testes testes-pg e2e docker lint limpar

ajuda:
	@echo "Monitor Tributário — comandos disponíveis"
	@echo "  make instalar   instala dependências de backend e frontend"
	@echo "  make seed       recria o banco com a massa demonstrativa"
	@echo "  make api        sobe a API em http://localhost:8000"
	@echo "  make web        sobe o frontend em http://localhost:5173"
	@echo "  make testes     roda a suíte pytest (SQLite)"
	@echo "  make testes-pg  roda a suíte pytest contra PostgreSQL"
	@echo "  make e2e        roda o teste de interface (Playwright)"
	@echo "  make docker     sobe tudo com docker compose"

instalar:
	cd backend && python3 -m pip install -r requirements-dev.txt
	cd frontend && npm install

seed:
	cd backend && MT_SCHEDULER_ENABLED=false python3 -m scripts.seed --reset

api:
	cd backend && python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd frontend && npm run dev

testes:
	cd backend && python3 -m pytest tests/ -v

testes-pg:
	cd backend && MT_DATABASE_URL="postgresql+psycopg://monitor@127.0.0.1:5432/monitor_test" \
		python3 -m pytest tests/ -v

e2e:
	node e2e/fluxo-ui.mjs http://127.0.0.1:8000

docker:
	docker compose up --build

lint:
	cd backend && python3 -m ruff check app scripts tests || true
	cd frontend && npx tsc -b

limpar:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf backend/monitor_tributario.db e2e/capturas
