const bridge = window.AstrBotPluginPage;
const logEl = document.getElementById("log");

function log(msg) {
  const line = `[${new Date().toLocaleTimeString()}] ${msg}`;
  logEl.textContent = line + "\n" + logEl.textContent;
}

function listToCsv(arr) {
  return (arr || []).join(", ");
}

function csvToList(s) {
  return String(s || "")
    .split(/[,，\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function renderLevels(levels) {
  const box = document.getElementById("levels");
  box.innerHTML = "";
  (levels || []).forEach((lv) => {
    const span = document.createElement("span");
    span.className = "chip" + (lv.commander_only ? " cmd" : "");
    span.textContent = `${lv.name} ${lv.lo}–${lv.hi}${lv.commander_only ? " ·仅指挥官" : ""}`;
    box.appendChild(span);
  });
}

function renderScores(rows) {
  const box = document.getElementById("scoreTable");
  if (!rows || !rows.length) {
    box.innerHTML = `<p class="muted">暂无记录（互动后写入 data/laffey_affection/scores.json）</p>`;
    return;
  }
  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>
    <th>UID</th><th>分数</th><th>档位</th><th>身份</th><th>封顶</th><th></th>
  </tr></thead>`;
  const tbody = document.createElement("tbody");
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.uid}</td>
      <td>${r.score}</td>
      <td>${r.level}</td>
      <td>${r.is_commander ? "指挥官" : "普通"}</td>
      <td>${r.cap}</td>
      <td></td>`;
    const del = document.createElement("button");
    del.textContent = "删除";
    del.className = "danger";
    del.onclick = async () => {
      if (!confirm(`删除 ${r.uid} 的好感记录？`)) return;
      await bridge.apiPost("scores/delete", { uid: r.uid });
      log("deleted " + r.uid);
      await loadState();
    };
    tr.lastElementChild.appendChild(del);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  box.innerHTML = "";
  box.appendChild(table);
}

async function loadState() {
  const s = await bridge.apiGet("state");
  document.getElementById("enabled").checked = !!s.enabled;
  document.getElementById("inject_prompt").checked = !!s.inject_prompt;
  document.getElementById("gain_at").value = s.gain_at;
  document.getElementById("gain_care").value = s.gain_care;
  document.getElementById("gain_juice").value = s.gain_juice;
  document.getElementById("spam_penalty").value = s.spam_penalty;
  document.getElementById("spam_window_seconds").value = s.spam_window_seconds;
  document.getElementById("spam_threshold").value = s.spam_threshold;
  document.getElementById("gain_cooldown_seconds").value = s.gain_cooldown_seconds;
  document.getElementById("default_score").value = s.default_score;
  document.getElementById("max_score").value = s.max_score;
  document.getElementById("commander_uids").value = listToCsv(s.commander_uids);
  document.getElementById("allow_list_uids").value = listToCsv(s.allow_list_uids);
  document.getElementById("data_dir").value = s.data_dir || "";
  renderLevels(s.levels);
  renderScores(s.scores);
  return s;
}

document.getElementById("saveSettings").onclick = async () => {
  await bridge.apiPost("settings", {
    enabled: document.getElementById("enabled").checked,
    inject_prompt: document.getElementById("inject_prompt").checked,
    gain_at: Number(document.getElementById("gain_at").value),
    gain_care: Number(document.getElementById("gain_care").value),
    gain_juice: Number(document.getElementById("gain_juice").value),
    spam_penalty: Number(document.getElementById("spam_penalty").value),
    spam_window_seconds: Number(document.getElementById("spam_window_seconds").value),
    spam_threshold: Number(document.getElementById("spam_threshold").value),
    gain_cooldown_seconds: Number(document.getElementById("gain_cooldown_seconds").value),
    default_score: Number(document.getElementById("default_score").value),
    max_score: Number(document.getElementById("max_score").value),
    commander_uids: csvToList(document.getElementById("commander_uids").value),
    allow_list_uids: csvToList(document.getElementById("allow_list_uids").value),
    data_dir: document.getElementById("data_dir").value.trim(),
  });
  log("settings saved");
  await loadState();
};

document.getElementById("setScoreBtn").onclick = async () => {
  const uid = document.getElementById("setUid").value.trim();
  const score = Number(document.getElementById("setScore").value);
  if (!uid) return log("missing uid");
  const r = await bridge.apiPost("scores/set", { uid, score });
  log(`set ${r.uid} -> ${r.score} (${r.level})`);
  await loadState();
};

document.getElementById("refreshBtn").onclick = () => loadState().then(() => log("refreshed"));

await bridge.ready();
await loadState();
log("ready");
