// Offscreen document keeps the service worker alive by sending periodic messages
// This ensures the background.js polling never stops
setInterval(() => {
  chrome.runtime.sendMessage({ type: 'KEEPALIVE' }).catch(() => {});
}, 4000);
