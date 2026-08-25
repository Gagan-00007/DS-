// Shared API helper used by every page except checkpoint.js (which is
// unauthenticated — it runs on a door device, not a logged-in user).

const API_BASE = "https://ds-pw3z.onrender.com"; // Render deployment

function getToken() {
  return localStorage.getItem("access_token");
}

function getRole() {
  return localStorage.getItem("role");
}

function getFullName() {
  return localStorage.getItem("full_name");
}

function requireAuth(expectedRole) {
  const token = getToken();
  if (!token) {
    window.location.href = "login.html";
    return false;
  }
  if (expectedRole && getRole() !== expectedRole) {
    // Logged in, but wrong role for this page — send them to login rather
    // than showing a broken/empty dashboard.
    window.location.href = "login.html";
    return false;
  }
  return true;
}

function logout() {
  localStorage.clear();
  window.location.href = "login.html";
}

/**
 * Wrapper around fetch that attaches the JWT and handles 401s by sending
 * the user back to login. Throws on non-OK responses so callers can
 * catch and show an error message.
 */
async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = Object.assign({}, options.headers || {}, {
    Authorization: token ? `Bearer ${token}` : undefined,
  });

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    logout();
    throw new Error("Session expired — please log in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}
