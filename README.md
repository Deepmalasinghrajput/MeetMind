# MeetMind — AI Meeting Assistant

Full-stack meeting intelligence app: upload / YouTube → Whisper STT → LLM summary & action items → RAG chat → export. Auth, history, responsive UI.

## Stack

- **Backend:** Flask, Gunicorn, SQLite  
- **AI:** OpenAI Whisper, LangChain, Groq, ChromaDB  
- **Frontend:** HTML/CSS/JS (responsive)  
- **Deploy:** Docker, Render  

## Local run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # add GROQ_API_KEY
python app.py
```

Open http://127.0.0.1:5000

## Docker (local)

```bash
docker build -t meetmind .
docker run --rm -p 5000:5000 \
  -e GROQ_API_KEY=your_key \
  -e SECRET_KEY=change-me \
  -e WHISPER_MODEL=tiny \
  meetmind
```

## Deploy on Render (Docker)

1. Push this repo to GitHub (already set as origin if forked).
2. https://dashboard.render.com → **New** → **Web Service**.
3. Connect **Deepmalasinghrajput/MeetMind** (or your fork).
4. **Runtime:** Docker  
5. **Dockerfile path:** `./Dockerfile`  
6. **Plan:** Starter or higher is strongly recommended (Whisper + ML deps need RAM). Free may run out of memory.
7. **Environment:**
   - `GROQ_API_KEY` = your Groq key  
   - `SECRET_KEY` = long random string (or let Render generate)  
   - `WHISPER_MODEL=tiny` (fastest/smallest)  
8. Optional: **Persistent Disk** mount path `/app/data` (SQLite history).  
9. Health check path: `/health`  
10. Deploy and open the public URL.

Blueprint: you can also use **New → Blueprint** with `render.yaml` in the repo root, then set `GROQ_API_KEY` when prompted.

### Notes for production

- First request that loads Whisper may take minutes (model download).  
- Prefer `WHISPER_MODEL=tiny` on small instances.  
- Keep secrets in Render env vars — never commit `.env`.

## License

Student / personal project.
