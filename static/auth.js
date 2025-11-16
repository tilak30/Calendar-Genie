/**
 * Calendar-Genie Auth Module
 * Handles Google OAuth authentication and session management
 */

const API_BASE = 'http://localhost:8000';

/**
 * Check if user is already logged in by verifying session with backend
 * @returns {Promise<Object|null>} User data {email, name, picture} or null if not authenticated
 */
async function checkAuthStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/user`, {
      method: 'GET',
      credentials: 'include'
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn('Auth check failed:', e);
  }
  return null;
}

/**
 * Initiate Google OAuth flow
 * Redirects user to backend OAuth endpoint which handles Google login
 */
function initiateGoogleAuth() {
  window.location.href = `${API_BASE}/auth/google`;
}

/**
 * Handle OAuth callback from backend after user authorizes
 * Checks for session parameter (mock mode) or authorization code (real OAuth)
 * @returns {Promise<Object|null>} User data or null if callback failed
 */
async function handleAuthCallback() {
  const params = new URLSearchParams(window.location.search);
  const session = params.get('session');

  if (session) {
    // Mock mode or OAuth callback - session cookie set by backend
    window.history.replaceState({}, document.title, '/index.html');
    return await checkAuthStatus();
  }
  
  const code = params.get('code');
  if (code) {
    try {
      const res = await fetch(`${API_BASE}/auth/callback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ code })
      });

      if (res.ok) {
        window.history.replaceState({}, document.title, '/index.html');
        return await res.json();
      } else {
        console.error('Auth callback failed:', res.status);
      }
    } catch (e) {
      console.error('Auth callback error:', e);
    }
  }
  return null;
}

/**
 * Logout user and clear session
 * Clears cookies and redirects to auth screen
 */
async function logout() {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include'
    });
  } catch (e) {
    console.warn('Logout error:', e);
  }
  sessionStorage.clear();
  window.location.href = '/index.html';
}
