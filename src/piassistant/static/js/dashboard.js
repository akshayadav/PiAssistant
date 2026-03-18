// === DOM refs ===
const messagesEl = document.getElementById("messages");
const mainScroll = document.getElementById("main-scroll");
const inputEl = document.getElementById("msg-input");
const sendBtn = document.getElementById("send-btn");
const statusEl = document.getElementById("status");
const timerAlert = document.getElementById("timer-alert");
const timerAlertText = document.getElementById("timer-alert-text");

let sending = false;

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
  sender.textContent = role === "user" ? "You" : "PiAssistant";
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
  sender.textContent = "PiAssistant";
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
      headers: { "Content-Type": "application/json" },
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
    await fetch("/api/reset", { method: "POST" });
    messagesEl.innerHTML = "";
    addMessage("Chat reset. How can I help you?", "bot");
  } catch (err) {
    addMessage(`Reset failed: ${err.message}`, "bot error");
  }
}

async function shutdownPi() {
  if (!confirm("Shut down the Raspberry Pi?")) return;
  try {
    await fetch("/api/shutdown", { method: "POST" });
    addMessage("Shutting down... Safe to unplug in 10 seconds.", "bot");
    statusEl.textContent = "shutting down";
    statusEl.className = "status";
  } catch (err) {
    addMessage(`Shutdown failed: ${err.message}`, "bot error");
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name }),
  });
  input.value = "";
  document.getElementById("weather-add-form").style.display = "none";
  fetchWeather();
}

async function removeWeatherCity(id) {
  await fetch(`/api/weather/cities/${id}`, { method: "DELETE" });
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, type, provider, country: type === "headlines" ? country : "", query: type === "search" ? query : "" }),
  });
  document.getElementById("news-feed-name").value = "";
  document.getElementById("news-feed-query").value = "";
  document.getElementById("news-add-form").style.display = "none";
  fetchNews();
}

async function removeNewsFeed(id) {
  await fetch(`/api/news/feeds/${id}`, { method: "DELETE" });
  fetchNews();
}

function speakNews() {
  if (newsSpeaking) {
    speechSynthesis.cancel();
    return;
  }

  const lines = [];
  for (const feed of newsFeedsData) {
    if (!feed.articles.length) continue;
    lines.push(feed.name + ".");
    for (const a of feed.articles) lines.push(a.title + ".");
  }
  if (!lines.length) return;

  const utterance = new SpeechSynthesisUtterance(lines.join(" "));
  utterance.rate = 0.95;
  utterance.onstart = () => { newsSpeaking = true; setNewsTTSButton(true); };
  utterance.onend = () => { newsSpeaking = false; setNewsTTSButton(false); };
  utterance.onerror = () => { newsSpeaking = false; setNewsTTSButton(false); };
  speechSynthesis.speak(utterance);
}

function setNewsTTSButton(speaking) {
  const btn = document.getElementById("news-tts-btn");
  if (!btn) return;
  btn.textContent = speaking ? "■ Stop" : "▶ Read";
  btn.title = speaking ? "Stop reading" : "Read headlines aloud";
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
    await fetch(`/api/grocery/${id}/done`, { method: "POST" });
  }
  // Refresh after short delay
  setTimeout(fetchGrocery, 300);
}

// === Reminders Widget ===

async function fetchReminders() {
  const el = document.getElementById("reminders-content");
  const countEl = document.getElementById("reminders-count");
  try {
    const res = await fetch("/api/reminders");
    if (!res.ok) throw new Error();
    const reminders = await res.json();
    countEl.textContent = reminders.length;

    if (reminders.length === 0) {
      el.innerHTML = '<div class="empty-state">No reminders</div>';
      return;
    }

    el.innerHTML = reminders.map(r => `
      <div class="reminder-item">
        <input type="checkbox" onchange="completeReminder(${r.id})">
        <span>${r.text}</span>
        ${r.due_at ? `<span class="reminder-due">${r.due_at}</span>` : ""}
        ${r.for_person ? `<span class="reminder-person">@${r.for_person}</span>` : ""}
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Reminders unavailable</div>';
  }
}

async function completeReminder(id) {
  await fetch(`/api/reminders/${id}/done`, { method: "POST" });
  setTimeout(fetchReminders, 300);
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

// === Todos Widget ===

async function fetchTodos() {
  const el = document.getElementById("todos-content");
  const countEl = document.getElementById("todos-count");
  try {
    const res = await fetch("/api/todos");
    if (!res.ok) throw new Error();
    const todos = await res.json();
    countEl.textContent = todos.length;

    if (todos.length === 0) {
      el.innerHTML = '<div class="empty-state">No to-dos</div>';
      return;
    }

    el.innerHTML = todos.map(t => `
      <div class="todo-item ${t.done ? 'done' : ''} ${t.priority ? 'todo-priority-' + t.priority : ''}">
        <input type="checkbox" ${t.done ? 'checked' : ''} onchange="completeTodo(${t.id})">
        <span>${t.text}</span>
      </div>
    `).join("");
  } catch {
    el.innerHTML = '<div class="empty-state">Todos unavailable</div>';
  }
}

async function completeTodo(id) {
  await fetch(`/api/todos/${id}/done`, { method: "POST" });
  setTimeout(fetchTodos, 300);
}

// === Refresh all widgets ===

function refreshAll() {
  fetchWeather();
  fetchSessions();
  fetchTimers();
  fetchNews();
  fetchGrocery();
  fetchReminders();
  fetchNotes();
  fetchTodos();
}

// === Init ===

checkHealth();
refreshAll();

// Polling intervals
setInterval(checkHealth, 30000);
setInterval(fetchWeather, 300000);    // 5 min
setInterval(fetchNews, 1800000);      // 30 min
setInterval(fetchSessions, 2000);     // 2 sec
setInterval(fetchTimers, 1000);       // 1 sec
setInterval(fetchGrocery, 30000);     // 30 sec
setInterval(fetchReminders, 30000);   // 30 sec
setInterval(fetchNotes, 30000);       // 30 sec
setInterval(fetchTodos, 30000);       // 30 sec
