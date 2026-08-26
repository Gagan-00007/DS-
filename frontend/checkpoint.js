// Runs on the phone/device mounted at the door. Not login-gated — this
// page is configured per-device via URL query params, e.g.:
//   checkpoint.html?room=Room-1&camera_id=cam-entry-1&checkpoint_type=entry
//   checkpoint.html?room=Room-1&camera_id=cam-exit-1&checkpoint_type=exit

const API_BASE = window.location.protocol === "file:" ? "http://localhost:8000" : window.location.origin;

const params = new URLSearchParams(window.location.search);
const ROOM = params.get("room") || "Room-1";
const CAMERA_ID = params.get("camera_id") || "cam-entry-1";
const CHECKPOINT_TYPE = params.get("checkpoint_type") || "entry";

const BURST_FRAME_COUNT = 8;       // frames per capture, per spec 3.2 (5-10 over ~1.5s)
const BURST_INTERVAL_MS = 180;     // spacing between frames in the burst
const SCAN_LOOP_INTERVAL_MS = 3000; // how often to attempt a new burst
const COOLDOWN_AFTER_MATCH_MS = 5000; // pause after a successful/failed match so one
                                       // person doesn't get scanned 3x while walking through

document.getElementById("checkpoint-label").textContent =
  `${CHECKPOINT_TYPE === "entry" ? "Entry" : "Exit"} Checkpoint — ${ROOM}`;

const videoEl = document.getElementById("video");
const canvasEl = document.getElementById("canvas");
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");

let scanning = false;
let cooldownUntil = 0;

function setStatus(text, cssClass) {
  statusEl.textContent = text;
  statusEl.className = `status-text ${cssClass}`;
}

function addLogEntry(status, name) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  const time = new Date().toLocaleTimeString();
  const label = name ? `${status.replace(/_/g, " ")} — ${name}` : status.replace(/_/g, " ");
  entry.innerHTML = `<span>${label}</span><span class="time">${time}</span>`;
  logEl.prepend(entry);
  // Keep the log from growing unbounded during a long demo.
  while (logEl.children.length > 30) logEl.removeChild(logEl.lastChild);
}

async function startCamera() {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "environment" }, // rear camera on a phone mounted at a door
    audio: false,
  });
  videoEl.srcObject = stream;
}

function captureFrameAsBase64() {
  const w = videoEl.videoWidth;
  const h = videoEl.videoHeight;
  if (!w || !h) return null;
  canvasEl.width = w;
  canvasEl.height = h;
  const ctx = canvasEl.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, w, h);
  // Strip the "data:image/jpeg;base64," prefix — backend expects raw base64.
  return canvasEl.toDataURL("image/jpeg", 0.8).split(",")[1];
}

async function captureBurst() {
  const frames = [];
  for (let i = 0; i < BURST_FRAME_COUNT; i++) {
    const frame = captureFrameAsBase64();
    if (frame) frames.push(frame);
    await new Promise((r) => setTimeout(r, BURST_INTERVAL_MS));
  }
  return frames;
}

function statusToDisplay(status) {
  const map = {
    marked_present: ["✅ Attendance Marked", "status-success"],
    marked_late: ["✅ Marked Late", "status-success"],
    marked_left_early: ["⚠️ Marked Left Early", "status-fail"],
    spoof_suspected: ["❌ Spoof Attempt Detected", "status-fail"],
    unrecognized: ["❌ Not Recognized", "status-fail"],
    no_face: ["Idle", "status-idle"],
    no_active_class: ["No Active Class Right Now", "status-idle"],
  };
  return map[status] || [status, "status-idle"];
}

async function runScanCycle() {
  if (scanning || Date.now() < cooldownUntil) return;
  scanning = true;

  try {
    setStatus("Face Detected — Capturing...", "status-detecting");
    const frames = await captureBurst();

    if (frames.length === 0) {
      setStatus("Idle", "status-idle");
      return;
    }

    setStatus("Verifying Liveness...", "status-verifying");

    const res = await fetch(`${API_BASE}/checkpoint/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room: ROOM,
        camera_id: CAMERA_ID,
        checkpoint_type: CHECKPOINT_TYPE,
        frames_base64: frames,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setStatus(`Error: ${err.detail || res.status}`, "status-fail");
      return;
    }

    const result = await res.json();
    const [display, cssClass] = statusToDisplay(result.status);
    const fullDisplay = result.student_name ? `${display}: ${result.student_name}` : display;
    setStatus(fullDisplay, cssClass);

    // Only log and cool down on outcomes that involved an actual face —
    // a plain "no_face" tick of the loop (nobody at the door) shouldn't
    // clutter the log or trigger a cooldown.
    if (result.status !== "no_face" && result.status !== "no_active_class") {
      addLogEntry(result.status, result.student_name);
      cooldownUntil = Date.now() + COOLDOWN_AFTER_MATCH_MS;
    }
  } catch (err) {
    setStatus(`Connection error: ${err.message}`, "status-fail");
  } finally {
    scanning = false;
  }
}

(async function init() {
  try {
    await startCamera();
    setStatus("Idle", "status-idle");
    setInterval(runScanCycle, SCAN_LOOP_INTERVAL_MS);
  } catch (err) {
    setStatus(`Camera error: ${err.message}`, "status-fail");
  }
})();
