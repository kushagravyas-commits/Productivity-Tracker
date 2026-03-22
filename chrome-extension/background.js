// TrackFlow Browser Context — Background Service Worker
// Polls active tab + all tabs every 5s and sends to local backend

const API_URL = 'http://127.0.0.1:8080/api/v1/context/browser';
const INTERVAL_MS = 5000;
const FETCH_TIMEOUT_MS = 5000;
const MAX_RETRY_QUEUE = 50;
const _retryQueue = [];

// Stable machine ID — generated once, stored in chrome.storage.local
let machineGuid = null;
chrome.storage.local.get('trackflow_machine_guid', (result) => {
  if (result.trackflow_machine_guid) {
    machineGuid = result.trackflow_machine_guid;
  } else {
    machineGuid = crypto.randomUUID();
    chrome.storage.local.set({ trackflow_machine_guid: machineGuid });
  }
});

// YouTube context is stored here when the content script messages us
let youtubeContext = null;
// Message listener is below (combined with keepalive listener)

function detectBrowser() {
  if (navigator.userAgentData && navigator.userAgentData.brands) {
    const brands = navigator.userAgentData.brands.map(b => b.brand.toLowerCase());
    if (brands.includes('brave')) return 'Brave';
    if (brands.includes('microsoft edge')) return 'Edge';
    if (brands.includes('opera')) return 'Opera';
  }

  const ua = navigator.userAgent;
  if (ua.includes('Brave')) return 'Brave';
  if (ua.includes('Edg/')) return 'Edge';
  if (ua.includes('OPR/')) return 'Opera';
  if (ua.includes('Chrome')) return 'Chrome';
  if (ua.includes('Firefox')) return 'Firefox';
  return 'Browser';
}

function extractDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

async function fetchWithTimeout(url, headers, body) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    await fetch(url, {
      method: 'POST',
      headers,
      body,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

async function flushRetryQueue(headers) {
  while (_retryQueue.length > 0) {
    const item = _retryQueue[0];
    try {
      await fetchWithTimeout(API_URL, headers, item);
      _retryQueue.shift(); // success — remove from queue
    } catch {
      break; // server still down — stop retrying
    }
  }
}

async function collectAndSend() {
  try {
    const [allTabs, activeTabs] = await Promise.all([
      chrome.tabs.query({}),
      chrome.tabs.query({ active: true, currentWindow: true }),
    ]);

    const activeTab = activeTabs[0] ?? null;
    const activeUrl = activeTab?.url ?? null;
    const activeDomain = activeUrl ? extractDomain(activeUrl) : null;
    const isYouTube = activeUrl?.includes('youtube.com/watch');

    if (!isYouTube) {
      youtubeContext = null;
    }

    const openDomains = [...new Set(
      allTabs
        .map(t => t.url ? extractDomain(t.url) : null)
        .filter(Boolean)
    )];

    const payload = {
      // Send local device time (no timezone suffix) so admin dashboard shows correct time
      captured_at: (() => { const n = new Date(); return new Date(n.getTime() - n.getTimezoneOffset() * 60000).toISOString().slice(0, 19); })(),
      browser_app: detectBrowser(),
      active_tab_url: activeUrl,
      active_tab_title: activeTab?.title ?? null,
      active_tab_domain: activeDomain,
      tab_count: allTabs.length,
      open_domains: openDomains,
      youtube_video_title: isYouTube ? youtubeContext?.videoTitle : null,
      youtube_channel: isYouTube ? youtubeContext?.channel : null,
      youtube_is_playing: isYouTube ? youtubeContext?.isPlaying : null,
      youtube_progress_pct: isYouTube ? youtubeContext?.progressPct : null,
    };

    const headers = { 'Content-Type': 'application/json' };
    if (machineGuid) {
      headers['X-Machine-GUID'] = machineGuid;
    }

    const body = JSON.stringify(payload);

    // Flush any queued payloads first
    await flushRetryQueue(headers);

    // Send current payload
    try {
      await fetchWithTimeout(API_URL, headers, body);
    } catch (sendErr) {
      // Queue for retry on next poll
      if (_retryQueue.length < MAX_RETRY_QUEUE) {
        _retryQueue.push(body);
      }
      console.warn('[TrackFlow] Send failed, queued for retry:', sendErr?.message ?? sendErr);
    }
  } catch (err) {
    console.error('[TrackFlow] Failed to collect browser context:', err?.message ?? err);
  }
}

// --- Keep service worker alive using offscreen document ---
// MV3 service workers suspend after ~30s. Offscreen doc sends keepalive messages
// which count as "activity" and prevent suspension.
async function ensureOffscreen() {
  try {
    if (typeof chrome.offscreen?.createDocument === 'function') {
      const existing = await chrome.offscreen.hasDocument?.() ?? false;
      if (!existing) {
        await chrome.offscreen.createDocument({
          url: 'offscreen.html',
          reasons: ['BLOBS'],
          justification: 'Keep service worker alive for continuous tab tracking'
        });
      }
    }
  } catch (e) {
    // Offscreen API not available or doc already exists — ignore
  }
}

// Listen for keepalive pings from offscreen doc
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'KEEPALIVE') {
    // Just receiving the message keeps us alive
  }
  // Also handle YouTube context (existing)
  if (msg.type === 'YOUTUBE_CONTEXT') {
    youtubeContext = msg.payload;
  }
});

// Track the active interval so we can restart it after suspension
let _intervalId = null;
function startPolling() {
  if (_intervalId) clearInterval(_intervalId);
  _intervalId = setInterval(collectAndSend, INTERVAL_MS);
}

// 1. Alarms — wake up service worker every minute (Chrome minimum)
//    Also used to restart the setInterval after the worker was suspended
if (chrome.alarms) {
  chrome.alarms.create('trackflow-poll', { periodInMinutes: 1 });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'trackflow-poll') {
      collectAndSend();       // immediate collection after wake
      startPolling();         // restart the 5s interval (may have stopped during suspension)
      ensureOffscreen();      // re-create offscreen doc if it died
    }
  });
}

// 2. setInterval — poll every 5s while service worker is active
startPolling();

// 3. Start offscreen doc to keep us alive
ensureOffscreen();

// 4. Send immediately on startup
collectAndSend();
