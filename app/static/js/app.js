const API_BASE = '';

function safeLocalStorage(key, value) {
    try {
        if (value === undefined) {
            return localStorage.getItem(key);
        } else if (value === null) {
            localStorage.removeItem(key);
        } else {
            localStorage.setItem(key, value);
        }
    } catch (e) {
        console.warn('localStorage error:', e);
        // Don't clear localStorage on quota exceeded - just log and continue
        // This prevents unintentional logout when storage is full
        return null;
    }
}

function getToken() {
    return safeLocalStorage('token');
}

function getUser() {
    try {
        return JSON.parse(safeLocalStorage('user') || '{}');
    } catch {
        return {};
    }
}

async function fetchWithAuth(url, options = {}) {
    const token = getToken();
    const isFormData = options.body instanceof FormData;
    const headers = {
        'Authorization': `Bearer ${token}`,
        ...options.headers
    };

    if (!isFormData) {
        headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(url, {
        ...options,
        headers
    });

    if (res.status === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/auth/login';
        return res;
    }

    return res;
}

if (window.location.pathname !== '/auth/login' && !getToken()) {
    window.location.href = '/auth/login';
}
