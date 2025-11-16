#!/bin/bash
# QUICK START GUIDE

echo "╔════════════════════════════════════════════════════════════╗"
echo "║      Calendar-Genie Unified Backend - Quick Start          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check Python version
echo "🐍 Checking Python..."
python3 --version

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                  AVAILABLE COMMANDS                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "1️⃣  Start server (MOCK mode):"
echo "   MOCK_AUTH=true python server.py"
echo ""
echo "2️⃣  Start server (REAL OAuth):"
echo "   export GOOGLE_CLIENT_ID='...'"
echo "   export GOOGLE_CLIENT_SECRET='...'"
echo "   python server.py"
echo ""
echo "3️⃣  Run integration tests:"
echo "   ./test_unified_backend.sh"
echo ""
echo "4️⃣  View API documentation (after server starts):"
echo "   http://localhost:8000/docs"
echo ""
echo "5️⃣  Kill old Flask server:"
echo "   pkill -f 'python.*app.py'"
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    ENVIRONMENT VARIABLES                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Set these in your .env file or export them:"
echo ""
echo "MOCK_AUTH=true                    # Use mock mode (no OAuth)"
echo "GOOGLE_CLIENT_ID=...              # Google OAuth client ID"
echo "GOOGLE_CLIENT_SECRET=...          # Google OAuth secret"
echo "OPENROUTER_API_KEY=...            # OpenRouter API key (for Claude)"
echo "ELEVENLABS_API_KEY=...            # ElevenLabs API key (for audio)"
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    API ENDPOINTS                           ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Health:          GET /health"
echo "Auth:            GET /auth/google"
echo "Callback:        POST /auth/callback"
echo "User:            GET /api/user"
echo "Logout:          POST /auth/logout"
echo "Prep Meeting:    POST /api/prep-meeting"
echo "Chat:            POST /api/chat"
echo "API Docs:        GET /docs"
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    USEFUL FILES                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "server.py              Main unified backend (FastAPI)"
echo "ARCHITECTURE.md        System design & architecture"
echo "MIGRATION_GUIDE.md     Guide for migrating from Flask"
echo "test_unified_backend.sh Integration test suite"
echo "requirements.txt       Python dependencies"
echo ""
echo "Ready to start? Run: MOCK_AUTH=true python server.py"
echo ""
