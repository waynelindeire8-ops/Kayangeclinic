const API_BASE = '';

function getToken() {
    return localStorage.getItem('token');
}

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('user') || '{}');
    } catch {
        return {};
    }
}

async function fetchWithAuth(url, options = {}) {
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers
    };

    if (!options.body) {
        delete headers['Content-Type'];
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
