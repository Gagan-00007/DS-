if (requireAuth("student")) {
  document.getElementById("user-name").textContent = getFullName();
  loadAttendance();
}

async function loadAttendance() {
  try {
    const records = await apiFetch("/attendance/me");
    const body = document.getElementById("attendance-body");
    const emptyMsg = document.getElementById("empty-msg");

    if (records.length === 0) {
      emptyMsg.style.display = "block";
      return;
    }

    body.innerHTML = records
      .map((r) => `
        <tr>
          <td>${new Date(r.date).toLocaleDateString()}</td>
          <td>
            <span class="status-badge status-${r.status}">${r.status.replace(/_/g, " ")}</span>
            ${r.is_corrected ? '<span class="corrected-tag">corrected</span>' : ""}
          </td>
          <td>${r.entry_time ? new Date(r.entry_time).toLocaleTimeString() : "—"}</td>
          <td>${r.exit_time ? new Date(r.exit_time).toLocaleTimeString() : "—"}</td>
        </tr>
      `)
      .join("");
  } catch (err) {
    document.getElementById("empty-msg").textContent = `Error loading attendance: ${err.message}`;
    document.getElementById("empty-msg").style.display = "block";
  }
}
