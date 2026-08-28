# Deploy AI Meeting Assistant on Render (Docker)

Your code is on GitHub: https://github.com/Deepmalasinghrajput/MeetMind

## Quick path (Web Service)

1. Open https://dashboard.render.com → **New** → **Web Service**.
2. Connect GitHub if needed.
3. Connect account **Deepmalasinghrajput** and select repo **MeetMind**.
4. Settings:

| Field | Value |
| --- | --- |
| Name | `ai-meeting-assistant` |
| Runtime | **Docker** |
| Branch | `main` |
| Dockerfile Path | `./Dockerfile` |
| Docker Context | `.` |
| Instance type | **Starter** (recommended) |

5. **Environment** (Environment tab):

| Key | Value |
| --- | --- |
| `GROQ_API_KEY` | your Groq API key |
| `SECRET_KEY` | long random string (or Generate) |
| `WHISPER_MODEL` | `tiny` |
| `WEB_CONCURRENCY` | `1` |
| `GUNICORN_TIMEOUT` | `600` |
| `GUNICORN_THREADS` | `1` |
| `FORCE_HTTPS` | `true` |

6. Health check path: `/health`
7. (Optional) **Disk**: name `ai-meeting-assistant-data`, mount `/app/data`, 2 GB — saves SQLite history.
8. **Create Web Service** and wait for the build.

### Live demo tip

On Render, use **Upload file** with a short MP3/WAV (under 2 minutes). YouTube URLs often fail with “not a bot” on cloud IPs — that is YouTube blocking datacenter traffic, not a broken deploy.

## Blueprint path

1. **New** → **Blueprint**.
2. Select **MeetMind** repo.
3. Render reads `render.yaml`.
4. Set `GROQ_API_KEY` when prompted.

## After deploy

- Open `https://ai-meeting-assistant-xxxx.onrender.com`
- First Whisper load can take several minutes.
- Prefer `WHISPER_MODEL=tiny` on small plans.

## Local Docker smoke test

```bash
docker build -t ai-meeting-assistant .
docker run --rm -p 10000:10000 -e PORT=10000 -e GROQ_API_KEY=your_key -e SECRET_KEY=dev ai-meeting-assistant
```
