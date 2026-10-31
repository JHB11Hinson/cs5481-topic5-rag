/* The whole client: a conversation sidebar with multi-select delete, one transcript,
   and a source drawer. No framework, no build step — this page is read by a demo
   audience, and a page that needs `pnpm` to show a citation is a page that fails in
   front of an audience. */

const state = {
  conversations: [],
  currentId: null,
  selected: new Set(),
  busy: false,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = { error: text }; }
  if (!response.ok) {
    throw new Error((payload && payload.error) || `HTTP ${response.status}`);
  }
  return payload;
}

/* ---------------- sidebar ---------------- */

function renderList() {
  const list = $("conversation-list");
  list.innerHTML = "";
  for (const conversation of state.conversations) {
    const item = document.createElement("li");
    item.className = conversation.id === state.currentId ? "active" : "";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.selected.has(conversation.id);
    box.title = "Select for bulk delete";
    box.addEventListener("click", (event) => event.stopPropagation());
    box.addEventListener("change", () => {
      if (box.checked) state.selected.add(conversation.id);
      else state.selected.delete(conversation.id);
      syncBulkControls();
    });

    const middle = document.createElement("div");
    middle.style.minWidth = "0";
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = conversation.title || "Untitled conversation";
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${conversation.turns} turn(s) · ${conversation.updated_at.replace("T", " ").replace("+00:00", " UTC")}`;
    middle.append(title, meta);

    const del = document.createElement("button");
    del.className = "del";
    del.textContent = "✕";
    del.title = "Delete this conversation";
    del.addEventListener("click", async (event) => {
      event.stopPropagation();
      await bulkDelete([conversation.id]);
    });

    item.append(box, middle, del);
    item.addEventListener("click", () => openConversation(conversation.id));
    list.append(item);
  }
  syncBulkControls();
}

function syncBulkControls() {
  const count = state.selected.size;
  $("delete-selected").disabled = count === 0 || state.busy;
  $("delete-selected").textContent = count ? `Delete selected (${count})` : "Delete selected";
  const all = $("select-all");
  all.checked = state.conversations.length > 0 && count === state.conversations.length;
}

async function refreshList() {
  const payload = await api("/api/conversations");
  state.conversations = payload.conversations;
  for (const id of Array.from(state.selected)) {
    if (!state.conversations.some((c) => c.id === id)) state.selected.delete(id);
  }
  renderList();
}

async function bulkDelete(ids) {
  if (!ids.length) return;
  const label = ids.length === 1 ? "this conversation" : `${ids.length} conversations`;
  if (!confirm(`Delete ${label}? This removes the stored transcript and cannot be undone.`)) return;
  state.busy = true;
  syncBulkControls();
  try {
    const result = await api("/api/conversations", {
      method: "DELETE",
      body: JSON.stringify({ ids }),
    });
    for (const id of result.deleted) state.selected.delete(id);
    if (result.missing.length) {
      setStatus(`Deleted ${result.deleted.length}; ${result.missing.length} no longer existed.`);
    } else {
      setStatus(`Deleted ${result.deleted.length} conversation(s).`);
    }
    if (result.deleted.includes(state.currentId)) {
      state.currentId = null;
      $("transcript").innerHTML = "";
      $("conversation-title").textContent = "New conversation";
      $("conversation-meta").textContent = "";
    }
    await refreshList();
    if (!state.currentId && state.conversations.length) {
      await openConversation(state.conversations[0].id);
    }
  } catch (error) {
    setStatus(`Delete failed: ${error.message}`);
  } finally {
    state.busy = false;
    syncBulkControls();
  }
}

/* ---------------- transcript ---------------- */

function addUserTurn(text) {
  const wrap = document.createElement("div");
  wrap.className = "turn user";
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = text;
  wrap.append(body);
  $("transcript").append(wrap);
  scrollToEnd();
}

function addAssistantTurn(content, payload, isError = false) {
  const wrap = document.createElement("div");
  wrap.className = "turn assistant";
  const body = document.createElement("div");
  body.className = "body" + (isError ? " error" : "");
  body.textContent = content;
  wrap.append(body);

  const chips = document.createElement("div");
  chips.className = "chips";
  for (const claim of (payload && payload.claims) || []) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = claim.marker;
    chip.title = `${claim.doc_title || ""} ${claim.heading_path ? "› " + claim.heading_path : ""}`.trim();
    chip.addEventListener("click", () => openCitation(claim.citation));
    chips.append(chip);
  }
  if (payload && payload.abstained) {
    const note = document.createElement("span");
    note.className = "chip abstain";
    note.textContent = "abstained";
    note.title = payload.abstain_reason || "the documentation does not answer this";
    chips.append(note);
  }
  if (chips.children.length) wrap.append(chips);
  $("transcript").append(wrap);
  scrollToEnd();
}

function scrollToEnd() {
  const transcript = $("transcript");
  transcript.scrollTop = transcript.scrollHeight;
}

async function openConversation(id) {
  state.currentId = id;
  renderList();
  try {
    const payload = await api(`/api/conversations/${encodeURIComponent(id)}`);
    $("conversation-title").textContent = payload.conversation.title || "Untitled conversation";
    $("conversation-meta").textContent =
      `${id} · ${payload.conversation.turns} turn(s) · last used ${payload.conversation.updated_at}`;
    $("transcript").innerHTML = "";
    for (const turn of payload.messages) {
      if (turn.role === "user") addUserTurn(turn.content);
      else addAssistantTurn(turn.content, turn.payload);
    }
    setStatus("");
  } catch (error) {
    setStatus(`Could not open ${id}: ${error.message}`);
  }
}

/* ---------------- asking ---------------- */

async function ask(question) {
  if (state.busy) { setStatus("One question at a time — the index is single-tenant."); return; }
  state.busy = true;
  $("ask").disabled = true;
  setStatus("Retrieving and answering…");
  addUserTurn(question);
  try {
    if (!state.currentId) {
      const created = await api("/api/conversations", { method: "POST", body: "{}" });
      state.currentId = created.id;
    }
    const payload = await api(`/api/conversations/${encodeURIComponent(state.currentId)}/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
    addAssistantTurn(payload.rendered, payload.payload);
    $("conversation-title").textContent = payload.conversation.title || "Untitled conversation";
    const response = payload.response;
    setStatus(
      `retrieval ${response.retrieval_ms.toFixed(0)} ms · generation ${response.generation_ms.toFixed(0)} ms · ` +
      `${response.verified_claims}/${response.claims.length} claims verified · ${response.config_name}`
    );
    await refreshList();
  } catch (error) {
    addAssistantTurn(`**The answer did not arrive.** ${error.message}`, null, true);
    setStatus(`Failed: ${error.message}`);
  } finally {
    state.busy = false;
    $("ask").disabled = false;
  }
}

/* ---------------- source drawer ---------------- */

async function openCitation(citation) {
  if (!citation) return;
  try {
    const props = await api("/api/citation", { method: "POST", body: JSON.stringify({ payload: citation }) });
    $("drawer-title").textContent = `Source ${props.marker || ""} — ${props.doc_title || ""}`;
    const bits = [];
    if (props.heading_path) bits.push(props.heading_path);
    if (props.url) bits.push(props.url);
    $("drawer-meta").textContent = bits.join(" · ");
    // The server already escaped the chunk and wrapped the cited span in <mark>; using
    // `chunk_html` keeps one escaping rule in one place instead of two.
    if (props.chunk_html) {
      $("drawer-text").innerHTML = props.chunk_html;
    } else {
      $("drawer-text").textContent = props.span_text || "";
    }
    $("drawer").classList.remove("hidden");
  } catch (error) {
    setStatus(`Citation could not be opened: ${error.message}`);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function setStatus(text) { $("status").textContent = text; }

/* ---------------- wiring ---------------- */

$("new-chat").addEventListener("click", async () => {
  try {
    const created = await api("/api/conversations", { method: "POST", body: "{}" });
    await refreshList();
    await openConversation(created.id);
    $("question").focus();
  } catch (error) {
    setStatus(`Could not create a conversation: ${error.message}`);
  }
});

$("select-all").addEventListener("change", (event) => {
  state.selected = event.target.checked ? new Set(state.conversations.map((c) => c.id)) : new Set();
  renderList();
});

$("delete-selected").addEventListener("click", () => bulkDelete(Array.from(state.selected)));

$("rename").addEventListener("click", async () => {
  if (!state.currentId) return;
  const current = $("conversation-title").textContent;
  const next = prompt("Conversation title", current);
  if (next === null) return;
  try {
    await api(`/api/conversations/${encodeURIComponent(state.currentId)}`, {
      method: "PATCH",
      body: JSON.stringify({ title: next }),
    });
    $("conversation-title").textContent = next || "Untitled conversation";
    await refreshList();
  } catch (error) {
    setStatus(`Rename failed: ${error.message}`);
  }
});

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (!question) return;
  $("question").value = "";
  ask(question);
});

$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

$("drawer-close").addEventListener("click", () => $("drawer").classList.add("hidden"));

(async function boot() {
  try {
    const config = await api("/api/config");
    $("config-line").textContent =
      `${config.configuration} · ${config.chunks} chunks · ${config.retrieval} k=${config.k}`;
  } catch (error) {
    $("config-line").textContent = `configuration unavailable: ${error.message}`;
  }
  await refreshList();
  if (state.conversations.length) await openConversation(state.conversations[0].id);
  else {
    const created = await api("/api/conversations", { method: "POST", body: "{}" });
    await refreshList();
    await openConversation(created.id);
  }
})();
