if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/js/sw.js')
        .then(() => console.log('Service Worker registered for offline support'))
        .catch(err => console.error('Service Worker registration failed:', err));
}
