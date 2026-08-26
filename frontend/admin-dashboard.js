if (requireAuth("admin")) {
  document.getElementById("user-name").textContent = getFullName();
  loadStudents();
  loadSections();
  loadTeachers();
  loadTimetable();
  loadAnalytics();
  populateReportSectionDropdown();
  searchAuditLogs();
}

// ---------- Students ----------

async function loadStudents() {
  try {
    const students = await apiFetch("/admin/students");
    const body = document.getElementById("students-body");
    const empty = document.getElementById("students-empty");
    if (students.length === 0) {
      empty.style.display = "block";
      body.innerHTML = "";
      return;
    }
    empty.style.display = "none";
    body.innerHTML = students
      .map((s) => `
        <tr>
          <td>${s.full_name}</td>
          <td>${s.email}</td>
          <td>${s.section}</td>
          <td>${s.has_face ? "✅ Yes" : "❌ No"}</td>
        </tr>
      `)
      .join("");
  } catch (err) {
    console.error("Failed to load students:", err);
  }
}

// ---------- Sections ----------

async function loadSections() {
  try {
    const sections = await apiFetch("/admin/sections");
    document.getElementById("sections-body").innerHTML = sections
      .map((s) => `<tr><td>${s.id}</td><td>${s.name}</td></tr>`)
      .join("");

    // Populate section dropdowns used elsewhere on the page.
    const options = sections.map((s) => `<option value="${s.id}">${s.name}</option>`).join("");
    document.getElementById("tt-section").innerHTML = options;
    document.getElementById("enroll-section").innerHTML = options;
    document.getElementById("report-section").innerHTML = `<option value="">All Sections</option>${options}`;
  } catch (err) {
    console.error("Failed to load sections:", err);
  }
}

async function createSection() {
  const name = document.getElementById("new-section-name").value.trim();
  if (!name) return;
  try {
    await apiFetch("/admin/sections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    document.getElementById("new-section-name").value = "";
    loadSections();
  } catch (err) {
    alert(`Could not create section: ${err.message}`);
  }
}

// ---------- Teachers ----------

async function loadTeachers() {
  try {
    const teachers = await apiFetch("/admin/teachers");
    document.getElementById("teachers-body").innerHTML = teachers
      .map((t) => `<tr><td>${t.full_name}</td><td>${t.email}</td></tr>`)
      .join("");
    document.getElementById("tt-teacher").innerHTML = teachers
      .map((t) => `<option value="${t.id}">${t.full_name}</option>`)
      .join("");
  } catch (err) {
    console.error("Failed to load teachers:", err);
  }
}

async function createTeacher() {
  const full_name = document.getElementById("new-teacher-name").value.trim();
  const email = document.getElementById("new-teacher-email").value.trim();
  const password = document.getElementById("new-teacher-password").value.trim() || "teacher123";
  if (!full_name || !email) return;
  try {
    await apiFetch("/admin/teachers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name, email, password }),
    });
    document.getElementById("new-teacher-name").value = "";
    document.getElementById("new-teacher-email").value = "";
    loadTeachers();
  } catch (err) {
    alert(`Could not create teacher: ${err.message}`);
  }
}

// ---------- Timetable ----------

async function loadTimetable() {
  try {
    const entries = await apiFetch("/admin/timetable");
    const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    document.getElementById("timetable-body").innerHTML = entries
      .map((e) => `
        <tr>
          <td>${e.section}</td><td>${e.teacher}</td><td>${e.subject}</td><td>${e.room}</td>
          <td>${dayNames[e.day_of_week] || e.day_of_week}</td>
          <td>${e.start_time}</td><td>${e.end_time}</td>
        </tr>
      `)
      .join("");
  } catch (err) {
    console.error("Failed to load timetable:", err);
  }
}

async function createTimetableEntry() {
  const section_id = parseInt(document.getElementById("tt-section").value, 10);
  const teacher_id = parseInt(document.getElementById("tt-teacher").value, 10);
  const subject = document.getElementById("tt-subject").value.trim();
  const room = document.getElementById("tt-room").value.trim();
  const day_of_week = parseInt(document.getElementById("tt-day").value, 10);
  const start_time = document.getElementById("tt-start").value; // "HH:MM"
  const end_time = document.getElementById("tt-end").value;

  if (!section_id || !teacher_id || !subject || !room || !start_time || !end_time) {
    alert("Please fill in all timetable fields.");
    return;
  }

  try {
    await apiFetch("/admin/timetable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        section_id, teacher_id, subject, room, day_of_week, start_time, end_time,
      }),
    });
    document.getElementById("tt-subject").value = "";
    document.getElementById("tt-room").value = "";
    loadTimetable();
  } catch (err) {
    alert(`Could not create timetable slot: ${err.message}`);
  }
}

// ---------- Enrollment modal ----------

let enrollStream = null;
let capturedFrames = []; // base64 strings, webcam mode only
let activeEnrollTab = "upload";

function openEnrollModal() {
  document.getElementById("enroll-name").value = "";
  document.getElementById("enroll-email").value = "";
  document.getElementById("enroll-password").value = "student123";
  document.getElementById("enroll-photos").value = "";
  document.getElementById("enroll-error").style.display = "none";
  capturedFrames = [];
  updateCaptureCount();
  switchEnrollTab("upload");
  document.getElementById("enroll-modal").style.display = "flex";
}

function closeEnrollModal() {
  stopEnrollCamera();
  document.getElementById("enroll-modal").style.display = "none";
}

function switchEnrollTab(tab) {
  activeEnrollTab = tab;
  document.getElementById("enroll-tab-upload").style.display = tab === "upload" ? "block" : "none";
  document.getElementById("enroll-tab-webcam").style.display = tab === "webcam" ? "block" : "none";
  document.getElementById("tab-btn-upload").classList.toggle("active", tab === "upload");
  document.getElementById("tab-btn-webcam").classList.toggle("active", tab === "webcam");
  if (tab !== "webcam") stopEnrollCamera();
}

async function startEnrollCamera() {
  try {
    enrollStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    document.getElementById("enroll-video").srcObject = enrollStream;
  } catch (err) {
    showEnrollError(`Camera error: ${err.message}`);
  }
}

function stopEnrollCamera() {
  if (enrollStream) {
    enrollStream.getTracks().forEach((t) => t.stop());
    enrollStream = null;
  }
}

function captureEnrollFrame() {
  const video = document.getElementById("enroll-video");
  const canvas = document.getElementById("enroll-canvas");
  const w = video.videoWidth, h = video.videoHeight;
  if (!w || !h) {
    showEnrollError("Start the camera first.");
    return;
  }
  canvas.width = w;
  canvas.height = h;
  canvas.getContext("2d").drawImage(video, 0, 0, w, h);
  const b64 = canvas.toDataURL("image/jpeg", 0.9).split(",")[1];
  capturedFrames.push(b64);
  updateCaptureCount();
}

function updateCaptureCount() {
  document.getElementById("enroll-capture-count").textContent = `${capturedFrames.length} photo(s) captured`;
}

function showEnrollError(message) {
  const el = document.getElementById("enroll-error");
  el.textContent = message;
  el.style.display = "block";
}

async function submitEnrollment() {
  const full_name = document.getElementById("enroll-name").value.trim();
  const email = document.getElementById("enroll-email").value.trim();
  const section_id = document.getElementById("enroll-section").value;
  const password = document.getElementById("enroll-password").value.trim() || "student123";
  const errorEl = document.getElementById("enroll-error");
  errorEl.style.display = "none";

  if (!full_name || !email || !section_id) {
    showEnrollError("Name, email, and section are required.");
    return;
  }

  const submitBtn = document.getElementById("enroll-submit-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "Enrolling...";

  try {
    if (activeEnrollTab === "upload") {
      const fileInput = document.getElementById("enroll-photos");
      if (!fileInput.files || fileInput.files.length === 0) {
        throw new Error("Please choose at least one photo.");
      }
      const formData = new FormData();
      formData.append("email", email);
      formData.append("full_name", full_name);
      formData.append("section_id", section_id);
      formData.append("password", password);
      for (const file of fileInput.files) formData.append("photos", file);

      await apiFetch("/admin/students/enroll-upload", { method: "POST", body: formData });
    } else {
      if (capturedFrames.length === 0) {
        throw new Error("Please capture at least one photo from the webcam.");
      }
      await apiFetch("/admin/students/enroll-webcam", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email, full_name, section_id: parseInt(section_id, 10), password,
          frames_base64: capturedFrames,
        }),
      });
    }

    closeEnrollModal();
    loadStudents();
  } catch (err) {
    showEnrollError(err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Enroll";
  }
}

// ---------- Analytics ----------

let trendChartInstance = null;

async function loadAnalytics() {
  try {
    const data = await apiFetch("/admin/analytics/summary");

    document.getElementById("analytics-stats").innerHTML = `
      ${statCard("Students", data.total_students)}
      ${statCard("Teachers", data.total_teachers)}
      ${statCard("Sections", data.total_sections)}
      ${statCard("Overall Attendance", `${data.overall_attendance_rate}%`)}
    `;

    document.getElementById("section-breakdown-body").innerHTML = data.section_breakdown
      .map((s) => `<tr><td>${s.section}</td><td>${s.total_records}</td><td>${s.attendance_rate}%</td></tr>`)
      .join("");

    renderTrendChart(data.trend_last_7_days);
  } catch (err) {
    console.error("Failed to load analytics:", err);
  }
}

function statCard(label, value) {
  return `
    <div class="card" style="flex:1; min-width:140px; text-align:center; margin-bottom:0;">
      <div style="font-size:28px; font-weight:700; color: var(--accent);">${value}</div>
      <div style="font-size:12px; color: var(--text-dim); text-transform:uppercase; letter-spacing:0.04em; margin-top:4px;">${label}</div>
    </div>
  `;
}

function renderTrendChart(trend) {
  const ctx = document.getElementById("trend-chart").getContext("2d");
  const labels = trend.map((t) => t.date.slice(5)); // "MM-DD"
  const values = trend.map((t) => t.attendance_rate);

  if (trendChartInstance) {
    trendChartInstance.data.labels = labels;
    trendChartInstance.data.datasets[0].data = values;
    trendChartInstance.update();
    return;
  }

  trendChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Attendance Rate (%)",
        data: values,
        borderColor: "#4f7cff",
        backgroundColor: "rgba(79,124,255,0.15)",
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#9aa4bf" } } },
      scales: {
        x: { ticks: { color: "#9aa4bf" }, grid: { color: "#2e3852" } },
        y: { ticks: { color: "#9aa4bf" }, grid: { color: "#2e3852" }, min: 0, max: 100 },
      },
    },
  });
}

// ---------- Reports & export ----------

async function populateReportSectionDropdown() {
  try {
    const sections = await apiFetch("/admin/sections");
    const options = sections.map((s) => `<option value="${s.id}">${s.name}</option>`).join("");
    document.getElementById("report-section").innerHTML = `<option value="">All Sections</option>${options}`;
  } catch (err) {
    console.error("Failed to load sections for report filter:", err);
  }
}

async function exportAttendanceCsv() {
  const sectionId = document.getElementById("report-section").value;
  const dateFrom = document.getElementById("report-date-from").value;
  const dateTo = document.getElementById("report-date-to").value;
  const statusEl = document.getElementById("report-status");
  statusEl.textContent = "Generating CSV...";

  const params = new URLSearchParams();
  if (sectionId) params.append("section_id", sectionId);
  if (dateFrom) params.append("date_from", dateFrom);
  if (dateTo) params.append("date_to", dateTo);

  try {
    const token = getToken();
    const res = await fetch(`${API_BASE}/admin/reports/attendance/export?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Export failed (${res.status})`);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "attendance_report.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    statusEl.textContent = "Downloaded.";
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
}

// ---------- Audit log search ----------

async function searchAuditLogs() {
  const studentName = document.getElementById("audit-student-name").value.trim();
  const status = document.getElementById("audit-status").value;
  const dateFrom = document.getElementById("audit-date-from").value;
  const dateTo = document.getElementById("audit-date-to").value;

  const params = new URLSearchParams();
  if (studentName) params.append("student_name", studentName);
  if (status) params.append("status", status);
  if (dateFrom) params.append("date_from", dateFrom);
  if (dateTo) params.append("date_to", dateTo);

  const body = document.getElementById("audit-logs-body");
  const empty = document.getElementById("audit-logs-empty");

  try {
    const logs = await apiFetch(`/admin/audit-logs?${params.toString()}`);
    if (logs.length === 0) {
      body.innerHTML = "";
      empty.style.display = "block";
      return;
    }
    empty.style.display = "none";
    body.innerHTML = logs
      .map((l) => `
        <tr>
          <td>${l.student_name}</td>
          <td>${l.changed_by}</td>
          <td><span class="status-badge status-${l.previous_status}">${l.previous_status.replace(/_/g, " ")}</span></td>
          <td><span class="status-badge status-${l.new_status}">${l.new_status.replace(/_/g, " ")}</span></td>
          <td>${l.reason}</td>
          <td>${new Date(l.changed_at).toLocaleString()}</td>
        </tr>
      `)
      .join("");
  } catch (err) {
    empty.textContent = `Error loading audit logs: ${err.message}`;
    empty.style.display = "block";
  }
}

