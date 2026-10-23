# Kayange Clinic Management System

Flask + SQLite hospital management system. Neon Postgres is the persistent store:
SQLite runs locally / in /tmp on Vercel, and is synced to and restored from Neon.

## Configuration
The only database setting is `NEON_DATABASE_URL` (falls back to `DATABASE_URL`), read in `config.py`.
See `.env.example`. Use Neon's pooled connection string.

| Where it runs | Where to set it |
|---|---|
| Vercel | Project > Settings > Environment Variables (Production), then Redeploy |
| Fly.io | `fly secrets set NEON_DATABASE_URL="..." SECRET_KEY="..." JWT_SECRET_KEY="..."` |
| Local (PowerShell) | `$env:NEON_DATABASE_URL = "..."` then `python run.py` |

Also set `SECRET_KEY` and `JWT_SECRET_KEY` in production; the built-in defaults are public.

## First-time setup
1. `pip install -r requirements.txt`
2. Set `NEON_DATABASE_URL`.
3. `python check_neon.py` to test the connection.
4. `python sync_to_neon.py` to push local SQLite data to Neon (only if local data is the newest).
5. `python run.py`

## Deploy
- Vercel: `api/index.py` is the entry point (`vercel.json`). On cold start the app restores SQLite from Neon.
- Fly.io / any host: `gunicorn run:app --timeout 120` (see `Procfile`).

## Safety notes
- Change the default admin password (`admin / admin123`) right after first login.
- Do not commit `.env`, `*.db`, or `uploads/patient_documents/` (they hold patient data).
- `cleanup_neon.py` deletes data in Neon; read it before running.
