# Calendar-Genie
# 🧞 Calendar-Genie

An intelligent agent that lives in your chat, preparing you for your next meeting by deciding where to find the most relevant information and switching autonomously between your private documents and the public web.

## 🎯 The Pitch

**"Calendar-Genie is an intelligent agent that lives in your chat. It prepares you for your next meeting by not just reading your calendar, but by deciding where to find the most relevant information, switching autonomously between your private documents and the public web."**

### The Novelty: Dynamic Contextual Grounding

- **Internal Meeting?** 🏢 Pivots to "Private RAG Mode" — reads the full content of your Google Drive docs
- **External Meeting?** 🌐 Pivots to "Public Search Mode" — uses Google to find public context on the person or company
- **Smart Switching:** Automatically chooses the best source based on what's available

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Google account (for OAuth)
- Modern web browser (Chrome, Edge, Firefox)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd Calendar-Genie

# Install dependencies
python3 -m pip install -r requirements.txt
```

### Run in Mock Mode (No Setup Required)

Perfect for testing and development:

```bash
MOCK_AUTH=true python3 main.py
```

Then open: **http://localhost:8000/index.html**

- Click "Sign in with Google" → Instant demo login
- Try: Type "Prep me" or click the Record button

### Run with Real Google OAuth

See [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md) for detailed steps. Quick version:

```bash
export GOOGLE_CLIENT_ID="your-client-id"
export GOOGLE_CLIENT_SECRET="your-client-secret"
python3 main.py
```

## 📋 Architecture

### Three-Tier System

```
Frontend (Static UI)
├── Auth Screen (Google OAuth)
├── Chat UI (Messages + Voice Input)
├── Voice Input (SpeechRecognition API)
└── TTS Fallback (Browser Speech Synthesis)
           ↓
Backend (FastAPI)
├── /auth/google (OAuth initiation)
├── /auth/callback (OAuth handling)
├── /api/user (Session management)
└── /api/chat (Main orchestrator)
           ↓
External APIs
├── Google Calendar API
├── Google Drive API  
├── Google Custom Search API
├── OpenRouter (LLM)
└── ElevenLabs (Audio generation)
```

## 📁 Project Structure

```
Calendar-Genie/
├── index.html                    # Frontend entry point
├── main.py                       # FastAPI backend
├── requirements.txt              # Python dependencies
├── static/
│   ├── auth.js                  # OAuth & session management
│   ├── script.js                # Chat UI & messaging logic
│   └── styles.css               # Styling & responsive design
├── README.md                     # This file
├── GOOGLE_OAUTH_SETUP.md         # Detailed OAuth setup
└── SETUP_COMPLETE.md             # Setup checklist
```

## 🎮 Features

### Phase 1: ✅ Authentication
- [x] Google OAuth sign-in
- [x] Session management
- [x] User profile display
- [x] Mock mode for testing

### Phase 2: ✅ Frontend UI
- [x] Chat message interface
- [x] Text input & Send button
- [x] Voice input (Record button)
- [x] Loading indicators
- [x] Responsive mobile design

### Phase 2.5: ✅ Audio Generation
- [x] ElevenLabs integration (high-quality TTS)
- [x] Automatic audio playback
- [x] Voice selection options
- [x] Fallback speech synthesis
- [x] Data URL audio streaming

### Phase 3: 🔄 Backend Tools (In Progress)
- [ ] Calendar API integration (get next event)
- [ ] Drive RAG (search & read documents)
- [ ] Google Search fallback
- [ ] OpenRouter LLM integration

### Phase 4: 🔄 Full Integration (In Progress)
- [ ] Orchestrator flow (all tools combined)
- [ ] Meeting prep briefing
- [ ] Demo & testing

## 🔧 Configuration

### Environment Variables

**Mock Mode (Default):**
```bash
MOCK_AUTH=true python3 main.py
```

**With ElevenLabs Audio (Recommended):**
```bash
export ELEVENLABS_API_KEY="your-api-key-from-elevenlabs.io"
MOCK_AUTH=true python3 main.py
```

**Real OAuth:**
```bash
export GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="GOCSPX-xxx"
export ELEVENLABS_API_KEY="your-api-key"
python3 main.py
```

**Optional ElevenLabs Configuration:**
```bash
export ELEVENLABS_VOICE_ID="21m00Tcm4TlvDq8ikWAM"  # Rachel (default)
export ELEVENLABS_API_URL="https://api.elevenlabs.io/v1"
```

## 💬 API Endpoints

### Authentication
- `GET /auth/google` - Initiate OAuth flow
- `POST /auth/callback` - Handle OAuth callback
- `POST /auth/logout` - Logout user
- `GET /api/user` - Get current user info

### Chat
- `POST /api/chat` - Send message and get response
  - Request: `{ "text": "user message" }`
  - Response: `{ "text": "response", "audio_url": "...", "source": "private_docs|public_search" }`

## 🎨 UI/UX

### Color Scheme
- **Dark Theme**: Modern dark UI with purple accents
- **Purple Accent**: #7c3aed (Tailwind indigo-600)
- **Responsive**: Mobile-first design

### User Interface
- **Auth Screen**: Clean login panel
- **Chat UI**: Message bubbles with timestamps
- **Voice Input**: Record button with visual feedback
- **Loading State**: "Genie is thinking..." indicator
- **Error Handling**: Friendly error messages

## 🔊 Voice Features

### Speech-to-Text (STT)
- Uses Web Speech Recognition API
- Supported: Chrome, Edge, Firefox
- Auto-submit when done speaking

### Text-to-Speech (TTS)
- Primary: ElevenLabs API (production)
- Fallback: Web Speech Synthesis (browser)
- Auto-play responses

## 📱 Browser Support

| Browser | STT | TTS | Status |
|---------|-----|-----|--------|
| Chrome  | ✅  | ✅  | Fully Supported |
| Edge    | ✅  | ✅  | Fully Supported |
| Firefox | ✅  | ✅  | Fully Supported |
| Safari  | ⚠️  | ✅  | Limited STT |

## 🚀 Deployment

### Development
```bash
MOCK_AUTH=true python3 main.py
```

### Production
1. Get Google OAuth credentials
2. Set environment variables
3. Use production-grade WSGI server (Gunicorn, etc)
4. Enable HTTPS
5. Update redirect URIs in Google Console

## 📚 Documentation

- **Setup Guide**: See [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md)
- **Setup Checklist**: See [SETUP_COMPLETE.md](SETUP_COMPLETE.md)

## 🐛 Troubleshooting

### "Sign in" button doesn't work
- Check browser console (F12) for errors
- Verify backend is running: `MOCK_AUTH=true python3 main.py`
- Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows/Linux)

### "Genie is thinking..." forever
- Check backend logs for `/api/chat` errors
- Verify mock mode is enabled
- Check network tab in DevTools

### Voice input not working
- Verify browser supports Web Speech Recognition
- Check microphone permissions in browser settings
- Try Chrome or Edge (best STT support)

## 📝 Development Notes

### Code Organization
- **auth.js**: OAuth and session management
- **script.js**: Chat UI and messaging
- **main.py**: FastAPI backend and orchestrator
- **styles.css**: Responsive, dark-theme styling

### Best Practices Implemented
- JSDoc comments on all functions
- Error handling throughout
- Session management with cookies
- CORS support
- Responsive mobile design
- Accessibility considerations

## 🎯 Next Steps

1. **Test Current UI**: Run in mock mode and explore
2. **Get Google Credentials**: Follow [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md)
3. **Integrate Calendar API**: Fetch next event details
4. **Integrate Drive RAG**: Search and read documents
5. **Add OpenRouter LLM**: Summarization
6. **Add ElevenLabs Audio**: High-quality voice

## 📄 License

TBD

## 👥 Contributing

TBD

---

**Happy Hacking! 🚀**

For questions or issues, check the troubleshooting section or review backend logs.


