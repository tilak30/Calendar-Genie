# Migration Guide: Flask → FastAPI Unified Backend

## Summary

✅ **Successfully combined:**
- `main.py` (FastAPI UI + OAuth) 
- `app.py` (Flask LLM conversation logic)
- Into a single **`server.py`** (FastAPI)

## What Changed

### Before
```
main.py (8000)     ← Google OAuth, session management, audio
    ↓
app.py (5001)      ← Meeting prep, chat, LLM agents
```

### After
```
server.py (8000)   ← Everything in one FastAPI server
    ↓
    ├── OAuth (Google)
    ├── Session management
    ├── Meeting prep + chat
    ├── LLM agents
    └── Audio generation
```

## Key Improvements

| Aspect | Flask (`app.py`) | FastAPI (`server.py`) |
|--------|------------------|----------------------|
| **Async Support** | ❌ None | ✅ Full async/await |
| **Session Storage** | Simple dict | Integrated with Starlette |
| **Multiple Meetings** | Single session | Per-user, per-meeting sessions |
| **Error Handling** | Basic try/catch | Proper HTTP exceptions |
| **Validation** | Manual checks | Pydantic models |
| **Documentation** | None | Auto-generated OpenAPI docs |
| **Scalability** | Limited | Async-ready for scaling |

## How to Use

### 1. Stop Old Servers
```bash
pkill -f "python.*app.py"  # Kill Flask
pkill -f "python.*main.py" # Kill old FastAPI (if running)
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start New Unified Server
```bash
# Mock mode (for testing)
MOCK_AUTH=true python server.py

# Real OAuth mode
export GOOGLE_CLIENT_ID="..."
export GOOGLE_CLIENT_SECRET="..."
export OPENROUTER_API_KEY="..."
export ELEVENLABS_API_KEY="..."
python server.py
```

### 4. Update Frontend
The API endpoints remain the same, but:

**Old path (worked before):**
```javascript
POST /api/prep-meeting
{ "meetings": true, "mock_index": 0 }
```

**Now returns:**
```json
{
  "session_id": "...",
  "meeting_session_id": "...",  // NEW
  "status": "ready",
  "meeting": { ... }
}
```

**Old chat endpoint:**
```javascript
POST /api/chat
{ "session_id": "...", "query": "..." }
```

**New chat endpoint:**
```javascript
POST /api/chat
{
  "meeting_session_id": "...",  // CHANGED from session_id
  "query": "..."
}
```

## Frontend Integration Checklist

- [ ] Update `/api/prep-meeting` to capture `meeting_session_id`
- [ ] Update `/api/chat` to use `meeting_session_id` instead of `session_id`
- [ ] Ensure cookies are being sent with requests (they're now httpOnly)
- [ ] Handle `audio_url` field in chat response
- [ ] Display `reasoning` and `decision` fields (optional)

## Files to Delete (Old Code)

```bash
rm app.py               # Old Flask server
# Keep main.py and server.py? Or replace main.py with server.py
```

## Files to Keep/Use

```
server.py              # NEW - Unified server (run this)
meeting.json           # Unchanged
agents/                # Unchanged
requirements.txt       # Updated
ARCHITECTURE.md        # NEW - Documentation
test_unified_backend.sh # NEW - Integration tests
```

## Testing

```bash
# Run integration tests
./test_unified_backend.sh

# Or test individual endpoints
curl http://localhost:8000/health
curl http://localhost:8000/auth/google
# ... etc
```

## Troubleshooting

### "Session expired" when calling /api/chat
- Ensure you got session_id from `/auth/google` 
- Make sure you're including it in cookies: `-H "Cookie: session_id=..."`

### "Invalid meeting session"
- Call `/api/prep-meeting` first to get `meeting_session_id`
- Use that `meeting_session_id` in chat requests, not `session_id`

### Port 8000 in use
```bash
lsof -i :8000
kill -9 <PID>
```

### ElevenLabs audio not generating
- Ensure `ELEVENLABS_API_KEY` is set
- Server will continue working, just `audio_url: null`

## Performance Notes

- **Async operations**: All API calls (OpenRouter, ElevenLabs, etc.) are now async
- **Faster response times**: No blocking I/O
- **Better concurrency**: Can handle multiple users/requests simultaneously
- **Memory efficient**: Sessions are in-memory (consider Redis for production)

## Next Steps for Production

1. **Database**: Move sessions from memory to MongoDB/PostgreSQL
2. **Caching**: Use Redis for conversation history
3. **Logging**: Add structured logging (JSON logs)
4. **Monitoring**: Add Datadog/CloudWatch
5. **Rate Limiting**: Add per-user rate limits
6. **Authentication**: Implement proper JWT tokens
7. **Testing**: Add unit/integration tests with pytest
8. **Deployment**: Use Docker + Kubernetes/Render/Railway

## Questions?

Refer to `ARCHITECTURE.md` for detailed system design.
