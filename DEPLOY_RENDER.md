# Deploy MeetMind on Render (Docker)

Your code is on GitHub: https://github.com/Deepmalasinghrajput/MeetMind

## 1) Create the service (click path)

1. Open https://dashboard.render.com and sign in (GitHub login is easiest).
2. **New** → **Web Service**.
3. Connect account **Deepmalasinghrajput** and select repo **MeetMind**.
4. Configure:

| Setting | Value |
|--------|--------|
| Name | `meetmind` |
| Region | Oregon (or closest) |
| Branch | `main` |
| Runtime | **Docker** |
| Dockerfile Path | `./Dockerfile` |
| Instance type | **Starter** (or higher) |

> Free tier often fails: Docker image is large (Torch + Whisper). Use **Starter**.

5. **Health Check Path:** `/health`
6. **Environment** → Add:

| Key | Value |
|-----|--------|
| `GROQ_API_KEY` | Your key from https://console.groq.com |
| `SECRET_KEY` | Long random string (or click Generate) |
| `WHISPER_MODEL` | `tiny` |
| `WEB_CONCURRENCY` | `1` |
| `GUNICORN_TIMEOUT` | `600` |
| `FORCE_HTTPS` | `true` |

7. (Optional) **Disk**: name `meetmind-data`, mount `/app/data`, 2 GB — saves SQLite history.
8. Click **Create Web Service** / **Deploy**.

Build can take **15–40+ minutes** the first time.

## 2) Blueprint path (uses `render.yaml`)

1. **New** → **Blueprint**.
2. Select **MeetMind** repo.
3. When prompted, set **GROQ_API_KEY**.
4. Apply → wait for deploy.

## 3) After deploy

- Open `https://meetmind-xxxx.onrender.com`
- Create an account and try **Transcribe**.
- First Whisper run downloads a model; wait a few minutes once.

## 4) If deploy fails

| Error | Fix |
|-------|-----|
| Out of memory / OOM | Upgrade plan; keep `WHISPER_MODEL=tiny` |
| Build timeout | Retry; Starter has longer builds |
| Health check failed | Ensure entrypoint binds `$PORT`; wait for start |
| App loses meetings | Add disk at `/app/data` |

## Local Docker (test before cloud)

```bash
docker build -t meetmind .
docker run --rm -p 10000:10000 -e PORT=10000 -e GROQ_API_KEY=your_key -e SECRET_KEY=dev meetmind
```
