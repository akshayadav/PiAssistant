// === DOM refs ===
const messagesEl = document.getElementById("messages");
const mainScroll = document.getElementById("main-scroll");
const inputEl = document.getElementById("msg-input");
const sendBtn = document.getElementById("send-btn");
const statusEl = document.getElementById("status");
const timerAlert = document.getElementById("timer-alert");
const timerAlertText = document.getElementById("timer-alert-text");

let sending = false;
let assistantName = "Assistant";

// === API Key / Auth ===

function getApiKey() {
  return localStorage.getItem("piassistant_api_key") || "";
}

function authHeaders() {
  const key = getApiKey();
  const h = { "Content-Type": "application/json" };
  if (key) h["Authorization"] = `Bearer ${key}`;
  return h;
}

function authHeadersNoBody() {
  const key = getApiKey();
  if (key) return { "Authorization": `Bearer ${key}` };
  return {};
}


// Fetch display name from config
fetch("/api/config").then(r => r.json()).then(c => {
  assistantName = c.assistant_name || "Assistant";
  document.getElementById("app-title").textContent = assistantName;
  document.title = assistantName;
}).catch(() => {});

// === Chat ===

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + "px";
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = role === "user" ? "You" : assistantName;
  div.appendChild(sender);
  const body = document.createElement("div");
  body.textContent = text;
  div.appendChild(body);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  mainScroll.scrollTop = mainScroll.scrollHeight;
  return div;
}

function addThinking() {
  const div = document.createElement("div");
  div.className = "msg bot thinking";
  div.id = "thinking";
  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = assistantName;
  div.appendChild(sender);
  const body = document.createElement("span");
  body.textContent = "Thinking";
  div.appendChild(body);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  mainScroll.scrollTop = mainScroll.scrollHeight;
}

function removeThinking() {
  const el = document.getElementById("thinking");
  if (el) el.remove();
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || sending) return;

  sending = true;
  sendBtn.disabled = true;
  inputEl.value = "";
  inputEl.style.height = "auto";

  addMessage(text, "user");
  addThinking();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ message: text }),
    });
    removeThinking();
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    addMessage(data.response, "bot");
    // Refresh widgets after chat (user may have added items)
    refreshAll();
  } catch (err) {
    removeThinking();
    addMessage(`Error: ${err.message}`, "bot error");
  } finally {
    sending = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

async function resetChat() {
  try {
    await fetch("/api/reset", { method: "POST", headers: authHeadersNoBody() });
    messagesEl.innerHTML = "";
    addMessage("Chat reset. How can I help you?", "bot");
  } catch (err) {
    addMessage(`Reset failed: ${err.message}`, "bot error");
  }
}

async function shutdownPi() {
  if (!confirm("Shut down the Raspberry Pi?")) return;
  try {
    await fetch("/api/shutdown", { method: "POST", headers: authHeadersNoBody() });
    addMessage("Shutting down... Safe to unplug in 10 seconds.", "bot");
    statusEl.textContent = "shutting down";
    statusEl.className = "status";
  } catch (err) {
    addMessage(`Shutdown failed: ${err.message}`, "bot error");
  }
}

// === Voice Input (Web Speech API) ===

let _recognition = null;
let _isListening = false;

function toggleVoiceInput() {
  if (_isListening) {
    stopVoiceInput();
    return;
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    addMessage("Voice input not supported in this browser.", "bot error");
    return;
  }

  _recognition = new SpeechRecognition();
  _recognition.lang = "en-US";
  _recognition.interimResults = true;
  _recognition.continuous = false;

  const micBtn = document.getElementById("mic-btn");
  const input = document.getElementById("msg-input");
  const originalPlaceholder = input.placeholder;

  _recognition.onstart = () => {
    _isListening = true;
    micBtn.classList.add("listening");
    input.placeholder = "Listening...";
  };

  _recognition.onresult = (event) => {
    let transcript = "";
    for (let i = 0; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    input.value = transcript;
  };

  _recognition.onend = () => {
    _isListening = false;
    micBtn.classList.remove("listening");
    input.placeholder = originalPlaceholder;
    // Auto-send if we got text
    if (input.value.trim()) {
      sendMessage();
    }
  };

  _recognition.onerror = (event) => {
    _isListening = false;
    micBtn.classList.remove("listening");
    input.placeholder = originalPlaceholder;
    if (event.error !== "no-speech") {
      addMessage(`Voice error: ${event.error}`, "bot error");
    }
  };

  _recognition.start();
}

function stopVoiceInput() {
  if (_recognition) {
    _recognition.stop();
  }
}

// === Health ===

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    statusEl.textContent = data.status === "ok" ? "online" : "degraded";
    statusEl.className = "status " + (data.status === "ok" ? "online" : "");
  } catch {
    statusEl.textContent = "offline";
    statusEl.className = "status";
  }
}

// === Calendar Widget ===

async function fetchCalendar() {
  const el = document.getElementById("calendar-content");
  const countEl = document.getElementById("calendar-count");
  try {
    const res = await fetch("/api/calendar/events?days=7");
    if (!res.ok) throw new Error();
    const events = await res.json();
    countEl.textContent = events.length;

    if (events.length === 0) {
      el.innerHTML = '<div class="empty-state">No upcoming events</div>';
      return;
    }

    // Group by date
    const grouped = {};
    for (const e of events) {
      const dateStr = e.start.substring(0, 10);
      if (!grouped[dateStr]) grouped[dateStr] = [];
      grouped[dateStr].push(e);
    }

    el.innerHTML = '<div class="calendar-timeline">' + Object.entries(grouped).map(([dateStr, evts]) => {
      const d = new Date(dateStr + "T00:00:00");
      const today = new Date();
      const isToday = d.toDateString() === today.toDateString();
      const tomorrow = new Date(today);
      tomorrow.setDate(today.getDate() + 1);
      const isTomorrow = d.toDateString() === tomorrow.toDateString();
      const label = isToday ? "Today" : isTomorrow ? "Tomorrow" : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

      return `
        <div class="cal-date-group">
          <div class="cal-date-label${isToday ? ' cal-today' : ''}">${label}</div>
          ${evts.map(e => {
            const timeStr = e.all_day ? "All day" : new Date(e.start).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
            const srcClass = e.source === "google" ? "cal-google" : "cal-icloud";
            return `
              <div class="cal-event ${srcClass}">
                <span class="cal-time">${timeStr}</span>
                <span class="cal-summary">${e.summary}</span>
              </div>`;
          }).join("")}
        </div>`;
    }).join("") + '</div>';
  } catch {
    el.innerHTML = '<div class="empty-state">Calendar unavailable</div>';
  }
}

// === Weather Widget ===

async function fetchWeather() {
  const el = document.getElementById("weather-content");
  const countEl = document.getElementById("weather-count");
  try {
    const res = await fetch("/api/weather/cities");
    if (!res.ok) throw new Error();
    const cities = await res.json();
    countEl.textContent = cities.length;

    if (cities.length === 0) {
      el.innerHTML = '<div class="empty-state">No cities tracked</div>';
      return;
    }

    el.innerHTML = '<div class="weather-cities">' + cities.map(c => {
      let localTime = "";
      if (c.timezone) {
        try {
          localTime = new Date().toLocaleTimeString("en-US", {
            timeZone: c.timezone, hour: "numeric", minute: "2-digit", hour12: true
          });
        } catch { localTime = ""; }
      }
      return `
      <div class="weather-city-card">
        <button class="weather-city-remove" onclick="removeWeatherCity(${c.id})" title="Remove">&times;</button>
        <div class="weather-city-name">${c.display_name}</div>
        ${localTime ? `<div class="weather-city-time">${localTime}</div>` : ""}
        ${c.temp !== null && c.temp !== undefined
          ? `<div class="weather-city-temp">${Math.round(c.temp)}&deg;F</div>
             <div class="weather-city-desc">${c.desc}</div>
             <div class="weather-city-details">
               <span>Feels ${Math.round(c.feel)}&deg;</span>
               <span>${c.hum}%</span>
               <span>${c.wind}mph</span>
             </div>`
          : '<div class="weather-city-desc">Unavailable</div>'
        }
      </div>`;
    }).join("") + '</div>';
  } catch {
    el.innerHTML = '<div class="empty-state">Weather unavailable</div>';
  }
}

function toggleWeatherForm() {
  const form = document.getElementById("weather-add-form");
  form.style.display = form.style.display === "none" ? "block" : "none";
  if (form.style.display === "block") {
    document.getElementById("weather-city-input").focus();
  }
}

async function addWeatherCity(e) {
  e.preventDefault();
  const input = document.getElementById("weather-city-input");
  const name = input.value.trim();
  if (!name) return;
  await fetch("/api/weather/cities", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ name: name }),
  });
  input.value = "";
  document.getElementById("weather-add-form").style.display = "none";
  fetchWeather();
}

async function removeWeatherCity(id) {
  await fetch(`/api/weather/cities/${id}`, { method: "DELETE", headers: authHeadersNoBody() });
  fetchWeather();
}

// === Sessions Widget ===

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function statusBadge(status) {
  let cls = "badge-active";
  if (status === "thinking") cls = "badge-thinking";
  else if (status.startsWith("running")) cls = "badge-running";
  else if (status === "waiting for input") cls = "badge-waiting";
  else if (status === "needs attention") cls = "badge-attention";
  else if (status === "idle") cls = "badge-idle";
  return `<span class="badge ${cls}">${status}</span>`;
}

async function fetchSessions() {
  const el = document.getElementById("sessions-content");
  const countEl = document.getElementById("sessions-count");
  try {
    const res = await fetch("/api/hooks/sessions");
    if (!res.ok) throw new Error();
    const sessions = await res.json();
    countEl.textContent = sessions.length;

    if (sessions.length === 0) {
      el.innerHTML = '<div class="empty-state">No active sessions</div>';
      return;
    }

    el.innerHTML = sessions.map(s => `
      <div class="session-card">
        <div class="session-project">${s.project} ${statusBadge(s.status)}</div>
        <div class="session-meta">
          ${s.machine ? s.machine + " &middot; " : ""}${formatDuration(s.duration)}${s.idle > 60 ? " &middot; idle " + formatDuration(s.idle) : ""}
        </div>
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Sessions unavailable</div>';
  }
}

// === System Monitor Widget ===

function formatUptime(seconds) {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function sysBar(label, percent, detail) {
  const cls = percent > 85 ? "bar-red" : percent > 60 ? "bar-yellow" : "bar-green";
  return `
    <div class="sys-metric">
      <div class="sys-label"><span>${label}</span><span>${detail}</span></div>
      <div class="sys-bar"><div class="sys-bar-fill ${cls}" style="width:${percent}%"></div></div>
    </div>`;
}

async function fetchSystem() {
  const el = document.getElementById("system-content");
  try {
    const res = await fetch("/api/system");
    if (!res.ok) throw new Error();
    const s = await res.json();

    const memDetail = `${s.memory_percent}% (${s.memory_available_gb}GB free)`;
    const diskDetail = `${s.disk_percent}% (${s.disk_free_gb}GB free)`;

    el.innerHTML = `
      ${sysBar("CPU", s.cpu_percent, s.cpu_percent + "%")}
      ${sysBar("RAM", s.memory_percent, memDetail)}
      ${sysBar("Disk", s.disk_percent, diskDetail)}
      <div class="sys-info">
        ${s.cpu_temp_c !== null ? `<span>Temp: ${s.cpu_temp_c}&deg;C</span>` : ""}
        <span>Up: ${formatUptime(s.uptime_seconds)}</span>
        <span>${s.platform}</span>
      </div>
    `;
  } catch {
    el.innerHTML = '<div class="empty-state">System unavailable</div>';
  }
}

// === Network Widget ===

async function fetchNetwork() {
  const el = document.getElementById("network-content");
  const countEl = document.getElementById("network-count");
  try {
    const res = await fetch("/api/network/devices");
    if (!res.ok) throw new Error();
    const devices = await res.json();
    const onlineCount = devices.filter(d => d.is_online).length;
    countEl.textContent = `${onlineCount}/${devices.length}`;

    if (devices.length === 0) {
      el.innerHTML = '<div class="empty-state">No devices tracked</div>';
      return;
    }

    el.innerHTML = devices.map(d => `
      <div class="network-device">
        <span class="net-status ${d.is_online ? 'net-online' : 'net-offline'}"></span>
        <span class="net-name">${d.name}</span>
        <span class="net-host">${d.hostname}</span>
        ${d.last_seen ? `<span class="net-seen">${new Date(d.last_seen).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})}</span>` : ""}
        <button class="net-remove" onclick="removeNetworkDevice(${d.id})" title="Remove">&times;</button>
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Network unavailable</div>';
  }
}

function toggleNetworkForm() {
  const form = document.getElementById("network-add-form");
  form.style.display = form.style.display === "none" ? "block" : "none";
  if (form.style.display === "block") {
    document.getElementById("network-device-name").focus();
  }
}

async function addNetworkDevice(e) {
  e.preventDefault();
  const name = document.getElementById("network-device-name").value.trim();
  const hostname = document.getElementById("network-device-host").value.trim();
  if (!name || !hostname) return;
  await fetch("/api/network/devices", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ name, hostname }),
  });
  document.getElementById("network-device-name").value = "";
  document.getElementById("network-device-host").value = "";
  document.getElementById("network-add-form").style.display = "none";
  fetchNetwork();
}

async function removeNetworkDevice(id) {
  await fetch(`/api/network/devices/${id}`, { method: "DELETE", headers: authHeadersNoBody() });
  fetchNetwork();
}

// === Timers Widget ===

function formatTimer(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function fetchTimers() {
  const el = document.getElementById("timers-content");
  const countEl = document.getElementById("timers-count");
  try {
    const res = await fetch("/api/timers");
    if (!res.ok) throw new Error();
    const data = await res.json();
    const timers = data.timers || [];
    const fired = data.fired || [];
    const active = timers.filter(t => !t.fired);
    countEl.textContent = active.length;

    // Show alert for fired timers
    if (fired.length > 0) {
      showTimerAlert(fired.map(f => f.name).join(", "));
    }

    if (timers.length === 0) {
      el.innerHTML = '<div class="empty-state">No active timers</div>';
      return;
    }

    el.innerHTML = timers.map(t => `
      <div class="timer-entry">
        <span class="timer-name">${t.name}</span>
        <span class="${t.fired ? 'timer-fired' : 'timer-time'}">${t.fired ? 'DONE!' : formatTimer(t.remaining)}</span>
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Timers unavailable</div>';
  }
}

function showTimerAlert(names) {
  timerAlertText.textContent = `Timer done: ${names}`;
  timerAlert.style.display = "block";
  // Try to play a beep
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = 800;
    osc.connect(ctx.destination);
    osc.start();
    setTimeout(() => { osc.stop(); ctx.close(); }, 500);
  } catch {}
}

function dismissTimerAlert() {
  timerAlert.style.display = "none";
}

// === News Widget ===

let newsFeedsData = [];
let newsSpeaking = false;

async function fetchNews() {
  const el = document.getElementById("news-content");
  const countEl = document.getElementById("news-count");
  try {
    const res = await fetch("/api/news/feeds");
    if (!res.ok) throw new Error();
    const feeds = await res.json();
    newsFeedsData = feeds;
    const totalArticles = feeds.reduce((s, f) => s + f.articles.length, 0);
    countEl.textContent = totalArticles;

    if (feeds.length === 0) {
      el.innerHTML = '<div class="empty-state">No news feeds configured</div>';
      return;
    }

    el.innerHTML = '<div class="news-feeds">' + feeds.map(f => `
      <div class="news-feed-section">
        <button class="news-feed-remove" onclick="removeNewsFeed(${f.id})" title="Remove">&times;</button>
        <div class="news-feed-name">${f.name}</div>
        ${f.articles.length === 0
          ? '<div class="empty-state">No articles</div>'
          : f.articles.map(a => `
            <div class="news-headline">
              ${a.title} <span class="news-source">${a.source}</span>
            </div>
          `).join("")
        }
      </div>
    `).join("") + '</div>';
  } catch {
    el.innerHTML = '<div class="empty-state">News unavailable</div>';
  }
}

function toggleNewsForm() {
  const form = document.getElementById("news-add-form");
  form.style.display = form.style.display === "none" ? "block" : "none";
  if (form.style.display === "block") {
    document.getElementById("news-feed-name").focus();
  }
}

function toggleNewsFields() {
  const type = document.getElementById("news-feed-type").value;
  document.getElementById("news-feed-country").style.display = type === "headlines" ? "" : "none";
  document.getElementById("news-feed-query").style.display = type === "search" ? "" : "none";
}

async function addNewsFeed(e) {
  e.preventDefault();
  const name = document.getElementById("news-feed-name").value.trim();
  const provider = document.getElementById("news-feed-provider").value;
  const type = document.getElementById("news-feed-type").value;
  const country = document.getElementById("news-feed-country").value.trim();
  const query = document.getElementById("news-feed-query").value.trim();
  if (!name) return;
  if (type === "search" && !query) return;

  await fetch("/api/news/feeds", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ name, type, provider, country: type === "headlines" ? country : "", query: type === "search" ? query : "" }),
  });
  document.getElementById("news-feed-name").value = "";
  document.getElementById("news-feed-query").value = "";
  document.getElementById("news-add-form").style.display = "none";
  fetchNews();
}

async function removeNewsFeed(id) {
  await fetch(`/api/news/feeds/${id}`, { method: "DELETE", headers: authHeadersNoBody() });
  fetchNews();
}

// === TTS Engine (backend Kokoro/Piper with browser fallback) ===
let _ttsAudio = null;
let _ttsSpeaking = false;
let _ttsMediaSource = null;

async function speakText(text, onStart, onEnd) {
  if (_ttsSpeaking) { stopSpeaking(); if (onEnd) onEnd(); return; }
  const t0 = performance.now();
  console.log("[TTS] speakText called, text length:", text.length, "chars");

  // Try streaming if MediaSource supports MP3
  const canStream = typeof MediaSource !== "undefined" &&
    MediaSource.isTypeSupported("audio/mpeg");
  if (canStream) {
    console.log("[TTS] Streaming mode — POST /api/voice/speak {stream:true}");
    try {
      await _speakStreaming(text, t0, onStart, onEnd);
      return;
    } catch (err) {
      console.warn("[TTS] Streaming failed:", err.message, "— trying non-streaming");
    }
  }

  // Non-streaming fallback (full blob)
  console.log("[TTS] Non-streaming mode — POST /api/voice/speak");
  try {
    const res = await fetch("/api/voice/speak", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ text }),
    });
    const t1 = performance.now();
    console.log("[TTS] Backend responded:", res.status, "in", Math.round(t1 - t0), "ms");
    if (!res.ok) throw new Error("TTS backend error " + res.status);
    const blob = await res.blob();
    console.log("[TTS] Audio blob:", blob.size, "bytes in", Math.round(performance.now() - t0), "ms");
    const url = URL.createObjectURL(blob);
    _ttsAudio = new Audio(url);
    _ttsAudio.onplay = () => {
      console.log("[TTS] Playback started, TTFA:", Math.round(performance.now() - t0), "ms");
      _ttsSpeaking = true; if (onStart) onStart();
    };
    _ttsAudio.onended = () => { console.log("[TTS] Playback ended"); _cleanupTTS(); if (onEnd) onEnd(); };
    _ttsAudio.onerror = () => { _cleanupTTS(); if (onEnd) onEnd(); };
    _ttsAudio.play();
  } catch (err) {
    console.warn("[TTS] Backend failed:", err.message, "— browser speechSynthesis fallback");
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95;
    u.onstart = onStart; u.onend = onEnd; u.onerror = onEnd;
    speechSynthesis.speak(u);
  }
}

async function _speakStreaming(text, t0, onStart, onEnd) {
  const res = await fetch("/api/voice/speak", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ text, stream: true }),
  });
  if (!res.ok) throw new Error("TTS stream error " + res.status);
  console.log("[TTS] Stream response started in", Math.round(performance.now() - t0), "ms");

  const mediaSource = new MediaSource();
  _ttsMediaSource = mediaSource;
  _ttsAudio = new Audio();
  _ttsAudio.src = URL.createObjectURL(mediaSource);

  _ttsAudio.onplay = () => {
    console.log("[TTS] Stream playback started, TTFA:", Math.round(performance.now() - t0), "ms");
    _ttsSpeaking = true; if (onStart) onStart();
  };
  _ttsAudio.onended = () => { console.log("[TTS] Stream playback ended"); _cleanupTTS(); if (onEnd) onEnd(); };
  _ttsAudio.onerror = (e) => { console.error("[TTS] Stream playback error:", e); _cleanupTTS(); if (onEnd) onEnd(); };

  await new Promise((resolve, reject) => {
    mediaSource.addEventListener("sourceopen", async () => {
      try {
        const sourceBuffer = mediaSource.addSourceBuffer("audio/mpeg");
        const reader = res.body.getReader();
        let chunkNum = 0, totalBytes = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunkNum++;
          totalBytes += value.byteLength;
          if (chunkNum === 1) {
            console.log("[TTS] First chunk:", value.byteLength, "bytes at", Math.round(performance.now() - t0), "ms");
          }
          // Wait for sourceBuffer to be ready
          if (sourceBuffer.updating) {
            await new Promise(r => sourceBuffer.addEventListener("updateend", r, { once: true }));
          }
          sourceBuffer.appendBuffer(value);
          // Start playback after first chunk is appended
          if (chunkNum === 1) {
            await new Promise(r => sourceBuffer.addEventListener("updateend", r, { once: true }));
            _ttsAudio.play();
          }
        }
        console.log("[TTS] Stream complete:", chunkNum, "chunks,", totalBytes, "bytes in", Math.round(performance.now() - t0), "ms");
        // Wait for final buffer update before ending stream
        if (sourceBuffer.updating) {
          await new Promise(r => sourceBuffer.addEventListener("updateend", r, { once: true }));
        }
        if (mediaSource.readyState === "open") mediaSource.endOfStream();
        resolve();
      } catch (e) {
        reject(e);
      }
    }, { once: true });
  });
}

function stopSpeaking() {
  if (_ttsAudio) { _ttsAudio.pause(); _ttsAudio.currentTime = 0; }
  _cleanupTTS();
  speechSynthesis.cancel();
}

function _cleanupTTS() {
  if (_ttsMediaSource && _ttsMediaSource.readyState === "open") {
    try { _ttsMediaSource.endOfStream(); } catch {}
  }
  _ttsMediaSource = null;
  if (_ttsAudio) {
    const src = _ttsAudio.src;
    _ttsAudio = null;
    if (src.startsWith("blob:")) URL.revokeObjectURL(src);
  }
  _ttsSpeaking = false;
}

function speakNews() {
  console.log("[TTS] === Read button clicked ===");
  if (newsSpeaking) {
    console.log("[TTS] Already speaking, stopping");
    stopSpeaking();
    newsSpeaking = false;
    setNewsTTSButton(false);
    return;
  }

  const lines = [];
  for (const feed of newsFeedsData) {
    if (!feed.articles.length) continue;
    lines.push(feed.name + ".");
    for (const a of feed.articles) lines.push(a.title + ".");
  }
  if (!lines.length) { console.log("[TTS] No headlines to read"); return; }
  console.log("[TTS] Collected", lines.length, "lines from", newsFeedsData.length, "feeds");

  speakText(
    lines.join(" "),
    () => { newsSpeaking = true; setNewsTTSButton(true); },
    () => { newsSpeaking = false; setNewsTTSButton(false); }
  );
}

function setNewsTTSButton(speaking) {
  const btn = document.getElementById("news-tts-btn");
  if (!btn) return;
  btn.textContent = speaking ? "■ Stop" : "▶ Read";
  btn.title = speaking ? "Stop reading" : "Read headlines aloud";
}

// === Orders Widget ===

async function fetchOrders() {
  const el = document.getElementById("orders-content");
  const countEl = document.getElementById("orders-count");
  try {
    const res = await fetch("/api/orders");
    if (!res.ok) throw new Error();
    const orders = await res.json();
    countEl.textContent = orders.length;

    if (orders.length === 0) {
      el.innerHTML = '<div class="empty-state">No pending orders</div>';
      return;
    }

    el.innerHTML = '<div class="orders-list">' + orders.map(o => {
      const itemsHtml = o.items.map(item => `
        <div class="order-item">
          ${item.image_link ? `<img class="order-item-img" src="${item.image_link}" alt="">` : ""}
          <span class="order-item-title">${item.title || "Item"}</span>
        </div>
      `).join("");

      const statusClass = o.delivery_status.toLowerCase().includes("shipped") ? "status-shipped"
        : o.delivery_status.toLowerCase().includes("out for") ? "status-out"
        : "status-pending";

      return `
        <div class="order-card">
          <div class="order-header">
            <span class="order-status ${statusClass}">${o.delivery_status || "Processing"}</span>
            ${o.grand_total != null ? `<span class="order-total">$${o.grand_total.toFixed(2)}</span>` : ""}
          </div>
          ${itemsHtml}
          <div class="order-meta">
            <span>Ordered ${o.order_date}</span>
            ${o.tracking_link ? `<a href="${o.tracking_link}" target="_blank" rel="noopener">Track</a>` : ""}
          </div>
        </div>`;
    }).join("") + '</div>';
  } catch {
    el.innerHTML = '<div class="empty-state">Orders unavailable</div>';
  }
}

async function refreshOrders() {
  const el = document.getElementById("orders-content");
  el.innerHTML = '<div class="empty-state">Refreshing from Amazon...</div>';
  try {
    const res = await fetch("/api/orders/refresh", { method: "POST", headers: authHeadersNoBody() });
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (data.error) {
      el.innerHTML = `<div class="empty-state">${data.error}</div>`;
      return;
    }
  } catch {
    // Fall through to fetch cached data
  }
  fetchOrders();
}

// === Quote Widget ===

async function fetchQuote() {
  const el = document.getElementById("quote-content");
  try {
    const res = await fetch("/api/quote");
    if (!res.ok) throw new Error();
    const data = await res.json();
    el.innerHTML = `
      <div class="quote-text">${data.quote}</div>
      <div class="quote-author">&mdash; ${data.author}</div>
    `;
  } catch {
    el.innerHTML = '<div class="empty-state">Quote unavailable</div>';
  }
}

// === Grocery Widget ===

async function fetchGrocery() {
  const el = document.getElementById("grocery-content");
  const countEl = document.getElementById("grocery-count");
  try {
    const res = await fetch("/api/grocery");
    if (!res.ok) throw new Error();
    const items = await res.json();
    const activeCount = items.filter(i => !i.done).length;
    countEl.textContent = activeCount;

    if (items.length === 0) {
      el.innerHTML = '<div class="empty-state">Grocery list empty</div>';
      return;
    }

    // Group by store
    const grouped = {};
    for (const item of items) {
      if (!grouped[item.store]) grouped[item.store] = [];
      grouped[item.store].push(item);
    }

    el.innerHTML = Object.entries(grouped).map(([store, items]) => `
      <div class="store-group">
        <div class="store-name">${store}</div>
        ${items.map(i => `
          <div class="grocery-item ${i.done ? 'done' : ''}">
            <input type="checkbox" ${i.done ? 'checked' : ''} onchange="toggleGrocery(${i.id}, this.checked)">
            <span>${i.text}</span>
            ${i.quantity ? `<span class="grocery-qty">(${i.quantity})</span>` : ""}
          </div>
        `).join("")}
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Grocery unavailable</div>';
  }
}

async function toggleGrocery(id, done) {
  if (done) {
    await fetch(`/api/grocery/${id}/done`, { method: "POST", headers: authHeadersNoBody() });
  }
  // Refresh after short delay
  setTimeout(fetchGrocery, 300);
}

// === Tasks Widget (unified todos + reminders) ===

let _lastNudgeIds = new Set();

function formatDueDate(dueAt) {
  if (!dueAt) return "";
  const due = new Date(dueAt);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const dueDay = new Date(due.getFullYear(), due.getMonth(), due.getDate());

  if (due < now) return '<span class="task-due task-overdue">Overdue</span>';
  if (dueDay.getTime() === today.getTime()) return '<span class="task-due task-due-today">Today</span>';
  if (dueDay.getTime() === tomorrow.getTime()) return '<span class="task-due">Tomorrow</span>';
  return `<span class="task-due">${due.toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>`;
}

function playNudgeChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.1);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.4);
  } catch {}
}

async function fetchTasks() {
  const el = document.getElementById("tasks-content");
  const countEl = document.getElementById("tasks-count");
  const bannerEl = document.getElementById("tasks-nudge-banner");
  try {
    const res = await fetch("/api/tasks");
    if (!res.ok) throw new Error();
    const data = await res.json();
    const tasks = data.tasks || [];
    const nudges = data.nudges || [];
    const nudgeIds = new Set(nudges.map(n => n.task_id));

    countEl.textContent = tasks.length;

    // Nudge banner
    if (nudges.length > 0) {
      bannerEl.style.display = "";
      bannerEl.innerHTML = `&#9888; ${nudges.length} task${nudges.length > 1 ? "s" : ""} need${nudges.length === 1 ? "s" : ""} attention`;
      // Play chime for new nudges
      const hasNew = nudges.some(n => !_lastNudgeIds.has(n.task_id));
      if (hasNew && _lastNudgeIds.size > 0) playNudgeChime();
    } else {
      bannerEl.style.display = "none";
    }
    _lastNudgeIds = nudgeIds;

    if (tasks.length === 0) {
      el.innerHTML = '<div class="empty-state">No tasks</div>';
      return;
    }

    el.innerHTML = tasks.map(t => {
      const isStale = nudgeIds.has(t.id);
      const priorityCls = t.priority ? `task-priority-${t.priority}` : "";
      const staleCls = isStale ? "task-stale" : "";
      const reminderCls = t.is_reminder ? "task-reminder" : "";
      return `
        <div class="task-item ${priorityCls} ${staleCls} ${reminderCls} ${t.done ? 'done' : ''}">
          <input type="checkbox" ${t.done ? "checked" : ""} onchange="completeTask(${t.id})">
          <span class="task-text">${t.is_reminder ? "&#128276; " : ""}${t.text}</span>
          ${t.for_person ? `<span class="task-person">@${t.for_person}</span>` : ""}
          ${formatDueDate(t.due_at)}
          <button class="task-delete-btn" onclick="deleteTask(${t.id})" title="Delete">&times;</button>
        </div>`;
    }).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Tasks unavailable</div>';
  }
}

async function completeTask(id) {
  await fetch(`/api/tasks/${id}/done`, { method: "POST", headers: authHeadersNoBody() });
  setTimeout(fetchTasks, 300);
}

async function deleteTask(id) {
  await fetch(`/api/tasks/${id}`, { method: "DELETE", headers: authHeadersNoBody() });
  setTimeout(fetchTasks, 300);
}

// === Notes Widget ===

async function fetchNotes() {
  const el = document.getElementById("notes-content");
  try {
    const res = await fetch("/api/notes");
    if (!res.ok) throw new Error();
    const notes = await res.json();

    if (notes.length === 0) {
      el.innerHTML = '<div class="empty-state">No notes</div>';
      return;
    }

    el.innerHTML = notes.map(n => `
      <div class="note-item">
        ${n.pinned ? '<span class="note-pinned">&#9733;</span>' : ""}
        <span>${n.text}</span>
        ${n.for_person ? `<span class="note-person">@${n.for_person}</span>` : ""}
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Notes unavailable</div>';
  }
}


// === Terminal Widget ===

let term = null;
let termWs = null;
let termFitAddon = null;
let termConnected = false;

async function checkTerminalAvailable() {
  try {
    const res = await fetch("/api/terminal/status");
    if (!res.ok) return;
    const data = await res.json();
    if (data.configured) {
      document.getElementById("terminal-section").style.display = "";
    }
  } catch {}
}

function initXterm() {
  if (term) return;
  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'Menlo', 'DejaVu Sans Mono', 'Consolas', monospace",
    theme: {
      background: "#1a1a2e",
      foreground: "#eeeeee",
      cursor: "#e94560",
      selectionBackground: "#0f346080",
      black: "#1a1a2e",
      red: "#e94560",
      green: "#4ade80",
      yellow: "#facc15",
      blue: "#60a5fa",
      magenta: "#c084fc",
      cyan: "#22d3ee",
      white: "#eeeeee",
      brightBlack: "#999999",
      brightRed: "#ef4444",
      brightGreen: "#4ade80",
      brightYellow: "#facc15",
      brightBlue: "#60a5fa",
      brightMagenta: "#c084fc",
      brightCyan: "#22d3ee",
      brightWhite: "#ffffff",
    },
  });
  termFitAddon = new FitAddon.FitAddon();
  term.loadAddon(termFitAddon);
  term.loadAddon(new WebLinksAddon.WebLinksAddon());
  term.open(document.getElementById("terminal-container"));
  termFitAddon.fit();

  // Send resize events to server
  term.onResize(({ cols, rows }) => {
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(JSON.stringify({ type: "resize", cols, rows }));
    }
  });

  // Refit on window resize
  window.addEventListener("resize", () => {
    if (termFitAddon) termFitAddon.fit();
  });
}

function connectTerminal() {
  const password = document.getElementById("terminal-password").value;
  if (!password) {
    alert("Enter terminal password to connect.");
    document.getElementById("terminal-password").focus();
    return;
  }

  initXterm();
  term.clear();

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  let url = `${proto}//${location.host}/api/terminal/ws?token=${encodeURIComponent(password)}`;

  termWs = new WebSocket(url);

  termWs.onopen = () => {
    termConnected = true;
    updateTerminalUI();
    termFitAddon.fit();
    // Send initial size
    const dims = termFitAddon.proposeDimensions();
    if (dims) {
      termWs.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
    }
  };

  termWs.onmessage = (e) => {
    term.write(e.data);
  };

  termWs.onclose = () => {
    termConnected = false;
    updateTerminalUI();
    term.write("\r\n\x1b[90m--- Disconnected ---\x1b[0m\r\n");
  };

  termWs.onerror = () => {
    termConnected = false;
    updateTerminalUI();
  };

  // Forward keystrokes to WebSocket
  term.onData((data) => {
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(data);
    }
  });
}

function disconnectTerminal() {
  if (termWs) {
    termWs.close();
    termWs = null;
  }
  termConnected = false;
  updateTerminalUI();
}

function toggleTerminal() {
  if (termConnected) {
    disconnectTerminal();
  } else {
    connectTerminal();
  }
}

function sendClaudeCommand() {
  if (termWs && termWs.readyState === WebSocket.OPEN) {
    termWs.send("claude\n");
  }
}

function toggleTerminalFullscreen() {
  const section = document.getElementById("terminal-section");
  section.classList.toggle("fullscreen");
  if (termFitAddon) setTimeout(() => termFitAddon.fit(), 100);
}

function updateTerminalUI() {
  const badge = document.getElementById("terminal-status-badge");
  const connectBtn = document.getElementById("terminal-connect-btn");
  const claudeBtn = document.getElementById("terminal-claude-btn");
  const passwordInput = document.getElementById("terminal-password");

  if (termConnected) {
    badge.textContent = "connected";
    badge.className = "badge badge-waiting";
    connectBtn.textContent = "Disconnect";
    claudeBtn.style.display = "";
    passwordInput.style.display = "none";
  } else {
    badge.textContent = "disconnected";
    badge.className = "badge badge-idle";
    connectBtn.textContent = "Connect";
    claudeBtn.style.display = "none";
    passwordInput.style.display = "";
  }
}

// === Refresh all widgets ===

function refreshAll() {
  fetchCalendar();
  fetchWeather();
  fetchSessions();
  fetchSystem();
  fetchNetwork();
  fetchTimers();
  fetchNews();
  fetchOrders();
  fetchGrocery();
  fetchTasks();
  fetchQuote();
  fetchNotes();
}

// === Init ===

checkHealth();
refreshAll();
checkTerminalAvailable();

// Polling intervals
setInterval(checkHealth, 30000);
setInterval(fetchWeather, 300000);    // 5 min
setInterval(fetchNews, 1800000);      // 30 min
setInterval(fetchSessions, 2000);     // 2 sec
setInterval(fetchTimers, 1000);       // 1 sec
setInterval(fetchOrders, 300000);     // 5 min
setInterval(fetchGrocery, 30000);     // 30 sec
setInterval(fetchTasks, 15000);       // 15 sec
setInterval(fetchNotes, 30000);       // 30 sec
setInterval(fetchQuote, 3600000);     // 1 hour
setInterval(fetchSystem, 10000);      // 10 sec
setInterval(fetchNetwork, 30000);     // 30 sec
setInterval(fetchCalendar, 300000);   // 5 min
