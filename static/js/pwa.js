// Store the client's timezone offset in minutes so the server can serve timezone-corrected dates
const timezoneOffset = new Date().getTimezoneOffset();
document.cookie = `timezone_offset=${timezoneOffset}; path=/; max-age=31536000; SameSite=Lax`;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then((registration) => {
        console.log('ServiceWorker registration successful with scope: ', registration.scope);
      })
      .catch((err) => {
        console.log('ServiceWorker registration failed: ', err);
      });
  });
}
