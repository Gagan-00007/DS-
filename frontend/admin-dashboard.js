/* ===== SmartFace AI — Admin Dashboard JS ===== */

// ---- Auth guard ----
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');
if (!token || role !== 'admin') { window.location.href = 'login.html'; }

const fullName = localStorage.getItem('fullName') || 'Admin';
document.getElementById('adminName').textContent = fullName;
document.getElementById('welcomeName').textContent = fullName;
document.getElementById('adminAvatar').textContent = fullName.split(' ').map(w=>w[0]).join('').substring(0,2).toUpperCase();

// ---- Theme ----
function initTheme() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeIcon(saved);
}
function updateThemeIcon(theme) {
  const icon = document.getElementById('themeIcon');
  if (theme === 'light') {
    icon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>';
  } else {
    icon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>';
  }
}
document.getElementById('themeToggle').addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
});
initTheme();

// ---- Live clock ----
function updateClock() {
  const now = new Date();
  document.getElementById('liveClock').textContent = now.toLocaleTimeString('en-US', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
setInterval(updateClock, 1000);
updateClock();

// ---- Logout ----
function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  localStorage.removeItem('fullName');
  window.location.href = 'login.html';
}

// ---- Tab switching ----
function switchTab(tabName) {
  document.querySelectorAll('.sidebar-item').forEach(el => el.classList.toggle('active', el.dataset.tab === tabName));
  document.querySelectorAll('.tab-panel').forEach(el => el.classList.toggle('active', el.id === 'tab-' + tabName));
  window.location.hash = tabName;
  // Load data for tab
  if (tabName === 'dashboard') loadDashboard();
  if (tabName === 'students') loadStudents();
  if (tabName === 'teachers') loadTeachers();
  if (tabName === 'attendance') loadAttendanceRecords();
  if (tabName === 'analytics') loadAnalytics();
  if (tabName === 'reports') loadDeptDropdowns();
  if (tabName === 'system') loadSystemAudit();
}

document.querySelectorAll('.sidebar-item').forEach(el => {
  el.addEventListener('click', () => switchTab(el.dataset.tab));
});

// Hash routing
const initialTab = window.location.hash.replace('#', '') || 'dashboard';
switchTab(initialTab);

// ---- API helper ----
function api(path, opts = {}) {
  const headers = { 'Authorization': 'Bearer ' + token, ...(opts.headers || {}) };
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  return fetch(API_BASE + path, { ...opts, headers }).then(r => {
    if (r.status === 401) { logout(); throw new Error('Unauthorized'); }
    return r;
  });
}

// ---- Load departments into all dropdowns ----
let departments = [];
async function loadDeptDropdowns() {
  if (departments.length) return;
  try {
    const r = await api('/admin/departments');
    departments = await r.json();
    ['regDept', 'studentDeptFilter', 'attDeptFilter', 'rptDept'].forEach(id => {
      const sel = document.getElementById(id);
      if (!sel) return;
      const isFilter = id !== 'regDept';
      if (isFilter && !sel.querySelector('option[value=""]')) {
        sel.innerHTML = '<option value="">All Departments</option>';
      } else if (!isFilter) {
        sel.innerHTML = '';
      }
      departments.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.id; opt.textContent = d.name;
        sel.appendChild(opt);
      });
    });
  } catch(e) { console.error('Failed to load departments', e); }
}
loadDeptDropdowns();

// ===== DASHBOARD TAB =====
async function loadDashboard() {
  try {
    const [kpiRes, summaryRes, actRes] = await Promise.all([
      api('/admin/dashboard/kpis'), api('/admin/analytics/summary'), api('/admin/activity-stream')
    ]);
    const kpis = await kpiRes.json();
    const summary = await summaryRes.json();
    const activity = await actRes.json();

    // KPI cards
    document.getElementById('kpiGrid').innerHTML = [
      kpiCard('👥', 'blue', kpis.total_students, 'Total Students'),
      kpiCard('🧑‍🏫', 'green', kpis.total_teachers, 'Registered Teachers'),
      kpiCard('📋', 'amber', kpis.todays_logs, "Today's Logs"),
      kpiCard('✅', 'green', kpis.present_today, 'Present Today'),
      kpiCard('❌', 'red', kpis.absent_today, 'Absent Today'),
      kpiCard('📊', 'blue', kpis.attendance_rate + '%', 'Attendance Rate'),
    ].join('');

    // Department bars
    const totalStudents = summary.total_students || 1;
    document.getElementById('deptBars').innerHTML = summary.department_breakdown.map(d =>
      `<div class="dept-bar">
        <div class="dept-bar-label"><span>${d.department}</span><span>${d.student_count} students (${d.attendance_rate}%)</span></div>
        <div class="dept-bar-track"><div class="dept-bar-fill" style="width:${(d.student_count/totalStudents)*100}%"></div></div>
      </div>`
    ).join('');

    // Activity stream
    document.getElementById('activityBody').innerHTML = activity.slice(0,20).map(e =>
      `<tr><td style="font-size:12px;color:var(--text-dim);white-space:nowrap;">${fmtTime(e.timestamp)}</td><td>${e.user}</td><td><span class="status-badge" style="background:var(--accent-light);color:var(--accent);">${e.action}</span></td><td style="font-size:13px;">${e.details||''}</td></tr>`
    ).join('') || '<tr><td colspan="4" style="color:var(--text-dim);">No activity yet</td></tr>';
  } catch(e) { console.error('Dashboard load error', e); }
}

function kpiCard(icon, color, value, label) {
  return `<div class="kpi-card"><div class="kpi-icon ${color}">${icon}</div><div class="kpi-value">${value}</div><div class="kpi-label">${label}</div></div>`;
}

function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-US', {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}

// ===== STUDENT DIRECTORY TAB =====
async function loadStudents() {
  const search = document.getElementById('studentSearch')?.value || '';
  const dept = document.getElementById('studentDeptFilter')?.value || '';
  let url = '/admin/students?';
  if (search) url += 'search=' + encodeURIComponent(search) + '&';
  if (dept) url += 'department_id=' + dept + '&';
  try {
    const r = await api(url);
    const students = await r.json();
    document.getElementById('studentsBody').innerHTML = students.map(s =>
      `<tr>
        <td>${s.username}</td><td>${s.full_name}</td><td>${s.department}</td>
        <td>${s.academic_year||'—'} / ${s.section||'—'}</td>
        <td>${s.encodings_count}</td><td>${s.samples_count}</td>
        <td>
          <button class="secondary" style="font-size:12px;padding:4px 8px;" onclick="viewSamples(${s.id},'${s.full_name}')">Samples</button>
          <button class="secondary" style="font-size:12px;padding:4px 8px;margin-left:4px;" onclick="deleteStudent(${s.id},'${s.full_name}')">Delete</button>
        </td>
      </tr>`
    ).join('') || '<tr><td colspan="7" style="color:var(--text-dim);">No students found</td></tr>';
  } catch(e) { console.error('Load students error', e); }
}

async function viewSamples(studentId, name) {
  try {
    const r = await api('/admin/students/' + studentId + '/samples');
    const samples = await r.json();
    const grid = samples.map(s => `<img src="data:image/png;base64,${s.image_base64}" alt="sample">`).join('')
      || '<p style="color:var(--text-dim);">No samples stored</p>';
    showModal(`Dataset Samples — ${name}`, `<div class="samples-grid">${grid}</div>`);
  } catch(e) { console.error(e); }
}

async function deleteStudent(id, name) {
  if (!confirm(`Delete student "${name}"? This cannot be undone.`)) return;
  try {
    await api('/admin/students/' + id, { method: 'DELETE' });
    loadStudents();
  } catch(e) { alert('Delete failed'); }
}

// ===== TEACHER ACCOUNTS TAB =====
async function loadTeachers() {
  const search = (document.getElementById('teacherSearch')?.value || '').toLowerCase();
  try {
    const r = await api('/admin/teachers');
    let teachers = await r.json();
    if (search) teachers = teachers.filter(t => t.full_name.toLowerCase().includes(search) || (t.username||'').toLowerCase().includes(search));
    document.getElementById('teachersBody').innerHTML = teachers.map(t =>
      `<tr>
        <td>${t.full_name}</td><td>${t.username||'—'}</td><td>${t.email}</td>
        <td>${t.created_at ? fmtTime(t.created_at) : '—'}</td>
        <td>
          <button class="secondary" style="font-size:12px;padding:4px 8px;" onclick="resetTeacherPw(${t.id},'${t.full_name}')">Reset PW</button>
          <button class="secondary" style="font-size:12px;padding:4px 8px;margin-left:4px;" onclick="deleteTeacher(${t.id},'${t.full_name}')">Delete</button>
        </td>
      </tr>`
    ).join('') || '<tr><td colspan="5" style="color:var(--text-dim);">No teachers found</td></tr>';
  } catch(e) { console.error(e); }
}

function showCreateTeacherModal() {
  showModal('Create Teacher Account', `
    <div><label class="field-label">Full Name</label><input id="newTeacherName"></div>
    <div style="margin-top:10px;"><label class="field-label">Username</label><input id="newTeacherUsername"></div>
    <div style="margin-top:10px;"><label class="field-label">Email</label><input id="newTeacherEmail" type="email"></div>
    <div style="margin-top:10px;"><label class="field-label">Password</label><input id="newTeacherPw" value="teacher123"></div>
    <div class="actions"><button class="primary" onclick="createTeacher()">Create</button></div>
  `);
}

async function createTeacher() {
  const body = {
    full_name: document.getElementById('newTeacherName').value,
    username: document.getElementById('newTeacherUsername').value,
    email: document.getElementById('newTeacherEmail').value,
    password: document.getElementById('newTeacherPw').value,
  };
  try {
    const r = await api('/admin/teachers', { method: 'POST', body });
    if (!r.ok) { const e = await r.json(); alert(e.detail); return; }
    closeModal(); loadTeachers();
  } catch(e) { alert('Failed to create teacher'); }
}

async function resetTeacherPw(id, name) {
  const pw = prompt(`New password for ${name}:`, 'teacher123');
  if (!pw) return;
  try {
    await api('/admin/teachers/' + id + '/reset-password', { method: 'POST', body: { new_password: pw } });
    alert('Password reset successfully');
  } catch(e) { alert('Reset failed'); }
}

async function deleteTeacher(id, name) {
  if (!confirm(`Delete teacher "${name}"?`)) return;
  try {
    await api('/admin/teachers/' + id, { method: 'DELETE' });
    loadTeachers();
  } catch(e) { alert('Delete failed'); }
}

// ===== ATTENDANCE RECORDS TAB =====
async function loadAttendanceRecords() {
  let url = '/admin/attendance/records?';
  const search = document.getElementById('attSearch')?.value;
  const dept = document.getElementById('attDeptFilter')?.value;
  const status = document.getElementById('attStatusFilter')?.value;
  const date = document.getElementById('attDateFilter')?.value;
  if (search) url += 'search=' + encodeURIComponent(search) + '&';
  if (dept) url += 'department_id=' + dept + '&';
  if (status) url += 'status=' + status + '&';
  if (date) url += 'date_on=' + date + '&';
  try {
    const r = await api(url);
    const records = await r.json();
    document.getElementById('attendanceBody').innerHTML = records.map(r =>
      `<tr>
        <td>${r.student_id}</td><td>${r.full_name}</td><td>${r.department}</td>
        <td>${fmtTime(r.date)}</td>
        <td><span class="status-badge status-${r.status}">${r.status}</span></td>
        <td>${r.confidence ? (r.confidence * 100).toFixed(1) + '%' : '—'}</td>
        <td>${r.terminal}</td>
      </tr>`
    ).join('') || '<tr><td colspan="7" style="color:var(--text-dim);">No records found</td></tr>';
  } catch(e) { console.error(e); }
}

// ===== REPORTS TAB =====
async function loadReportPreview() {
  let url = '/admin/reports/preview?';
  const dept = document.getElementById('rptDept')?.value;
  const from = document.getElementById('rptDateFrom')?.value;
  const to = document.getElementById('rptDateTo')?.value;
  if (dept) url += 'department_id=' + dept + '&';
  if (from) url += 'date_from=' + from + '&';
  if (to) url += 'date_to=' + to + '&';
  try {
    const r = await api(url);
    const data = await r.json();
    document.getElementById('rptStats').innerHTML = [
      `<div class="stat-card"><div class="stat-number">${data.total_logged}</div><div class="stat-label">Total Logged</div></div>`,
      `<div class="stat-card"><div class="stat-number green">${data.present}</div><div class="stat-label">Present</div></div>`,
      `<div class="stat-card"><div class="stat-number amber">${data.late}</div><div class="stat-label">Late</div></div>`,
      `<div class="stat-card"><div class="stat-number">${data.turnout_rate}%</div><div class="stat-label">Turnout</div></div>`,
    ].join('');
    document.getElementById('rptPreviewBody').innerHTML = data.preview.map(r =>
      `<tr><td>${r.student_name}</td><td>${r.department}</td><td>${r.date}</td><td><span class="status-badge status-${r.status}">${r.status}</span></td></tr>`
    ).join('') || '<tr><td colspan="4">No data</td></tr>';
  } catch(e) { console.error(e); }
}

function exportReport(format) {
  let url = API_BASE + '/admin/reports/attendance/export?format=' + format;
  const dept = document.getElementById('rptDept')?.value;
  const from = document.getElementById('rptDateFrom')?.value;
  const to = document.getElementById('rptDateTo')?.value;
  if (dept) url += '&department_id=' + dept;
  if (from) url += '&date_from=' + from;
  if (to) url += '&date_to=' + to;
  // Download via hidden link
  const a = document.createElement('a');
  fetch(url, { headers: { 'Authorization': 'Bearer ' + token } })
    .then(r => r.blob())
    .then(blob => { a.href = URL.createObjectURL(blob); a.download = 'attendance_report.' + format; a.click(); });
}

// ===== ANALYTICS TAB =====
let trendChartInst, deptChartInst, turnoutChartInst;
async function loadAnalytics() {
  try {
    const r = await api('/admin/analytics/summary');
    const data = await r.json();
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
    const textColor = isDark ? '#9aa4bf' : '#6b7280';

    // Trend chart
    if (trendChartInst) trendChartInst.destroy();
    trendChartInst = new Chart(document.getElementById('trendChart'), {
      type: 'line',
      data: {
        labels: data.trend_last_7_days.map(d => d.date.substring(5)),
        datasets: [{
          label: 'Attendance Rate %', data: data.trend_last_7_days.map(d => d.attendance_rate),
          borderColor: '#4f7cff', backgroundColor: 'rgba(79,124,255,0.15)', fill: true, tension: 0.3,
        }]
      },
      options: { responsive: true, scales: { y: { beginAtZero: true, max: 100, grid: { color: gridColor }, ticks: { color: textColor } }, x: { grid: { display: false }, ticks: { color: textColor } } }, plugins: { legend: { labels: { color: textColor } } } }
    });

    // Dept bar chart
    if (deptChartInst) deptChartInst.destroy();
    deptChartInst = new Chart(document.getElementById('deptChart'), {
      type: 'bar',
      data: {
        labels: data.department_breakdown.map(d => d.department),
        datasets: [{ label: 'Students', data: data.department_breakdown.map(d => d.student_count), backgroundColor: '#4f7cff', borderRadius: 6 }]
      },
      options: { responsive: true, indexAxis: 'y', scales: { x: { grid: { color: gridColor }, ticks: { color: textColor } }, y: { grid: { display: false }, ticks: { color: textColor } } }, plugins: { legend: { display: false } } }
    });

    // Turnout doughnut
    if (turnoutChartInst) turnoutChartInst.destroy();
    turnoutChartInst = new Chart(document.getElementById('turnoutChart'), {
      type: 'doughnut',
      data: {
        labels: ['Present', 'Absent'],
        datasets: [{ data: [data.today_present, data.today_absent], backgroundColor: ['#34d399', '#f87171'], borderWidth: 0 }]
      },
      options: { responsive: true, plugins: { legend: { labels: { color: textColor } } } }
    });

    // Best dept
    const best = data.department_breakdown.sort((a,b) => b.attendance_rate - a.attendance_rate)[0];
    document.getElementById('perfBestDept').textContent = best ? `${best.department} (${best.attendance_rate}%)` : '—';
  } catch(e) { console.error('Analytics error', e); }
}

// ===== SYSTEM TAB =====
async function loadSystemAudit() {
  try {
    const r = await api('/admin/activity-stream?limit=100');
    const events = await r.json();
    document.getElementById('sysAuditBody').innerHTML = events.map(e =>
      `<tr><td style="white-space:nowrap;">${fmtTime(e.timestamp)}</td><td>${e.user}</td><td>${e.action}</td><td style="font-size:13px;">${e.details||''}</td><td><span class="status-badge" style="background:${e.category==='system'?'rgba(248,113,113,0.15)':'var(--accent-light)'};color:${e.category==='system'?'var(--red)':'var(--accent)'};">${e.category}</span></td></tr>`
    ).join('') || '<tr><td colspan="5">No events</td></tr>';
  } catch(e) { console.error(e); }
}

async function downloadBackup() {
  try {
    const r = await fetch(API_BASE + '/admin/backup/export', { headers: { 'Authorization': 'Bearer ' + token } });
    const blob = await r.blob();
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'smartface_backup.json'; a.click();
  } catch(e) { alert('Backup download failed'); }
}

async function restoreBackup() {
  if (!confirm('⚠️ This will OVERWRITE all data. Are you sure?')) return;
  if (!confirm('FINAL WARNING: All existing data will be permanently replaced.')) return;
  const file = document.getElementById('restoreFile').files[0];
  if (!file) { alert('Select a backup file first'); return; }
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await fetch(API_BASE + '/admin/backup/restore', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token }, body: fd });
    const data = await r.json();
    alert(data.detail || 'Restore complete');
    location.reload();
  } catch(e) { alert('Restore failed'); }
}

async function changePassword() {
  const current = document.getElementById('cpCurrent').value;
  const newPw = document.getElementById('cpNew').value;
  if (!current || !newPw) { alert('Fill in both fields'); return; }
  try {
    const r = await api('/admin/change-password', { method: 'POST', body: { current_password: current, new_password: newPw } });
    const data = await r.json();
    if (!r.ok) { alert(data.detail); return; }
    alert('Password changed successfully');
    document.getElementById('cpCurrent').value = '';
    document.getElementById('cpNew').value = '';
  } catch(e) { alert('Failed'); }
}

// ===== REGISTER STUDENT WIZARD =====
let wizardStep = 1;
let capturedFrames = [];
let regStream = null;

function wizardNext() {
  if (wizardStep === 1) {
    // Validate step 1
    const required = ['regUsername', 'regFullName', 'regEmail', 'regDept'];
    for (const id of required) {
      if (!document.getElementById(id).value) { alert('Please fill in all required fields'); return; }
    }
    wizardStep = 2;
    startCamera();
  } else if (wizardStep === 2) {
    if (capturedFrames.length === 0) { alert('Capture at least 1 frame'); return; }
    wizardStep = 3;
    submitEnrollment();
  }
  updateWizardUI();
}

function updateWizardUI() {
  document.querySelectorAll('.wizard-step').forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.toggle('active', s === wizardStep);
    el.classList.toggle('done', s < wizardStep);
  });
  document.querySelectorAll('.wizard-panel').forEach((el, i) => {
    el.classList.toggle('active', i + 1 === wizardStep);
  });
}

async function startCamera() {
  try {
    regStream = await navigator.mediaDevices.getUserMedia({ video: true });
    document.getElementById('regVideo').srcObject = regStream;
  } catch(e) { alert('Camera access denied'); }
}

function captureFrame() {
  const video = document.getElementById('regVideo');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
  const b64 = dataUrl.split(',')[1];
  capturedFrames.push(b64);
  document.getElementById('captureCount').textContent = capturedFrames.length;
  // Add thumbnail
  const img = document.createElement('img');
  img.src = dataUrl; img.className = 'capture-thumb';
  document.getElementById('captureStrip').appendChild(img);
}

async function submitEnrollment() {
  // Stop camera
  if (regStream) { regStream.getTracks().forEach(t => t.stop()); regStream = null; }
  const body = {
    username: document.getElementById('regUsername').value,
    email: document.getElementById('regEmail').value,
    full_name: document.getElementById('regFullName').value,
    department_id: parseInt(document.getElementById('regDept').value),
    academic_year: document.getElementById('regYear').value || null,
    section: document.getElementById('regSection').value || null,
    roll_number: document.getElementById('regRoll').value || null,
    phone_number: document.getElementById('regPhone').value || null,
    frames_base64: capturedFrames,
  };
  try {
    const r = await api('/admin/students/enroll-webcam', { method: 'POST', body });
    const data = await r.json();
    if (!r.ok) {
      document.getElementById('regResult').textContent = 'Error: ' + (data.detail || 'Unknown error');
      return;
    }
    document.getElementById('regResult').textContent = `${data.full_name} enrolled successfully! Encoding vectors: 1, Face samples stored: ${capturedFrames.length}`;
  } catch(e) {
    document.getElementById('regResult').textContent = 'Enrollment failed: ' + e.message;
  }
}

function resetWizard() {
  wizardStep = 1;
  capturedFrames = [];
  document.getElementById('captureStrip').innerHTML = '';
  document.getElementById('captureCount').textContent = '0';
  ['regUsername','regFullName','regEmail','regPhone','regYear','regSection','regRoll'].forEach(id => {
    document.getElementById(id).value = '';
  });
  updateWizardUI();
}

// ===== Modal helper =====
function showModal(title, content) {
  document.getElementById('modalContainer').innerHTML = `
    <div class="modal-backdrop" onclick="closeModal()">
      <div class="modal" onclick="event.stopPropagation()">
        <h3>${title}</h3>
        ${content}
        <div class="actions"><button class="secondary" onclick="closeModal()">Close</button></div>
      </div>
    </div>`;
}
function closeModal() { document.getElementById('modalContainer').innerHTML = ''; }

// ---- Initial load ----
loadDashboard();
