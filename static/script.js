/**
 * Calendar-Genie Chat Application
 * Handles UI, messaging, voice input, and responses
 * Note: API_BASE is defined in auth.js
 */

// ============================================================================
// STATE
// ============================================================================

let recognition = null;
let recording = false;
let currentUser = null;
let currentMeetingSessionId = null;  // Track current meeting session

// DOM elements (initialized in setupApp)
let authScreen, appScreen, googleSigninBtn, logoutBtn, userEmailEl;
let messagesEl, form, input, recordBtn;

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Setup the app after DOM is ready
 * Checks authentication and either shows auth screen or chat UI
 */
async function setupApp() {
  // Cache DOM elements
  authScreen = document.getElementById('auth-screen');
  appScreen = document.getElementById('app-screen');
  googleSigninBtn = document.getElementById('google-signin-btn');
  logoutBtn = document.getElementById('logout-btn');
  userEmailEl = document.getElementById('user-email');
  messagesEl = document.getElementById('messages');
  form = document.getElementById('chat-form');
  input = document.getElementById('input');
  recordBtn = document.getElementById('record-btn');

  // Setup event listeners
  googleSigninBtn.addEventListener('click', initiateGoogleAuth);
  logoutBtn.addEventListener('click', logout);

  // Check authentication
  let user = await handleAuthCallback();
  if (!user) {
    user = await checkAuthStatus();
  }

  if (user) {
    // Show chat UI
    currentUser = user;
    userEmailEl.innerText = `${user.name || user.email}`;
    authScreen.classList.add('hidden');
    appScreen.classList.remove('hidden');
    initChat();
  } else {
    // Show auth screen
    authScreen.classList.remove('hidden');
    appScreen.classList.add('hidden');
  }
}

/**
 * Initialize chat interface after user is authenticated
 */
function initChat() {
  recordBtn.disabled = false;
  recordBtn.title = 'Record your message';

  // Setup speech recognition if available
  setupSpeechRecognition();

  // Setup form submission
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    handleSend(input.value.trim());
  });

  // Auto-prepare first meeting on init
  prepareFirstMeeting();

  // Welcome message
  addMessage('Hello! I\'m Calendar-Genie. Type or say "Prep me" to prepare for your next meeting.', 'assistant');
}

// ============================================================================
// MESSAGE UI
// ============================================================================

/**
 * Add a message to the chat display
 * @param {string} text - Message text
 * @param {string} who - 'user' or 'assistant'
 * @param {string} meta - Optional metadata (source, timestamp, etc)
 */
function addMessage(text, who = 'assistant', meta = null) {
  const bubble = document.createElement('div');
  bubble.className = `bubble ${who === 'user' ? 'user' : 'assistant'}`;
  bubble.textContent = text;

  if (meta) {
    const metaEl = document.createElement('div');
    metaEl.className = 'meta';
    metaEl.textContent = meta;
    bubble.appendChild(metaEl);
  }

  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/**
 * Show "thinking" loading indicator
 */
function addLoading() {
  const bubble = document.createElement('div');
  bubble.id = 'loading-bubble';
  bubble.className = 'bubble assistant loading';
  bubble.textContent = '✨ Genie is thinking...';
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/**
 * Hide loading indicator
 */
function removeLoading() {
  const bubble = document.getElementById('loading-bubble');
  if (bubble) bubble.remove();
}

// ============================================================================
// CHAT LOGIC
// ============================================================================

/**
 * Prepare first meeting session
 * Must be called before sending chat messages
 */
async function prepareFirstMeeting() {
  try {
    const res = await fetch(`${API_BASE}/api/prep-meeting`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ 
        meetings: true,  // Use mock meetings
        mock_index: 0 
      })
    });

    if (!res.ok) {
      throw new Error(`Prep meeting failed: ${res.status}`);
    }

    const data = await res.json();
    currentMeetingSessionId = data.meeting_session_id;
    console.log('✅ Meeting prepared:', data.meeting.title);
  } catch (err) {
    console.error('Prep meeting error:', err);
    addMessage('⚠️ Could not prepare meeting. Retrying...', 'assistant');
    setTimeout(prepareFirstMeeting, 2000);
  }
}

/**
 * Send message to backend and handle response
 * @param {string} text - User message
 */
async function handleSend(text) {
  if (!text || !text.trim()) return;

  // Ensure meeting is prepared
  if (!currentMeetingSessionId) {
    addMessage('⚠️ Meeting not ready yet. Please wait...', 'assistant');
    await prepareFirstMeeting();
    return;
  }

  addMessage(text, 'user');
  input.value = '';
  addLoading();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ 
        query: text,
        meeting_session_id: currentMeetingSessionId
      })
    });

    if (!res.ok) {
      throw new Error(`Server error: ${res.status}`);
    }

    const data = await res.json();
    removeLoading();

    // Display response
    const { text: responseText, answer, audio_url, source } = data;
    let displayText = answer || responseText || '(No response)';

    if (source === 'public_search') {
      displayText += '\n\n📌 (Info from Google Search)';
    }

    addMessage(displayText, 'assistant');

    // Play audio or speak
    if (audio_url) {
      console.log('📌 Playing audio from URL');
      try {
        await playAudio(audio_url);
      } catch (audioErr) {
        console.warn('Audio playback error, using fallback speech synthesis:', audioErr);
        console.log('Calling speakTextFallback due to audio error');
        speakTextFallback(answer || responseText);
      }
    } else {
      // No audio URL, use fallback
      console.log('📌 No audio_url, using speech synthesis fallback');
      console.log('About to call speakTextFallback with:', (answer || responseText).substring(0, 50) + '...');
      speakTextFallback(answer || responseText);
    }

  } catch (err) {
    removeLoading();
    console.error('Chat error:', err);
    addMessage('❌ Error: Could not reach backend.', 'assistant');
    speakTextFallback('Sorry, I encountered an error. Please try again.');
  }
}

/**
 * Play audio from URL or fallback to speech synthesis
 * @param {string} url - Audio URL
 */
async function playAudio(url) {
  try {
    const audio = new Audio(url);
    audio.crossOrigin = 'anonymous';
    await audio.play();
  } catch (e) {
    console.warn('Audio playback failed, using speech synthesis:', e);
    // Fallback handled by caller
  }
}

/**
 * Speak text using Web Speech API (fallback only if audio_url fails)
 * @param {string} text - Text to speak
 */
function speakTextFallback(text) {
  console.log('🔄 speakTextFallback() called');
  
  if ('speechSynthesis' in window) {
    console.log('✅ speechSynthesis is available');
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    
    // Add event listeners
    utterance.onstart = () => console.log('🔊 Speech STARTED');
    utterance.onend = () => console.log('✅ Speech ENDED');
    utterance.onerror = (e) => console.error('❌ Speech ERROR:', e.error);
    
    window.speechSynthesis.cancel();
    console.log('About to call speechSynthesis.speak()');
    window.speechSynthesis.speak(utterance);
    console.log('speak() called');
  } else {
    console.error('❌ speechSynthesis NOT available in this browser');
  }
}

// ============================================================================
// SPEECH RECOGNITION (STT - Speech To Text)
// ============================================================================

/**
 * Setup Web Speech Recognition API
 * Allows users to speak their message instead of typing
 */
function setupSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SR) {
    recordBtn.disabled = true;
    recordBtn.title = 'Speech Recognition not supported in this browser';
    return;
  }

  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    recording = true;
    recordBtn.innerText = '🎙️ Listening...';
  };

  recognition.onresult = (event) => {
    // Only process final results, not interim ones
    const isFinal = event.results[event.results.length - 1].isFinal;
    const transcript = event.results[event.results.length - 1][0].transcript;
    
    if (isFinal) {
      input.value = transcript;
      handleSend(transcript);
    } else {
      // Show interim transcript in input for user feedback
      input.value = transcript;
    }
  };

  recognition.onerror = (event) => {
    console.warn('Speech recognition error:', event.error);
    // Show a clearer, actionable message to the user
    addMessage(`❌ Mic error: ${event.error}. Try: check microphone permissions, ensure you're online, or try another browser.`, 'assistant');
    // Run a quick microphone diagnostic to help the user
    testMicrophoneAccess().then(result => {
      addMessage(`🔎 Microphone test: ${result}`, 'assistant');
    }).catch(err => {
      console.warn('Microphone diagnostic failed:', err);
      addMessage('🔎 Microphone test failed. Check browser and OS permissions.', 'assistant');
    });

    recording = false;
    recordBtn.innerText = '● Record';
  };

  recognition.onend = () => {
    recording = false;
    recordBtn.innerText = '● Record';
  };

  // Toggle recording on button click
  recordBtn.addEventListener('click', () => {
    if (recording) {
      recognition.stop();
      recording = false;
      recordBtn.innerText = '● Record';
    } else {
      try {
        recognition.start();
      } catch (e) {
        console.warn('Could not start speech recognition:', e);
      }
    }
  });
}

// ============================================================================
// APP INITIALIZATION
// ============================================================================

/**
 * Quick microphone diagnostic using getUserMedia
 * Returns a human-friendly string describing result
 */
async function testMicrophoneAccess() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return 'getUserMedia not supported by this browser.';
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const tracks = stream.getAudioTracks();
    // Stop tracks immediately -- this was just a diagnostic
    tracks.forEach(t => t.stop());
    if (tracks.length > 0) return 'Microphone accessible (OK).';
    return 'No audio tracks found (microphone not detected).';
  } catch (err) {
    // Normalize common errors
    if (err && err.name === 'NotAllowedError') return 'Permission denied for microphone. Grant permission in browser/OS settings.';
    if (err && err.name === 'NotFoundError') return 'No microphone found. Check your audio input device.';
    if (err && err.name === 'AbortError') return 'Microphone access aborted.';
    if (err && err.name === 'NotReadableError') return 'Microphone is already in use by another application.';
    return `getUserMedia error: ${err && err.message ? err.message : err}`;
  }
}

// Wait for DOM to be ready before initializing
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupApp);
} else {
  setupApp();
}
