if (requireAuth("student")) {
  document.getElementById("user-name").textContent = getFullName();
  loadAttendance();
}

async function loadAttendance() {
  try {
    const records = await apiFetch("/attendance/me");
    const body = document.getElementById("attendance-body");
    const emptyMsg = document.getElementById("empty-msg");

    // Populate summary stats from the fetched records
    updateStats(records);

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

function updateStats(records) {
  const now = new Date();
  const thisMonth = records.filter((r) => {
    const d = new Date(r.date);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  });

  const present = thisMonth.filter((r) => r.status === "present" || r.status === "marked_present").length;
  const late    = thisMonth.filter((r) => r.status === "late" || r.status === "marked_late" || r.status === "left_early" || r.status === "marked_left_early").length;
  const absent  = thisMonth.filter((r) => r.status === "absent").length;

  document.getElementById("stat-total").textContent   = thisMonth.length;
  document.getElementById("stat-present").textContent = present;
  document.getElementById("stat-late").textContent    = late;
  document.getElementById("stat-absent").textContent  = absent;
}
