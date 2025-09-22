import cv2
from PIL import Image
from io import BytesIO
import base64
from datetime import datetime
import ollama
import time
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import threading

# =======================
# CONFIGURATION
# =======================
CAMERA_URL = "cctv_tg.mp4"   # or RTSP link
MODEL_NAME = "moondream"

app = Flask(__name__)
CORS(app)
analysis_logs = []

# =======================
# HELPER FUNCTIONS
# =======================
def encode_image(image):
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def describe_image(base64_image, frame_number):
    prompt = f"""
You are monitoring a live CCTV frame. Analyze and provide a concise, actionable description.
Frame number: {frame_number}
"""
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt, "images": [base64_image]}],
            stream=False
        )
        return response.get("message", {}).get("content", "").strip() or "Everything looks normal."
    except Exception as e:
        print(f"Error describing image: {e}")
        return "Everything looks normal."

def safe_read(cap, url):
    ret, frame = cap.read()
    if not ret:
        print("Reconnecting camera...")
        cap.release()
        time.sleep(1)
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        ret, frame = cap.read()
        if not ret:
            return cap, None
    return cap, frame

# =======================
# SURVEILLANCE LOOP
# =======================
def surveillance_loop():
    print(f"Surveillance Monitor started with {MODEL_NAME}.")
    cap = cv2.VideoCapture(CAMERA_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("Error: Cannot open camera stream.")
        return

    frame_count = 0
    try:
        while True:
            cap, frame = safe_read(cap, CAMERA_URL)
            if frame is None:
                continue

            frame_count += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            encoded_img = encode_image(frame)
            description = describe_image(encoded_img, frame_count)

            log_entry = {
                "frame_number": frame_count,
                "timestamp": timestamp,
                "description": description
            }
            analysis_logs.append(log_entry)
            if len(analysis_logs) > 100:
                analysis_logs.pop(0)

            print(f"Frame {frame_count}: {description}")

    except KeyboardInterrupt:
        print("Monitoring stopped.")
    finally:
        cap.release()

# =======================
# API ENDPOINTS
# =======================
@app.route("/logs")
def get_logs():
    return jsonify(analysis_logs)

# =======================
# DASHBOARD PAGE
# =======================
@app.route("/")
def dashboard():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
  <title>Monitoring Page</title>
  <style>
    body { background: #111; color: #fff; font-family: Arial; margin:0; padding:0;}
    header { padding:1rem; border-bottom:1px solid #333; display:flex; justify-content:space-between; }
    .stats { display:flex; gap:1rem; margin:1rem; }
    .stat { padding:1rem; border-radius:8px; flex:1; }
    .blue { background: linear-gradient(135deg, #2563EB, #1D4ED8);}
    .red { background: linear-gradient(135deg, #DC2626, #B91C1C);}
    .green { background: linear-gradient(135deg, #059669, #047857);}
    .logs { margin:1rem; display:grid; gap:1rem; grid-template-columns:repeat(auto-fill, minmax(350px, 1fr));}
    .card { background:#1F2937; border:1px solid #4B5563; border-radius:8px; padding:1rem;}
    .critical { background:#7F1D1D; color:#FECACA; padding:2px 6px; border-radius:4px;}
    .alert { background:#78350F; color:#FED7AA; padding:2px 6px; border-radius:4px;}
    .normal { background:#14532D; color:#BBF7D0; padding:2px 6px; border-radius:4px;}
  </style>
</head>
<body>
  <header>
    <h1>Monitoring Page</h1>
    <button onclick="fetchLogs()">Refresh</button>
  </header>
  <div class="stats">
    <div class="stat blue"><h3>Total Logs</h3><p id="totalLogs">0</p></div>
    <div class="stat red"><h3>Recent Alerts</h3><p id="recentAlerts">0</p></div>
    <div class="stat green"><h3>Active Monitoring</h3><p>1</p></div>
  </div>
  <div class="logs" id="logs"></div>

<script>
async function fetchLogs() {
  const res = await fetch('/logs');
  const data = await res.json();
  document.getElementById('totalLogs').innerText = data.length;
  document.getElementById('recentAlerts').innerText = data.filter(l =>
    l.description && (l.description.toLowerCase().includes('alert') ||
                      l.description.toLowerCase().includes('warning'))
  ).length;
  const container = document.getElementById('logs');
  container.innerHTML = '';
  data.slice().reverse().forEach(log => {
    let priority = 'normal';
    if(log.description.toLowerCase().includes('critical') || log.description.toLowerCase().includes('emergency')) priority='critical';
    else if(log.description.toLowerCase().includes('alert') || log.description.toLowerCase().includes('warning') || log.description.toLowerCase().includes('error')) priority='alert';
    container.innerHTML += `
      <div class="card">
        <h4>Frame #${log.frame_number} - <span class="${priority}">${priority.toUpperCase()}</span></h4>
        <small>${log.timestamp}</small>
        <p>${log.description}</p>
      </div>
    `;
  });
}
setInterval(fetchLogs, 5000);
fetchLogs();
</script>
</body>
</html>
""")

# =======================
# ENTRY POINT
# =======================
if __name__ == "__main__":
    t = threading.Thread(target=surveillance_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5001)
