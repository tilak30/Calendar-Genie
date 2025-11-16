# 🎉 Unified Backend - Complete Setup

## What's Done ✅

Your Flask (`app.py`) + FastAPI (`main.py`) backends have been successfully merged into a single, powerful FastAPI server (`server.py`) running on port 8000.

### Combined Features:
- ✅ Google OAuth authentication (from main.py)
- ✅ Session management with httpOnly cookies (secure!)
- ✅ Meeting preparation (from app.py)
- ✅ LLM-powered chat with RAG/Web search (from app.py)
- ✅ ElevenLabs audio generation (from main.py)
- ✅ Conversation history tracking (from app.py)
- ✅ Auto-generated API documentation (/docs)
- ✅ Async operations for better performance

## Files Overview

```
📁 Project Root
├── server.py                    ⭐ NEW - Main unified server (use this!)
├── requirements.txt             ✏️ UPDATED - FastAPI instead of Flask
├── ARCHITECTURE.md              📖 System design & detailed architecture
├── MIGRATION_GUIDE.md           📖 Guide from Flask/old FastAPI
├── IMPLEMENTATION_SUMMARY.md    📖 What was built & how
├── FRONTEND_INTEGRATION.md      📖 Frontend API integration guide
├── QUICKSTART.sh               🚀 Quick setup script
├── test_unified_backend.sh     🧪 Integration tests
│
├── app.py                       📦 OLD - Flask backend (can be archived)
├── main.py                      📦 OLD - FastAPI UI (replaced by server.py)
├── meeting.json                 📋 Mock meetings data
├── agents/                      🤖 LLM agents (unchanged)
│   ├── conversation_agent.py
│   ├── smart_fetcher.py
│   └── answer_synthesizer.py
│
├── static/                      🎨 Frontend assets (unchanged)
│   ├── auth.js
│   ├── script.js
│   └── styles.css
├── index.html                   🌐 Frontend (unchanged)
└── .env                         🔐 Environment variables
```

## Quick Start (30 seconds)

```bash
# 1. Run quick start setup
./QUICKSTART.sh

# 2. Start the server (pick one)
MOCK_AUTH=true python server.py          # Development (no OAuth)
# OR
python server.py                          # Production (with real OAuth)

# 3. Test it
./test_unified_backend.sh
```

## What Changed for Frontend Devs?

### Before (Flask + Old FastAPI)
- Two servers on different ports
- Pass `session_id` to chat endpoint
- No audio support

### After (Unified FastAPI)
- One server on port 8000
- Pass `meeting_session_id` (not `session_id`) to chat
- Full audio support included
- Better error messages

**[See FRONTEND_INTEGRATION.md for exact code changes]**

## Key Endpoints

```
Authentication:
  GET  /auth/google          Start OAuth flow
  POST /auth/callback        OAuth callback (auto-handled)
  POST /auth/logout          Logout
  GET  /api/user            Get user info

Meetings:
  POST /api/prep-meeting    Create meeting session
  POST /api/chat            Send message & get response

Utilities:
  GET  /health              Server health
  GET  /docs                Interactive API docs
  GET  /                    Serve index.html
```

## Running the Server

### Development (Fastest - no OAuth)
```bash
MOCK_AUTH=true python server.py
# Then visit http://localhost:8000
```

### Production (Real Google OAuth)
```bash
export GOOGLE_CLIENT_ID="your-client-id"
export GOOGLE_CLIENT_SECRET="your-client-secret"  
export OPENROUTER_API_KEY="your-openrouter-key"
export ELEVENLABS_API_KEY="your-elevenlabs-key"

python server.py
```

### Using Docker (recommended for production)
```bash
docker build -t calendar-genie .
docker run -p 8000:8000 \
  -e MOCK_AUTH=true \
  calendar-genie
```

## Environment Variables

```bash
# Auth
MOCK_AUTH=true                           # Skip real OAuth
GOOGLE_CLIENT_ID="client-id"            # OAuth client ID
GOOGLE_CLIENT_SECRET="client-secret"    # OAuth secret

# LLM
OPENROUTER_API_KEY="key"                # Claude API key

# Audio
ELEVENLABS_API_KEY="key"                # ElevenLabs API key
ELEVENLABS_VOICE_ID="21m00Tcm4..."      # Voice to use
```

## Testing

Run the included integration test:
```bash
./test_unified_backend.sh
```

This tests:
- ✅ OAuth/session creation
- ✅ Meeting preparation
- ✅ Chat with LLM
- ✅ History tracking
- ✅ Health checks

## Documentation

Choose what you need:

| Document | For |
|----------|-----|
| **ARCHITECTURE.md** | Understanding system design |
| **MIGRATION_GUIDE.md** | How Flask/FastAPI converted |
| **IMPLEMENTATION_SUMMARY.md** | What was implemented & why |
| **FRONTEND_INTEGRATION.md** | Updating frontend code |
| **QUICKSTART.sh** | Fast setup instructions |

## FAQ

### Q: Why FastAPI instead of Flask?
**A:** FastAPI is async-first (better for I/O-heavy operations), has auto-docs, and is ~3x faster. Perfect for calling external APIs (OpenRouter, ElevenLabs, Google).

### Q: Do I need to update my frontend?
**A:** Yes, but minimally. Change `session_id` → `meeting_session_id` in chat requests. See FRONTEND_INTEGRATION.md for exact code.

### Q: Can I use the old Flask server?
**A:** Not recommended. The unified server does everything better. You can archive `app.py` and `main.py`.

### Q: How do I add the conversation history to my frontend?
**A:** The server tracks it automatically. Each chat response includes full context. To retrieve history, add a `GET /api/history/{meeting_session_id}` endpoint (not yet implemented - let me know if needed).

### Q: What if ElevenLabs API key is missing?
**A:** The server gracefully degrades - `audio_url` will be `null` but text response works fine.

### Q: Can I deploy this to production?
**A:** Yes! Use Docker, set proper environment variables, and upgrade storage from memory to Redis/PostgreSQL. See ARCHITECTURE.md for production checklist.

## Support

- **Quick help**: See FAQ above
- **Setup issues**: Run `./QUICKSTART.sh`
- **Integration issues**: Check `FRONTEND_INTEGRATION.md`
- **Architecture questions**: Read `ARCHITECTURE.md`
- **Migration help**: See `MIGRATION_GUIDE.md`

## Next Steps

1. ✅ Run `./QUICKSTART.sh` to setup
2. ✅ Start server: `MOCK_AUTH=true python server.py`
3. ✅ Run tests: `./test_unified_backend.sh`
4. ✅ Update frontend (see FRONTEND_INTEGRATION.md)
5. ✅ Test end-to-end
6. ✅ Deploy! 🚀

## Tech Stack

- **Server**: FastAPI + Uvicorn
- **Auth**: Google OAuth 2.0
- **LLM**: Claude 3.5 (via OpenRouter)
- **Search**: Web search + RAG agents
- **Audio**: ElevenLabs text-to-speech
- **Language**: Python 3.8+

## License

Same as original project

---

**Status**: ✅ Production-ready (with minor setup)  
**Last Updated**: Nov 15, 2025  
**Maintainer**: Your team

Need help? Check the docs directory! 📚
