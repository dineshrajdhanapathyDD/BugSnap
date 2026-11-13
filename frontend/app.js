(function () {
  "use strict";
  const API = (window.BUGSNAP_CONFIG && window.BUGSNAP_CONFIG.apiUrl || "").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  const MAX_FILE = 5 * 1024 * 1024;
  const STATUSES = ["open", "in_progress", "resolved", "closed"];
  const STATUS_LABEL = { open: "Open", in_progress: "In progress", resolved: "Resolved", closed: "Closed" };

  async function api(path, options) {
    const res = await fetch(API + path, options);
    let body = null;
    try { body = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) {
      const err = new Error((body && body.error && body.error.message) || "Request failed (" + res.status + ")");
      err.body = body;
      throw err;
    }
    return body;
  }

  function el(tag, props, children) {
    const n = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (k === "className") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v);
    });
    (children || []).forEach((c) => n.appendChild(c));
    return n;
  }

  function badge(value, prefix) {
    return el("span", { className: "badge " + (prefix ? prefix + "-" : "") + value, text: value });
  }

  // ----- list + stats
  async function loadBugs() {
    const q = new URLSearchParams();
    if ($("f-severity").value) q.set("severity", $("f-severity").value);
    if ($("f-status").value) q.set("status", $("f-status").value);
    $("list-msg").textContent = "Loading...";
    $("list-msg").classList.remove("error");
    try {
      const data = await api("/bugs" + (q.toString() ? "?" + q : ""));
      renderStats(data.stats);
      renderRows(data.bugs);
      $("list-msg").textContent = data.count === 0 ? "No bugs match the current filters." : "";
    } catch (e) {
      $("list-msg").textContent = "Could not load bugs: " + e.message;
      $("list-msg").classList.add("error");
    }
  }

  function renderStats(s) {
    $("stat-total").textContent = s.total;
    $("stat-open").textContent = s.open;
    $("stat-resolved").textContent = s.resolved;
    $("stat-high").textContent = s.high_priority;
  }

  function renderRows(bugs) {
    const tbody = $("bug-rows");
    tbody.replaceChildren();
    bugs.forEach((b) => {
      const select = el("select", { "aria-label": "Status for " + b.title });
      STATUSES.forEach((s) => {
        const o = el("option", { value: s, text: STATUS_LABEL[s] });
        if (s === b.status) o.selected = true;
        select.appendChild(o);
      });
      select.addEventListener("change", async () => {
        select.disabled = true;
        try { await api("/bugs/" + encodeURIComponent(b.bug_id), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: select.value }) }); }
        catch (e) { alert("Update failed: " + e.message); }
        loadBugs();
      });
      const titleCell = el("td", { className: "title" }, [
        el("div", { className: "t", text: b.title }),
        el("div", { className: "d", text: b.description }),
      ]);
      if (b.attachment_key) {
        const link = el("a", { href: "#", text: "View screenshot" });
        link.addEventListener("click", async (ev) => {
          ev.preventDefault();
          try {
            const full = await api("/bugs/" + encodeURIComponent(b.bug_id));
            window.open(full.attachment_url, "_blank", "noopener");
          } catch (e) { alert(e.message); }
        });
        titleCell.appendChild(link);
      }
      tbody.appendChild(el("tr", {}, [
        titleCell,
        el("td", {}, [badge(b.severity, "sev")]),
        el("td", { text: b.priority }),
        el("td", {}, [select]),
        el("td", { text: new Date(b.created_at).toLocaleString() }),
      ]));
    });
  }

  // ----- workflow status panel
  function renderWorkflow(result, failed) {
    const wf = result.workflow || {};
    const box = $("workflow");
    box.replaceChildren();
    const ok = !failed && wf.status === "SUCCEEDED";
    const steps = ["ValidateBug", "SaveBug", "PrioritizeBug"];
    const list = el("ul", { className: "steps" });
    steps.forEach((s, i) => {
      let cls = "";
      if (ok) cls = "done";
      else if (failed && i === 0) cls = "failed"; // validation is the only expected failure point
      list.appendChild(el("li", { className: cls, text: s }));
    });
    box.appendChild(el("strong", { className: ok ? "" : "error", text: ok ? "Workflow SUCCEEDED" : "Workflow " + (wf.status || "FAILED") }));
    box.appendChild(list);
    const dl = el("dl");
    const add = (k, v) => { if (v !== undefined && v !== null) { dl.appendChild(el("dt", { text: k })); dl.appendChild(el("dd", { text: String(v) })); } };
    add("Execution", wf.execution_name);
    add("Duration", wf.duration_ms !== undefined ? wf.duration_ms + " ms" : undefined);
    if (ok) {
      add("Bug ID", result.bug_id);
      add("Priority", result.priority);
      add("Result", result.workflow_status);
    } else if (result.error) {
      add("Error", result.error.code);
      add("Details", (result.error.details || [result.error.message]).join("; "));
    }
    box.appendChild(dl);
  }

  // ----- submit
  async function uploadScreenshot(file) {
    const presign = await api("/uploads", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content_type: file.type }) });
    const put = await fetch(presign.upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
    if (!put.ok) throw new Error("Screenshot upload failed (" + put.status + ")");
    return presign.attachment_key;
  }

  $("bug-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const msg = $("form-msg");
    msg.className = "";
    msg.textContent = "";
    const file = $("screenshot").files[0];
    if (file && file.size > MAX_FILE) { msg.className = "error"; msg.textContent = "Screenshot must be 5 MB or smaller."; return; }

    $("submit-btn").disabled = true;
    msg.textContent = "Submitting...";
    try {
      const payload = { title: $("title").value, description: $("description").value, severity: $("severity").value };
      if (file) payload.attachment_key = await uploadScreenshot(file);
      const result = await api("/bugs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      renderWorkflow(result, false);
      msg.className = "ok";
      msg.textContent = "Bug created with priority " + result.priority + ".";
      $("bug-form").reset();
      loadBugs();
    } catch (e) {
      msg.className = "error";
      const details = e.body && e.body.error && e.body.error.details;
      msg.textContent = e.message + (details ? ": " + details.join("; ") : "");
      if (e.body && e.body.workflow) renderWorkflow(e.body, true);
    } finally {
      $("submit-btn").disabled = false;
    }
  });

  $("f-severity").addEventListener("change", loadBugs);
  $("f-status").addEventListener("change", loadBugs);
  $("refresh-btn").addEventListener("click", loadBugs);

  if (!API) {
    $("list-msg").textContent = "API URL is not configured (config.js).";
    $("list-msg").classList.add("error");
  } else {
    loadBugs();
  }
})();
