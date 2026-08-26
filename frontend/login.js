document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("error");
  const submitBtn = document.querySelector("#login-form button[type='submit']");
  errorEl.style.display = "none";

  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;

  // /auth/login uses OAuth2PasswordRequestForm on the backend, which
  // expects form-encoded fields named "username" and "password" — not JSON.
  const body = new URLSearchParams();
  body.append("username", email);
  body.append("password", password);

  // Loading state: disable the button immediately, and if the backend is
  // asleep (Render free tier cold start), tell the user after a few
  // seconds so it doesn't look frozen/broken.
  const originalBtnText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = "Signing in...";

  const slowNoticeTimer = setTimeout(() => {
    submitBtn.textContent = "Waking up server (may take ~30s)...";
  }, 3000);

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed.");
    }

    const data = await res.json();
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("role", data.role);
    localStorage.setItem("full_name", data.full_name);

    submitBtn.textContent = "Success — redirecting...";

    if (data.role === "student") {
      window.location.href = "student-dashboard.html";
    } else if (data.role === "teacher") {
      window.location.href = "teacher-dashboard.html";
    } else {
      window.location.href = "admin-dashboard.html";
    }
    // Don't reset the button here — page is navigating away.
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.style.display = "block";
    submitBtn.disabled = false;
    submitBtn.textContent = originalBtnText;
  } finally {
    clearTimeout(slowNoticeTimer);
  }
});
