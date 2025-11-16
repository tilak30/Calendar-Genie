#!/bin/bash
# Quick Reference Commands for ElevenLabs Testing

# ============================================================================
# VERIFY SETUP
# ============================================================================

# Check API key is set
echo "🔑 Checking API key..."
echo $ELEVENLABS_API_KEY | cut -c1-20
echo "..."

# Check Python syntax
echo -e "\n✅ Checking Python syntax..."
python3 -m py_compile main.py && echo "✅ Syntax valid" || echo "❌ Syntax error"

# Check dependencies
echo -e "\n📦 Checking dependencies..."
python3 -m pip list | grep -E "fastapi|elevenlabs|httpx|uvicorn"

# ============================================================================
# SET API KEY (if needed)
# ============================================================================

# Uncomment and replace with your key:
# export ELEVENLABS_API_KEY="your-api-key-from-elevenlabs.io"

# ============================================================================
# RUN TESTS
# ============================================================================

# Quick test of ElevenLabs connection
echo -e "\n🧪 Quick ElevenLabs test..."
python3 test_elevenlabs.py

# ============================================================================
# START BACKEND
# ============================================================================

# In Terminal 1:
echo -e "\n🚀 Starting backend..."
echo "Run in Terminal 1:"
echo "  MOCK_AUTH=true python3 main.py"

# ============================================================================
# TEST IN BROWSER
# ============================================================================

# In Terminal 2 or Browser:
echo -e "\n🌐 Open in browser:"
echo "  http://localhost:8000"

# ============================================================================
# MANUAL API TEST
# ============================================================================

# In Terminal 2:
echo -e "\n🧪 Test API directly:"
echo "  curl -X POST http://localhost:8000/api/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\":\"hello\"}' \\"
echo "    -b 'session_id=test'"

# ============================================================================
# VOICE OPTIONS
# ============================================================================

echo -e "\n🎵 Available voices:"
echo "  Rachel (calm):     21m00Tcm4TlvDq8ikWAM (default)"
echo "  Bella (warm):      EXAVITQu4vr4xnSDxMaL"
echo "  Josh (confident):  TxGEqnHWrfWFTfGW9XjX"
echo "  Callum (British):  pFZP5JQG7iQjIQuC4Iy3"

# To change voice:
echo -e "\n  export ELEVENLABS_VOICE_ID='EXAVITQu4vr4xnSDxMaL'"
echo "  MOCK_AUTH=true python3 main.py"

# ============================================================================
# CLEANUP
# ============================================================================

# Stop backend (in Terminal 1):
echo -e "\n⏹️  To stop backend:"
echo "  Press Ctrl+C"

# ============================================================================
# TROUBLESHOOTING
# ============================================================================

echo -e "\n❓ Troubleshooting:"
echo "  - No audio: Check speaker, browser console (F12)"
echo "  - API error: Verify ELEVENLABS_API_KEY is set"
echo "  - Backend won't start: Check python3 -m py_compile main.py"
echo "  - Slow: Normal (1-3 sec for ElevenLabs generation)"

# ============================================================================
# USEFUL LINKS
# ============================================================================

echo -e "\n🔗 Useful links:"
echo "  - ElevenLabs Dashboard: https://elevenlabs.io"
echo "  - Voice Lab: https://elevenlabs.io/voice-lab"
echo "  - API Docs: https://elevenlabs.io/docs"
echo "  - Pricing: https://elevenlabs.io/pricing"

