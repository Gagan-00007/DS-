if (requireAuth("teacher")) {
  document.getElementById("user-name").textContent = getFullName();
  loadSections();
  loadNotifications();
  loadSectionAttendance();
}

async function loadSections() {
  try {
    const sections = await apiFetch("/sections");
    const sel = document.getElementById("section-id-input");
    if (!sections || sections.length === 0) return;
    sel.innerHTML = sections
      .map((s) => `<option value="${s.id}">${s.name || "Section " + s.id}</option>`)
      .join("");
  } catch (_) {
    // non-critical — keep the default option
  }
}

let activeCorrectionRecordId = null;

// ---------- Notifications ----------

async function loadNotifications() {
  try {
    const notifs = await apiFetch("/notifications/me");
    const list = document.getElementById("notifications-list");
    const empty = document.getElementById("notif-empty");

    if (notifs.length === 0) {
      empty.style.display = "block";
      list.innerHTML = "";
      return;
    }
    empty.style.display = "none";

    list.innerHTML = notifs
      .map((n) => `
        <div class="notif-item ${n.is_read ? "" : "unread"}">
          <div>${n.message}</div>
          <div class="meta">
            ${new Date(n.created_at).toLocaleString()}
            ${!n.is_read ? `<button class="secondary" style="margin-left:10px; padding:3px 10px; font-size:12px;" onclick="markNotifRead(${n.id})">Mark read</button>` : ""}
          </div>
        </div>
      `)
      .join("");
  } catch (err) {
    console.error("Failed to load notifications:", err);
  }
}

async function markNotifRead(id) {
  try {
    await apiFetch(`/notifications/${id}/read`, { method: "POST" });
    loadNotifications();
  } catch (err) {
    alert(`Could not mark notification read: ${err.message}`);
  }
}

async function triggerMonthlyCheck() {
  const resultEl = document.getElementById("monthly-check-result");
  resultEl.textContent = "Running...";
  try {
    const result = await apiFetch("/notifications/run-monthly-check", { method: "POST" });
    resultEl.textContent = `Done — ${result.notifications_created} notification(s) created.`;
    loadNotifications();
  } catch (err) {
    resultEl.textContent = `Error: ${err.message}`;
  }
}

// ---------- Attendance table ----------

async function loadSectionAttendance() {
  const sectionId = document.getElementById("section-id-input").value;
  const date = document.getElementById("date-input").value;
  const body = document.getElementById("attendance-body");
  const emptyMsg = document.getElementById("empty-msg");
  emptyMsg.style.display = "none";
  body.innerHTML = "";

  if (!sectionId) return;

  let path = `/attendance/section/${sectionId}`;
  if (date) path += `?on_date=${date}`;

  try {
    const records = await apiFetch(path);

    if (records.length === 0) {
      emptyMsg.textContent = "No attendance records for this section/date.";
      emptyMsg.style.display = "block";
      return;
    }

    body.innerHTML = records
      .map((r) => `
        <tr>
          <td>${r.student_name}</td>
          <td>${new Date(r.date).toLocaleDateString()}</td>
          <td>
            <span class="status-badge status-${r.status}">${r.status.replace(/_/g, " ")}</span>
            ${r.is_corrected ? '<span class="corrected-tag">corrected</span>' : ""}
          </td>
          <td>${r.entry_time ? new Date(r.entry_time).toLocaleTimeString() : "—"}</td>
          <td>${r.exit_time ? new Date(r.exit_time).toLocaleTimeString() : "—"}</td>
          <td>${r.confidence !== null && r.confidence !== undefined ? r.confidence.toFixed(2) : "—"}</td>
          <td><button class="secondary" onclick="openCorrectionModal(${r.id})">Correct</button></td>
        </tr>
      `)
      .join("");
  } catch (err) {
    emptyMsg.textContent = `Error loading attendance: ${err.message}`;
    emptyMsg.style.display = "block";
  }
}

// ---------- Correction modal ----------

function openCorrectionModal(recordId) {
  activeCorrectionRecordId = recordId;
  document.getElementById("correction-reason").value = "";
  document.getElementById("correction-error").style.display = "none";
  document.getElementById("correction-modal").style.display = "flex";
}

function closeCorrectionModal() {
  document.getElementById("correction-modal").style.display = "none";
  activeCorrectionRecordId = null;
}

async function submitCorrection() {
  const status = document.getElementById("correction-status").value;
  const reason = document.getElementById("correction-reason").value;
  const errorEl = document.getElementById("correction-error");

  if (!reason.trim()) {
    errorEl.textContent = "A reason is required.";
    errorEl.style.display = "block";
    return;
  }

  try {
    await apiFetch(`/attendance/${activeCorrectionRecordId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_status: status, reason }),
    });
    closeCorrectionModal();
    loadSectionAttendance();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.style.display = "block";
  }
}
