const bridge = window.AstrBotPluginPage;
const logEl = document.getElementById("log");
let currentTag = null;

function log(msg) {
  const line = `[${new Date().toLocaleTimeString()}] ${msg}`;
  logEl.textContent = line + "\n" + logEl.textContent;
}

async function loadState() {
  const s = await bridge.apiGet("state");
  document.getElementById("enabled").checked = !!s.enabled;
  document.getElementById("cooldown_minutes").value = s.cooldown_minutes;
  document.getElementById("daily_cap").value = s.daily_cap;
  document.getElementById("quiet_start_hour").value = s.quiet_start_hour;
  document.getElementById("quiet_end_hour").value = s.quiet_end_hour;
  document.getElementById("max_per_reply").value = s.max_per_reply;
  document.getElementById("stickers_root").value = s.stickers_root || "";
  document.getElementById("dailyStat").textContent = `今日已发 ${s.daily_count}/${s.daily_cap}`;
  renderTags(s.tags || {}, s.tag_image_counts || {});
  if (currentTag) await loadGallery(currentTag);
  return s;
}

function renderTags(tags, counts) {
  const box = document.getElementById("tagList");
  box.innerHTML = "";
  Object.keys(tags).sort().forEach((tag) => {
    const div = document.createElement("div");
    div.className = "tag" + (tag === currentTag ? " active" : "");
    div.innerHTML = `<strong>${tag}</strong> <span class="meta">(${counts[tag] || 0} 张)</span>
      <div class="meta">触发：${(tags[tag] || []).join("，") || "（无）"}</div>
      <div class="row">
        <button data-act="select">管理图片</button>
        <button data-act="edit">填入编辑</button>
        <button data-act="del" class="danger">删除标签</button>
      </div>`;
    div.querySelector('[data-act="select"]').onclick = () => selectTag(tag);
    div.querySelector('[data-act="edit"]').onclick = () => {
      document.getElementById("newTag").value = tag;
      document.getElementById("newTriggers").value = (tags[tag] || []).join(", ");
    };
    div.querySelector('[data-act="del"]').onclick = async () => {
      if (!confirm(`删除标签 ${tag}？目录图片可保留。`)) return;
      await bridge.apiPost("tags/delete", { tag, delete_files: false });
      log("deleted tag " + tag);
      if (currentTag === tag) currentTag = null;
      await loadState();
    };
    box.appendChild(div);
  });
}

async function selectTag(tag) {
  currentTag = tag;
  document.getElementById("currentTagLabel").textContent = tag;
  document.getElementById("uploadBtn").disabled = false;
  await loadState();
}

async function loadGallery(tag) {
  const data = await bridge.apiGet("images", { tag });
  const gal = document.getElementById("gallery");
  gal.innerHTML = "";
  for (const file of data.files || []) {
    const card = document.createElement("div");
    card.className = "thumb";
    const img = document.createElement("img");
    img.alt = file;
    img.title = file;
    card.appendChild(img);
    const cap = document.createElement("div");
    cap.className = "meta";
    cap.textContent = file;
    card.appendChild(cap);
    const del = document.createElement("button");
    del.textContent = "删除";
    del.className = "danger";
    del.onclick = async () => {
      await bridge.apiPost("images/delete", { tag, file });
      log("deleted " + file);
      await loadGallery(tag);
      await loadState();
    };
    card.appendChild(del);
    gal.appendChild(card);
    try {
      const prev = await bridge.apiGet("images/preview_b64", { tag, file });
      if (prev && prev.data_url) img.src = prev.data_url;
    } catch (e) {
      img.alt = file + " (预览失败)";
    }
  }
}

document.getElementById("saveSettings").onclick = async () => {
  await bridge.apiPost("settings", {
    enabled: document.getElementById("enabled").checked,
    cooldown_minutes: Number(document.getElementById("cooldown_minutes").value),
    daily_cap: Number(document.getElementById("daily_cap").value),
    quiet_start_hour: Number(document.getElementById("quiet_start_hour").value),
    quiet_end_hour: Number(document.getElementById("quiet_end_hour").value),
    max_per_reply: Number(document.getElementById("max_per_reply").value),
    stickers_root: document.getElementById("stickers_root").value,
  });
  log("settings saved");
  await loadState();
};

document.getElementById("upsertTag").onclick = async () => {
  const tag = document.getElementById("newTag").value.trim();
  const triggers = document.getElementById("newTriggers").value;
  await bridge.apiPost("tags/upsert", { tag, triggers });
  log("upsert tag " + tag);
  await selectTag(tag);
};

document.getElementById("uploadBtn").onclick = async () => {
  const input = document.getElementById("fileInput");
  if (!currentTag || !input.files?.[0]) return;
  const result = await bridge.upload(`images/upload/${encodeURIComponent(currentTag)}`, input.files[0]);
  log("uploaded " + JSON.stringify(result));
  input.value = "";
  await loadGallery(currentTag);
  await loadState();
};

document.getElementById("refreshBtn").onclick = () => loadState();

await bridge.ready();
await loadState();
log("ready");
