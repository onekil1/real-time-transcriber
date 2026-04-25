const $ = (sel) => document.querySelector(sel);
const api = (path, opts = {}) =>
  fetch(path, { headers: { "Content-Type": "application/json" }, ...opts }).then(async (r) => {
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  });

const state = {
  activeId: null,
  recording: false,
  recordingSessionId: null,
  sse: null,
  saveTimer: null,
  templates: [],
};

async function loadTemplates() {
  try {
    state.templates = await api("/api/templates");
  } catch {
    state.templates = [];
  }
  fillChips($("#tmpl-new"), "tmpl-new", state.templates[0]?.key);
  fillChips($("#tmpl-current"), "tmpl-current", null);
}

function fillChips(container, group, selected) {
  if (!container) return;
  container.innerHTML = "";
  for (const t of state.templates) {
    const id = `${group}__${t.key}`;
    const input = document.createElement("input");
    input.type = "radio";
    input.name = group;
    input.id = id;
    input.value = t.key;
    if (selected && t.key === selected) input.checked = true;
    const label = document.createElement("label");
    label.htmlFor = id;
    label.textContent = t.label;
    container.appendChild(input);
    container.appendChild(label);
  }
}

function getChip(container) {
  return container?.querySelector('input[type="radio"]:checked')?.value || null;
}

function setChip(container, value) {
  if (!container) return;
  for (const r of container.querySelectorAll('input[type="radio"]')) {
    r.checked = r.value === value;
  }
}

// ---------- список сессий ----------

async function loadSessions() {
  const list = await api("/api/sessions");
  const el = $("#sessions");
  el.innerHTML = "";
  for (const s of list) {
    const li = document.createElement("li");
    if (s.id === state.activeId) li.classList.add("active");
    li.dataset.id = s.id;
    const date = s.started_at ? new Date(s.started_at * 1000).toLocaleString("ru-RU") : "";
    const dur = s.duration_sec ? ` · ${fmtDur(s.duration_sec)}` : "";
    li.innerHTML = `
      <div class="s-title">${escapeHtml(s.title || "Без названия")}</div>
      <div class="s-meta"><span>${date}${dur}</span><span class="badge ${s.status}">${s.status}</span></div>
    `;
    li.addEventListener("click", () => openSession(s.id));
    el.appendChild(li);
  }
  await pollStatus();
}

async function pollStatus() {
  const status = await api("/api/status").catch(() => null);
  if (!status) return;
  state.recording = status.recording;
  state.recordingSessionId = status.session_id;
  $("#btn-rec").classList.toggle("recording", status.recording);
  $("#btn-rec").textContent = status.recording ? "■ Стоп" : "● Записать";

  setActivity("whisper", !!status.whisper_busy);
  setActivity("llm", !!status.llm_busy);

  const sumBtn = $("#btn-sum-now");
  if (sumBtn) {
    sumBtn.disabled = !state.activeId || status.llm_busy;
    sumBtn.style.opacity = sumBtn.disabled ? 0.5 : 1;
  }
}

function setActivity(k, on) {
  document.querySelectorAll(`.h-dot[data-k="${k}"]`).forEach((el) => {
    el.classList.toggle("busy", on);
  });
  document.querySelectorAll(`.h-activity[data-k="${k}"]`).forEach((el) => {
    el.classList.toggle("on", on);
    if (on && !el.childElementCount) {
      el.innerHTML = '<span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span>';
    }
  });
}

async function openSession(id) {
  state.activeId = id;
  const s = await api(`/api/sessions/${id}`);
  $("#empty").classList.add("hidden");
  $("#glossary-view").classList.add("hidden");
  $("#detail").classList.remove("hidden");
  $("#title").textContent = s.title || "Без названия";
  const started = s.started_at ? new Date(s.started_at * 1000).toLocaleString("ru-RU") : "";
  const dur = s.duration_sec ? fmtDur(s.duration_sec) : "—";
  $("#meta").textContent = `${started} · ${dur} · ${s.source} · ${s.status}`;
  resetProgress();

  // шаблон
  setChip($("#tmpl-current"), s.template);

  // транскрипт
  const segs = s.segments || [];
  $("#transcript").innerHTML = segs.length
    ? segs.map((x) => `<div class="seg"><span class="t">[${fmtTs(x.start_sec)}]</span>${escapeHtml(x.text)}</div>`).join("")
    : '<div class="muted">Транскрипт пока пуст.</div>';

  // отчёт
  const md = s.report?.md || "";
  $("#report-md").value = md;
  renderPreview(md);

  // аудио
  $("#audio").src = `/api/sessions/${id}/audio`;

  // SSE — если сессия ещё обрабатывается
  if (state.sse) { state.sse.close(); state.sse = null; }
  if (["recording", "transcribing", "summarizing", "new"].includes(s.status)) {
    attachSSE(id);
  }

  // подсветка в списке
  document.querySelectorAll(".sessions li").forEach((li) => {
    li.classList.toggle("active", li.dataset.id === id);
  });
}

function attachSSE(id) {
  const es = new EventSource(`/api/sessions/${id}/events`);
  state.sse = es;
  es.onmessage = (e) => {
    const p = JSON.parse(e.data);
    setProgress(p);

    if (p.event === "asr:partial" && p.text) {
      appendPartial(p.start ?? 0, p.text);
    }

    if (p.event === "llm:done") {
      refreshReport(id);
      pollStatus();
    }

    if (p.event === "done" || p.event === "error") {
      es.close();
      state.sse = null;
      loadSessions();
      openSession(id);
    }
  };
  es.onerror = () => { es.close(); state.sse = null; };
}

async function refreshReport(id) {
  if (id !== state.activeId) return;
  try {
    const s = await api(`/api/sessions/${id}`);
    const md = s.report?.md || "";
    const ta = $("#report-md");
    if (ta && ta.value !== md) ta.value = md;
    renderPreview(md);
  } catch {}
}

const PROGRESS_STAGES = ["record", "asr", "llm"];

function resetProgress() {
  document.querySelectorAll("#progress .p-row").forEach((r) => {
    r.classList.remove("active", "done", "error");
    const t = r.querySelector(".p-text");
    if (t) t.textContent = "";
  });
  resetChunkCounter();
}

// Точный счётчик чанков ASR в строке «Транскрибация». Считаем независимо
// от p.chunk (тот — индекс файла-чанка на бекенде, может «сбиваться» при
// паузах). Здесь — просто счётчик событий: started vs done.
const chunkCounter = { started: 0, done: 0 };

function renderChunkCounter() {
  const el = document.getElementById("chunk-counter");
  if (!el) return;
  if (chunkCounter.started === 0) {
    el.textContent = "";
    return;
  }
  const pending = chunkCounter.started - chunkCounter.done;
  const tail = pending > 0 ? `<span class="cc-sep">·</span>в работе: ${pending}` : "";
  el.innerHTML = `<span class="cc-done">${chunkCounter.done}</span> готово${tail}`;
}

function resetChunkCounter() {
  chunkCounter.started = 0;
  chunkCounter.done = 0;
  renderChunkCounter();
}

function bumpChunkCounter(kind) {
  if (kind === "started") chunkCounter.started++;
  if (kind === "done") chunkCounter.done++;
  renderChunkCounter();
}

function hideChunkCounterSoon() {
  // Счётчик остаётся видим до начала следующей сессии (resetChunkCounter
  // вызывается в resetProgress) — пусть пользователь успеет увидеть итог.
}

function setProgressRow(stage, text, status) {
  const row = document.querySelector(`#progress .p-row[data-stage="${stage}"]`);
  if (!row) return;
  // предыдущие фазы помечаем как done, если они были active
  const idx = PROGRESS_STAGES.indexOf(stage);
  PROGRESS_STAGES.forEach((s, i) => {
    if (i >= idx) return;
    const r = document.querySelector(`#progress .p-row[data-stage="${s}"]`);
    if (r && r.classList.contains("active")) {
      r.classList.remove("active");
      r.classList.add("done");
    }
  });
  row.classList.remove("active", "done", "error");
  row.classList.add(status);
  const t = row.querySelector(".p-text");
  if (t) t.textContent = text;
}

function setProgress(p) {
  const pct = p.progress != null ? ` ${Math.round(p.progress * 100)}%` : "";
  // Пользователю показываем 1-based нумерацию (chunk на бекенде 0-based,
  // и это внутренний индекс файла-чанка, а не «номер по порядку»).
  const chunkN = (p.chunk != null) ? (p.chunk + 1) : null;
  switch (p.event) {
    case "recording":         return setProgressRow("record", "Идёт запись...", "active");
    case "recording:stopped": return setProgressRow("record", "Запись остановлена", "done");
    case "uploaded":          return setProgressRow("record", "Файл загружен", "done");
    case "asr:model_load":    return setProgressRow("asr", "Подготовка модели / препроцессинг...", "active");
    case "asr:chunk_start":
      bumpChunkCounter("started");
      return setProgressRow("asr", `Чанк ${chunkN}…`, "active");
    case "asr:chunk_done":
      bumpChunkCounter("done");
      return setProgressRow("asr", `Чанк ${chunkN} готов`, "active");
    case "asr:partial":       return setProgressRow("asr", `Чанк ${chunkN} готов`, "active");
    case "transcribing":      return setProgressRow("asr", `Транскрибация${pct}`, "active");
    case "asr:done":          return setProgressRow("asr", "Транскрибация завершена", "done");
    case "summarizing":       return setProgressRow("llm", "Генерация отчёта...", "active");
    case "llm:start":         return setProgressRow("llm", "Отправка в LLM...", "active");
    case "llm:chunk":         return setProgressRow("llm", `LLM обрабатывает часть${pct}`, "active");
    case "llm:done":          return setProgressRow("llm", "Отчёт готов", "done");
    case "done":
      hideChunkCounterSoon();
      return setProgressRow("llm", "Готово", "done");
    case "error": {
      hideChunkCounterSoon();
      const msg = `Ошибка: ${p.message || ""}`;
      const active = document.querySelector("#progress .p-row.active");
      if (active) {
        active.classList.remove("active");
        active.classList.add("error");
        const t = active.querySelector(".p-text");
        if (t) t.textContent = msg;
      } else {
        setProgressRow("llm", msg, "error");
      }
      return;
    }
  }
}

function appendPartial(startSec, text) {
  const box = $("#transcript");
  const placeholder = box.querySelector(".muted");
  if (placeholder) placeholder.remove();
  const div = document.createElement("div");
  div.className = "seg";
  div.innerHTML = `<span class="t">[${fmtTs(startSec)}]</span>${escapeHtml(text)}`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

// ---------- редактирование названия ----------

const titleEl = $("#title");
const titleInput = $("#title-input");

function startRenaming() {
  if (!state.activeId) return;
  titleInput.value = titleEl.textContent;
  titleInput.dataset.orig = titleEl.textContent;
  titleEl.classList.add("hidden");
  titleInput.classList.remove("hidden");
  titleInput.focus();
  titleInput.select();
}

$("#btn-rename").addEventListener("click", startRenaming);

titleInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); titleInput.blur(); }
  if (e.key === "Escape") { titleInput.value = titleInput.dataset.orig || ""; titleInput.blur(); }
});

titleInput.addEventListener("blur", async () => {
  const newTitle = titleInput.value.trim();
  const orig = titleInput.dataset.orig || "";
  titleInput.classList.add("hidden");
  titleEl.classList.remove("hidden");
  if (!newTitle || newTitle === orig || !state.activeId) {
    titleEl.textContent = orig;
    return;
  }
  const r = await api(`/api/sessions/${state.activeId}`, {
    method: "PATCH",
    body: JSON.stringify({ title: newTitle }),
  });
  titleEl.textContent = r.title;
  loadSessions();
});

// ---------- шаблон / регенерация / DOCX ----------

$("#tmpl-current").addEventListener("change", async (e) => {
  if (!state.activeId) return;
  if (e.target.type !== "radio") return;
  const tmpl = e.target.value;
  await api(`/api/sessions/${state.activeId}`, {
    method: "PATCH",
    body: JSON.stringify({ template: tmpl }),
  });
});

$("#btn-regen").addEventListener("click", async () => {
  if (!state.activeId) return;
  if (!confirm("Пересобрать отчёт по выбранному типу?\n\nТекущий отчёт (по прошлому типу) будет удалён и заменён новым.")) return;
  await api(`/api/sessions/${state.activeId}/regenerate`, { method: "POST" });
  attachSSE(state.activeId);
});

$("#btn-sum-now").addEventListener("click", async () => {
  if (!state.activeId) return;
  try {
    await api(`/api/sessions/${state.activeId}/summarize-now`, { method: "POST" });
    attachSSE(state.activeId);
    pollStatus();
  } catch (e) {
    alert("Не удалось: " + e.message);
  }
});

$("#btn-docx").addEventListener("click", () => {
  if (!state.activeId) return;
  window.location.href = `/api/sessions/${state.activeId}/docx`;
});

// ---------- глобальный глоссарий ----------

async function openGlossary() {
  try {
    const data = await api("/api/glossary");
    $("#glossary-text").value = data.text || "";
  } catch {
    $("#glossary-text").value = "";
  }
  if (state.sse) { state.sse.close(); state.sse = null; }
  state.activeId = null;
  document.querySelectorAll(".sessions li").forEach((li) => li.classList.remove("active"));
  $("#empty").classList.add("hidden");
  $("#detail").classList.add("hidden");
  $("#glossary-view").classList.remove("hidden");
  setGlossaryStatus("");
  updateGlossaryCount();
}

function updateGlossaryCount() {
  const ta = $("#glossary-text");
  const counter = $("#glossary-count");
  if (!ta || !counter) return;
  const n = ta.value.length;
  counter.textContent = n;
  counter.classList.toggle("warn", n > 500 && n <= 800);
  counter.classList.toggle("over", n > 800);
}

$("#glossary-text")?.addEventListener("input", updateGlossaryCount);

function closeGlossary() {
  $("#glossary-view").classList.add("hidden");
  if (state.activeId) {
    $("#detail").classList.remove("hidden");
  } else {
    $("#empty").classList.remove("hidden");
  }
}

async function saveGlossary() {
  const text = ($("#glossary-text").value || "").trim();
  try {
    await api("/api/glossary", {
      method: "PUT",
      body: JSON.stringify({ text }),
    });
    setGlossaryStatus("Сохранено " + new Date().toLocaleTimeString("ru-RU"));
  } catch (e) {
    setGlossaryStatus("Ошибка: " + e.message);
  }
}

$("#btn-glossary-open")?.addEventListener("click", openGlossary);
$("#btn-glossary-close")?.addEventListener("click", closeGlossary);
$("#btn-glossary-save")?.addEventListener("click", saveGlossary);

function setGlossaryStatus(s) {
  document.querySelectorAll(".glossary-status").forEach((el) => { el.textContent = s; });
  if (s) {
    setTimeout(() => {
      document.querySelectorAll(".glossary-status").forEach((el) => {
        if (el.textContent === s) el.textContent = "";
      });
    }, 3000);
  }
}

// ---------- удаление сессии ----------

$("#btn-delete").addEventListener("click", async () => {
  if (!state.activeId) return;
  const title = $("#title").textContent || "сессию";
  if (!confirm(`Удалить «${title}»? Действие необратимо.`)) return;
  await api(`/api/sessions/${state.activeId}`, { method: "DELETE" });
  if (state.sse) { state.sse.close(); state.sse = null; }
  state.activeId = null;
  $("#detail").classList.add("hidden");
  $("#empty").classList.remove("hidden");
  await loadSessions();
});

// ---------- запись ----------

$("#btn-rec").addEventListener("click", async () => {
  if (state.recording) {
    const sid = state.recordingSessionId;
    await api(`/api/sessions/${sid}/stop`, { method: "POST" });
    state.recording = false;
    $("#btn-rec").classList.remove("recording");
    $("#btn-rec").textContent = "● Записать";
    await loadSessions();
    if (sid) openSession(sid);
  } else {
    const tmpl = getChip($("#tmpl-new")) || "meeting";
    const title = state.templates.find((t) => t.key === tmpl)?.label || "Совещание";
    const r = await api("/api/sessions/start", {
      method: "POST",
      body: JSON.stringify({ title, template: tmpl }),
    });
    state.recording = true;
    state.recordingSessionId = r.id;
    $("#btn-rec").classList.add("recording");
    $("#btn-rec").textContent = "■ Стоп";
    await loadSessions();
    openSession(r.id);
  }
});

// ---------- загрузка файла ----------

$("#file-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("title", file.name.replace(/\.[^.]+$/, ""));
  fd.append("template", getChip($("#tmpl-new")) || "meeting");
  const r = await fetch("/api/upload", { method: "POST", body: fd });
  if (!r.ok) { alert("Ошибка загрузки"); return; }
  const data = await r.json();
  await loadSessions();
  openSession(data.id);
  e.target.value = "";
});

// ---------- вкладки ----------

document.querySelectorAll(".tabs button").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    const tab = b.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${tab}`));
  });
});

// ---------- отчёт ----------

$("#report-md").addEventListener("input", (e) => {
  renderPreview(e.target.value);
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => saveReport(), 800);
});

$("#btn-save-report").addEventListener("click", () => saveReport());
$("#btn-copy-report").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("#report-md").value);
  setSaveStatus("Скопировано");
});

async function saveReport() {
  if (!state.activeId) return;
  const md = $("#report-md").value;
  await api(`/api/sessions/${state.activeId}/report`, {
    method: "PATCH",
    body: JSON.stringify({ md }),
  });
  setSaveStatus("Сохранено " + new Date().toLocaleTimeString("ru-RU"));
}

function renderPreview(md) {
  const html = window.marked ? window.marked.parse(md || "") : escapeHtml(md || "");
  $("#report-preview").innerHTML = html;
}

function setSaveStatus(s) {
  document.querySelectorAll(".save-status").forEach((el) => { el.textContent = s; });
  setTimeout(() => {
    document.querySelectorAll(".save-status").forEach((el) => { el.textContent = ""; });
  }, 3000);
}

// ---------- утилиты ----------

function fmtDur(sec) {
  sec = Math.round(sec);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
function fmtTs(sec) {
  sec = Math.round(sec);
  return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
}
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- health-check ----------

async function loadHealth() {
  let h;
  try {
    h = await api("/api/health");
  } catch (e) {
    setHealthDot("whisper", "bad", "недоступно");
    setHealthDot("llm", "bad", "недоступно");
    return;
  }
  const w = h.whisper || {};
  setHealthDot("whisper", w.ok ? "ok" : "bad", w.ok ? "" : (w.error || "ошибка"));

  const l = h.llm || {};
  const lNote = l.ok
    ? (l.active_model || "—")
    : (l.error ? shortErr(l.error) : "офлайн");
  setHealthDot("llm", l.ok ? "ok" : "bad", lNote);
}

function setHealthDot(k, cls, note) {
  document.querySelectorAll(`.h-dot[data-k="${k}"]`).forEach((el) => {
    el.classList.remove("ok", "bad", "pending");
    el.classList.add(cls);
  });
  document.querySelectorAll(`.h-note[data-k="${k}"]`).forEach((el) => {
    el.textContent = note;
    el.title = note;
  });
}

function shortErr(e) {
  return (e || "").split(":").slice(-1)[0].trim().slice(0, 40) || "ошибка";
}

$("#health").addEventListener("click", async () => {
  try {
    const h = await api("/api/health");
    alert(JSON.stringify(h, null, 2));
  } catch (e) {
    alert("Health-check недоступен: " + e.message);
  }
});

// ---------- обновления ----------

const UPDATE_DISMISS_KEY = "ms_update_dismissed";

async function checkForUpdate() {
  let info;
  try {
    info = await api("/api/update/check");
  } catch {
    return;
  }
  if (!info.available) return;
  if (sessionStorage.getItem(UPDATE_DISMISS_KEY) === info.latest) return;

  const banner = $("#update-banner");
  $("#update-banner .upd-text").innerHTML =
    `Доступна новая версия <b>${escapeHtml(info.latest)}</b> (текущая ${escapeHtml(info.current)}).`;
  banner.classList.remove("hidden");

  $("#btn-update-later").onclick = () => {
    sessionStorage.setItem(UPDATE_DISMISS_KEY, info.latest);
    banner.classList.add("hidden");
  };

  $("#btn-update-apply").onclick = async () => {
    const btnEl = $("#btn-update-apply");

    // Режим «Перезагрузить» — кнопка превратилась в перезапуск после успешного
    // обновления. Дёргаем /api/restart и ждём, пока новый процесс поднимется.
    if (btnEl.dataset.action === "restart") {
      btnEl.disabled = true;
      btnEl.textContent = "Перезагружаю…";
      // Запоминаем текущую версию ДО рестарта — так мы поймём, что новый
      // процесс реально поднялся (а не словили ответ от ещё живого старого).
      let oldVersion = "";
      try { oldVersion = (await api("/api/version")).version || ""; } catch {}
      try { await api("/api/restart", { method: "POST" }); } catch {}
      // Сервер сейчас умрёт. Поллим /api/version, пока не вернётся НОВАЯ версия.
      const started = Date.now();
      const tick = async () => {
        try {
          const r = await fetch("/api/version", { cache: "no-store" });
          if (r.ok) {
            const j = await r.json();
            // Версия должна отличаться от старой — иначе это всё ещё старый
            // процесс, который не успел умереть.
            if (j.version && j.version !== oldVersion) {
              location.reload();
              return;
            }
          }
          throw new Error("still old");
        } catch {
          if (Date.now() - started > 60000) {
            btnEl.disabled = false;
            btnEl.textContent = "Перезагрузить";
            alert("Не дождались перезапуска за 60с. Запустите программу вручную.");
            return;
          }
          setTimeout(tick, 700);
        }
      };
      setTimeout(tick, 1500);
      return;
    }

    const notes = info.body ? `\n\nПримечания к релизу:\n${info.body.slice(0, 400)}` : "";
    if (!confirm(
      `Установить версию ${info.latest}?\n\nБудет выполнено git fetch + merge + uv sync. ` +
      `После установки появится кнопка «Перезагрузить».${notes}`
    )) return;

    const btn = $("#btn-update-apply");
    btn.disabled = true;
    btn.textContent = "Обновляю…";

    const upd = $("#update-banner");
    upd.classList.add("updating");
    let progEl = upd.querySelector(".upd-progress");
    if (!progEl) {
      progEl = document.createElement("div");
      progEl.className = "upd-progress";
      progEl.innerHTML = '<div class="upd-step"></div><pre class="upd-log"></pre>';
      upd.appendChild(progEl);
    }
    const stepEl = progEl.querySelector(".upd-step");
    const logEl  = progEl.querySelector(".upd-log");
    stepEl.textContent = "Подключение…";
    logEl.textContent  = "";

    const es = new EventSource("/api/update/apply/stream");
    es.onmessage = (ev) => {
      const evt = JSON.parse(ev.data);
      if (evt.type === "step") {
        stepEl.textContent = `▶ ${evt.label}`;
      } else if (evt.type === "line") {
        logEl.textContent += evt.text + "\n";
        logEl.scrollTop = logEl.scrollHeight;
        // короткий summary для активной строки uv sync / git
        const m = evt.text.match(/(?:Downloading|Resolving|Installing|Building)\s+([^\s]+)/i);
        if (m) stepEl.textContent = `▶ ${m[0]}`;
      } else if (evt.type === "step_done") {
        const ok = evt.code === 0 ? "✓" : "✗";
        logEl.textContent += `${ok} ${evt.label} (код ${evt.code})\n`;
        logEl.scrollTop = logEl.scrollHeight;
      } else if (evt.type === "done") {
        es.close();
        if (evt.ok) {
          $("#update-banner .upd-text").textContent =
            `Версия ${info.latest} установлена.`;
          stepEl.textContent = "✓ Готово";
          btn.disabled = false;
          btn.textContent = "Перезагрузить";
          btn.dataset.action = "restart";
          $("#btn-update-later").textContent = "Закрыть";
        } else {
          stepEl.textContent = `✗ Ошибка на этапе «${evt.step || "?"}»`;
          btn.disabled = false;
          btn.textContent = "Повторить";
        }
      }
    };
    es.onerror = () => {
      es.close();
      stepEl.textContent = "✗ Соединение прервано";
      btn.disabled = false;
      btn.textContent = "Повторить";
    };
  };
}

async function loadAppVersion() {
  try {
    const r = await api("/api/version");
    if (r.version) $("#app-version").textContent = `v${r.version}`;
  } catch {}
}

// ---------- init ----------

loadTemplates().then(loadSessions);
loadHealth();
loadAppVersion();
checkForUpdate();
setInterval(loadSessions, 5000);
setInterval(loadHealth, 15000);
setInterval(checkForUpdate, 60 * 60 * 1000);
