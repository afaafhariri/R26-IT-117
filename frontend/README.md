# Static Test Frontend

Single-file API test UI for the performance component.

## Run

1. Start backend services from project root:
   - `docker compose up --build -d`
2. Open a terminal in `frontend`:
   - `cd frontend`
3. Serve this folder with a simple local server:
   - `python -m http.server 8080`
4. Open:
   - `http://localhost:8080`

## Notes

- Default API base URL is `http://localhost:5004`.
- `Load Sample Payload` uses the raw Component 03-style schema; on `Submit Schedule`, the page auto-adapts it to the Component 04 backend schema.
- The page includes a sample `/schedule` payload and step-by-step API actions:
  - `/health`
  - `/schedule`
  - `/progress/spi`
  - `/progress/predict`
  - `/project/{id}/dashboard`
  - `/project/{id}/alerts`
