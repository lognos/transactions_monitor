.PHONY: backend frontend

backend:
	cd backend && uv run uvicorn app.server.main:app --reload --port 8010

frontend:
	cd frontend && npm run dev
