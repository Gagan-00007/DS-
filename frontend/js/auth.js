// Auth module — used by login.html. Wraps the same /auth/login endpoint
// the rest of the app already uses (OAuth2PasswordRequestForm on the
// backend), but the "username" field now carries a USN, Teacher ID, or
// Admin ID instead of an email — the backend was updated to match
// (see BACKEND_AUTH_PATCH.md).

const Auth = {
  /**
   * @param {string} username - USN / Teacher ID / Admin ID
   * @param {string} password
   * @param {string} roleHint - "student" | "teacher" | "admin" — UI hint only,
   *   the actual role used for redirect comes from the server's response,
   *   since that's the source of truth (a mistyped role toggle shouldn't matter).
   * @returns {Promise<{success: boolean, user: {role: string, full_name: string}}>}
   */
  async login(username, password, roleHint) {
    const body = new URLSearchParams();
    body.append("username", username);
    body.append("password", password);

    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed. Please check your credentials.");
    }

    const data = await res.json();
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("role", data.role);
    localStorage.setItem("full_name", data.full_name);

    return { success: true, user: { role: data.role, full_name: data.full_name } };
  },
};
