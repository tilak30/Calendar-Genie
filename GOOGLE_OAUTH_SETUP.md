# Google OAuth Setup Guide

Follow these steps to get your Google OAuth credentials for Calendar-Genie.

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top and select **"New Project"**
3. Enter project name: `Calendar-Genie` (or any name)
4. Click **"Create"**

## Step 2: Enable Required APIs

1. In the Cloud Console, go to **"APIs & Services"** → **"Library"**
2. Search for and enable each of these APIs:
   - **Google Calendar API**
   - **Google Drive API**
   - **Google+ API** (or User Info API)

3. For each API:
   - Click on it
   - Click **"Enable"**

## Step 3: Create OAuth 2.0 Credentials

1. Go to **"APIs & Services"** → **"Credentials"**
2. Click **"Create Credentials"** → **"OAuth client ID"**
3. If prompted, click **"Configure Consent Screen"** first:
   - Choose **"External"** user type
   - Fill in basic info (app name, user support email)
   - In **"Scopes"**, add:
     - `openid`
     - `email`
     - `profile`
     - `https://www.googleapis.com/auth/calendar`
     - `https://www.googleapis.com/auth/drive`
   - Save and continue

4. After consent screen, create OAuth credentials:
   - Application type: **"Web application"**
   - Name: `Calendar-Genie`
   - Authorized redirect URIs: Add `http://localhost:8000/auth/callback`
   - Click **"Create"**

5. Copy the **Client ID** and **Client Secret** from the popup

## Step 4: Set Environment Variables

In your terminal, before running the app:

```bash
export GOOGLE_CLIENT_ID="your-client-id-here"
export GOOGLE_CLIENT_SECRET="your-client-secret-here"
```

Or add to a `.env` file in the project root (then load it):

```bash
# .env
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here
```

## Step 5: Run the App

```bash
# Make sure dependencies are installed
python3 -m pip install -r requirements.txt

# Run the backend (if not already running)
python3 main.py

# Open in browser
open http://localhost:8000/index.html
```

## Step 6: Test the Login Flow

1. Click **"Sign in with Google"**
2. You'll see Google's consent screen asking for:
   - Calendar access
   - Drive access
   - Profile info
3. Click **"Allow"**
4. You should be redirected to the chat UI with your email displayed

## Troubleshooting

### "Invalid client ID" error
- Verify your Client ID and Secret are correct
- Check that `http://localhost:8000/auth/callback` is in your authorized redirect URIs

### "Redirect URI mismatch" error
- Make sure the redirect URI in Google Console exactly matches: `http://localhost:8000/auth/callback`
- Check for trailing slashes or protocol mismatches (http vs https)

### Scopes not showing in consent screen
- The first time, Google may show all requested scopes
- On subsequent tests, Google may remember your choice (clear cookies if needed)

## Next Steps

Once login works:
1. The backend will have access to your Google Calendar and Drive
2. You can implement Phase 3 tools:
   - **Calendar Tool**: Fetch your next event
   - **Drive RAG Tool**: Search and read documents
   - **Search Tool**: Fall back to Google Search if no internal docs found
