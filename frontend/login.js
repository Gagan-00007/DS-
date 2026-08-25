document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("error");
  errorEl.style.display = "none";

  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;

  // /auth/login uses OAuth2PasswordRequestForm on the backend, which
  // expects form-encoded fields named "username" and "password" — not JSON.
  const body = new URLSearchParams();
  body.append("username", email);
  body.append("password", password);

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

    if (data.role === "student") {
      window.location.href = "student-dashboard.html";
    } else if (data.role === "teacher") {
      window.location.href = "teacher-dashboard.html";
    } else {
      // admin
      window.location.href = "admin-dashboard.html";
    }
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.style.display = "block";
  }
});
