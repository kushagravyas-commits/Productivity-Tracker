// TrackFlow Browser Context — Background Service Worker
// Polls active tab + all tabs every 5s and sends to local backend

const API_URL = 'http://127.0.0.1:8000/api/v1/context/browser';
const INTERVAL_MS = 5000;

// YouTube context is stored here when the content script messages us
let youtubeContext = null;

// Listen for messages from the YouTube content script
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'YOUTUBE_CONTEXT') {
    youtubeContext = msg.payload;
  }
});

function detectBrowser() {
  // Check navigator.userAgentData first (more reliable for Brave/Edge)
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

async function collectAndSend() {
  try {
    // Get all tabs and the active tab
    const [allTabs, activeTabs] = await Promise.all([
      chrome.tabs.query({}),
      chrome.tabs.query({ active: true, currentWindow: true }),
    ]);

    const activeTab = activeTabs[0] ?? null;
    const activeUrl = activeTab?.url ?? null;
    const activeDomain = activeUrl ? extractDomain(activeUrl) : null;
    const isYouTube = activeUrl?.includes('youtube.com/watch');

    // If we've moved away from YouTube, clear the cached context
    if (!isYouTube) {
      youtubeContext = null;
    }

    // Collect titles of all open tabs (deduplicated domains for summary)
    const openDomains = [...new Set(
      allTabs
        .map(t => t.url ? extractDomain(t.url) : null)
        .filter(Boolean)
    )];

    const payload = {
      captured_at: new Date().toISOString(),
      browser_app: detectBrowser(),
      active_tab_url: activeUrl,
      active_tab_title: activeTab?.title ?? null,
      active_tab_domain: activeDomain,
      tab_count: allTabs.length,
      open_domains: openDomains,
      // YouTube-specific (only if active)
      youtube_video_title: isYouTube ? youtubeContext?.videoTitle : null,
      youtube_channel: isYouTube ? youtubeContext?.channel : null,
      youtube_is_playing: isYouTube ? youtubeContext?.isPlaying : null,
      youtube_progress_pct: isYouTube ? youtubeContext?.progressPct : null,
    };

    await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    // Silently fail — never disrupt browsing
  }
}

// Poll on interval using alarms (MV3 service workers can't use setInterval reliably)
if (chrome.alarms) {
  chrome.alarms.create('trackflow-poll', { periodInMinutes: 5 / 60 }); // every 5s

  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'trackflow-poll') {
      collectAndSend();
    }
  });
} else {
  console.error("TrackFlow: 'alarms' permission missing. Please reload extension from manifest.json.");
  // Fallback for development (less reliable)
  setInterval(collectAndSend, INTERVAL_MS);
}

// Also send immediately on startup
collectAndSend();
