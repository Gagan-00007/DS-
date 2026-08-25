if (requireAuth("admin")) {
  document.getElementById("user-name").textContent = getFullName();
  loadOverviewStats();
  loadSections();
  loadUsers();
  loadAdminNotifications();
}

// ---------- Overview stats ----------

async function loadOverviewStats() {
  try {
    const [users, sections] = await Promise.all([
      apiFetch("/admin/users"),
      apiFetch("/sections"),
    ]);

    const students = users.filter((u) => u.role === "student").length;
    const teachers = users.filter((u) => u.role === "teacher").length;

    document.getElementById("stat-students").textContent = students;
    document.getElementById("stat-teachers").textContent = teachers;
    document.getElementById("stat-sections").textContent = sections.length;

    // Today's overall attendance %: count today's present/late across all sections
    const today = new Date().toISOString().slice(0, 10);
    let totalToday = 0, presentToday = 0;
    for (const sec of sections) {
      try {
        const records = await apiFetch(`/attendance/section/${sec.id}?on_date=${today}`);
        totalToday += records.length;
        presentToday += records.filter(
          (r) => r.status === "present" || r.status === "marked_present" ||
                 r.status === "late"    || r.status === "marked_late"
        ).length;
      } catch (_) { /* skip sections we can't read */ }
    }
    const pct = totalToday > 0 ? Math.round((presentToday / totalToday) * 100) : "—";
    document.getElementById("stat-attendance").textContent = totalToday > 0 ? `${pct}%` : "—";
  } catch (err) {
    console.error("Failed to load overview stats:", err);
  }
}

// ---------- Sections ----------

let allSections = [];

async function loadSections() {
  try {
    allSections = await apiFetch("/sections");
    renderSections(allSections);
  } catch (err) {
    document.getElementById("sections-empty").textContent = `Error: ${err.message}`;
    document.getElementById("sections-empty").style.display = "block";
  }
}

function renderSections(sections) {
  const body = document.getElementById("sections-body");
  const empty = document.getElementById("sections-empty");

  if (!sections || sections.length === 0) {
    body.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";
  body.innerHTML = sections
    .map((s) => `
      <tr>
        <td>${s.id}</td>
        <td>${s.name || "—"}</td>
        <td>${s.room || "—"}</td>
        <td>${s.teacher_name || "—"}</td>
        <td>${s.student_count !== undefined ? s.student_count : "—"}</td>
      </tr>
    `)
    .join("");
}

function openAddSectionModal() {
  document.getElementById("new-section-name").value = "";
  document.getElementById("new-section-room").value = "";
  document.getElementById("add-section-error").style.display = "none";
  document.getElementById("add-section-modal").style.display = "flex";
}

function closeAddSectionModal() {
  document.getElementById("add-section-modal").style.display = "none";
}

async function submitAddSection() {
  const name = document.getElementById("new-section-name").value.trim();
  const room = document.getElementById("new-section-room").value.trim();
  const errorEl = document.getElementById("add-section-error");

  if (!name) {
    errorEl.textContent = "Section name is required.";
    errorEl.style.display = "block";
    return;
  }

  try {
    await apiFetch("/sections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, room }),
    });
    closeAddSectionModal();
    loadSections();
    loadOverviewStats();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.style.display = "block";
  }
}

// ---------- Users ----------

let allUsers = [];

async function loadUsers() {
  try {
    allUsers = await apiFetch("/admin/users");
    renderUsers(allUsers);
  } catch (err) {
    document.getElementById("users-empty").textContent = `Error: ${err.message}`;
    document.getElementById("users-empty").style.display = "block";
  }
}

function filterUsers() {
  const role = document.getElementById("role-filter").value;
  const filtered = role ? allUsers.filter((u) => u.role === role) : allUsers;
  renderUsers(filtered);
}

function renderUsers(users) {
  const body = document.getElementById("users-body");
  const empty = document.getElementById("users-empty");

  if (!users || users.length === 0) {
    body.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";
  body.innerHTML = users
    .map((u) => `
      <tr>
        <td>${u.full_name || u.name || "—"}</td>
        <td>${u.email}</td>
        <td><span class="status-badge status-${u.role === "teacher" ? "late" : u.role === "admin" ? "absent" : "present"}">${u.role}</span></td>
      </tr>
    `)
    .join("");
}

// ---------- System notifications ----------

async function loadAdminNotifications() {
  try {
    const notifs = await apiFetch("/notifications/all");
    const list = document.getElementById("admin-notifs-list");
    const empty = document.getElementById("admin-notifs-empty");

    if (!notifs || notifs.length === 0) {
      empty.style.display = "block";
      return;
    }
    empty.style.display = "none";
    list.innerHTML = notifs
      .map((n) => `
        <div class="notif-item ${n.is_read ? "" : "unread"}">
          <div>${n.message}</div>
          <div class="meta">${new Date(n.created_at).toLocaleString()}</div>
        </div>
      `)
      .join("");
  } catch (err) {
    console.error("Failed to load admin notifications:", err);
  }
}
