// TrackFlow — YouTube Content Script
// Injected on youtube.com pages to extract video metadata

function getYouTubeContext() {
  try {
    const video = document.querySelector('video');
    if (!video) return null;

    const titleEl =
      document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string') ||
      document.querySelector('yt-dynlink h1 .style-scope') ||
      document.querySelector('#above-the-fold #title h1') ||
      document.querySelector('h1.title');

    const videoTitle = titleEl?.textContent?.trim() ?? document.title.replace(' - YouTube', '').trim();

    const channelEl =
      document.querySelector('#channel-name a') ||
      document.querySelector('ytd-channel-name a');
    const channel = channelEl?.textContent?.trim() ?? null;

    const isPlaying = !video.paused && !video.ended;
    const progressPct = video.duration > 0
      ? Math.round((video.currentTime / video.duration) * 100)
      : null;

    return { videoTitle, channel, isPlaying, progressPct };
  } catch {
    return null;
  }
}

let pollInterval = null;

function sendContext() {
  try {
    // Check if extension context is still valid
    if (typeof chrome === 'undefined' || !chrome.runtime?.id) {
      cleanup();
      return;
    }

    const ctx = getYouTubeContext();
    if (ctx) {
      chrome.runtime.sendMessage({ type: 'YOUTUBE_CONTEXT', payload: ctx });
    }
  } catch (e) {
    // Background context likely gone or invalidated
    cleanup();
  }
}

function cleanup() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
  document.removeEventListener('play', sendContext, true);
  document.removeEventListener('pause', sendContext, true);
}

// Start polling
sendContext();
pollInterval = setInterval(sendContext, 4000);

// Also send on video events
document.addEventListener('play', sendContext, true);
document.addEventListener('pause', sendContext, true);
