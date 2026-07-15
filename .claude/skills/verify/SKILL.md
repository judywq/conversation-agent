---
name: verify
description: How to build, run, and drive this app end-to-end to verify frontend/conversation changes.
---

# Verifying conversation-agent changes

## Stack layout
- Backend (Django + Channels + Celery + Postgres + Redis) runs via Docker Compose; containers are named `conversation-agent-*`. API on `http://localhost:8000`, WS on `ws://localhost:8000/ws`. A Docker vite also serves port 5173.
- Frontend: `cd vue_frontend && npm run dev` — picks port 5174 when 5173 is taken by the Docker vite. Both serve the same mounted source.
- `npm run type-check` (vue-tsc) is clean; `npm run lint` has ~10 pre-existing errors in ConversationView.vue (`any` in catch blocks, unused `volunteer`/`sendTextTurn`/etc.) — don't count those against a change. `wordMouthSync.spec.ts > uses multiple flaps for long words` fails on the branch baseline (stale expectation after FLAP_MS change).

## Backend shell access
`docker exec conversation-agent-django-1 python manage.py ...` fails with `DATABASE_URL` unset — go through the entrypoint:

```
docker exec conversation-agent-django-1 /entrypoint python manage.py shell -c "..."
```

## Test login
- User: `admin@example.com` / `MyPass123` (from `.envs/.local/.django`). If login fails, reset via the shell above: `u.set_password('MyPass123'); u.save()`.
- Starting a session requires `UserProfile.profile_completed=True` — set it directly on `backend.users.models.UserProfile` if needed.

## Driving the UI (Playwright, headless)
- `uv run` a script with inline `dependencies = ["playwright"]`; chromium binaries are already in the ms-playwright cache.
- Launch args that matter: `--autoplay-policy=no-user-gesture-required` (turn audio), `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream` + context `permissions=["microphone"]` (mic recording works headless).
- Login form: `input[type=email]` / `input[type=password]` at `/auth/login`; conversation at `/app/conversation`.
- Setup phase gotcha: `select` also matches radix's hidden selects — the partner-count select is `select.h-9`.
- A real 1-partner session with a "keep answers very short" topic produces the first agent turn (LLM+TTS) in ~10–30 s; poll rather than fixed-wait.
- WebGL/Live2D renders fine in headless chromium (expect benign `GPU stall due to ReadPixels` warnings).
- The floating Vue DevTools anchor appears bottom-center in dev builds — ignore it in screenshots.
