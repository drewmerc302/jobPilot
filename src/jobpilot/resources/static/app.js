// Keyboard shortcuts for list-heavy screens (Matches, job rows)
(function () {
  const STATUSES = ["interested", "applied", "interviewing", "offer", "rejected", "withdrawn"];

  function selectedRow() {
    return document.querySelector(".match-row.focused");
  }

  function rows() {
    return Array.from(document.querySelectorAll(".match-row[data-job-id]"));
  }

  function focusRow(el) {
    rows().forEach((r) => r.classList.remove("focused"));
    if (el) {
      el.classList.add("focused");
      el.scrollIntoView({ block: "nearest" });
    }
  }

  document.addEventListener("keydown", function (e) {
    // Ignore when typing in an input/textarea
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;

    const all = rows();
    const cur = selectedRow();
    const idx = cur ? all.indexOf(cur) : -1;

    if (e.key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      focusRow(all[Math.min(idx + 1, all.length - 1)]);
    } else if (e.key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      focusRow(all[Math.max(idx - 1, 0)]);
    } else if (e.key === "Enter" && cur) {
      const jobId = cur.dataset.jobId;
      if (jobId) window.location = "/matches/" + jobId;
    } else if (e.key === "x" || e.key === "X") {
      if (cur) {
        const btn = cur.querySelector(".dismiss-btn");
        if (btn) btn.click();
      }
    } else if (e.key === "Escape") {
      focusRow(null);
      const dlg = document.getElementById("shortcuts-overlay");
      if (dlg && dlg.open) dlg.close();
    } else if (e.key === "?") {
      const dlg = document.getElementById("shortcuts-overlay");
      if (dlg) {
        if (dlg.open) dlg.close();
        else if (typeof dlg.showModal === "function") dlg.showModal();
        else dlg.setAttribute("open", "");
      }
    }
  });

  // Undo toast when a match row is dismissed (B3.1)
  document.addEventListener("matchDismissed", function (e) {
    const d = e.detail || {};
    const toast = document.getElementById("toast-container");
    if (!toast) return;
    const label = [d.company, d.title].filter(Boolean).join(" — ") || "Match";
    toast.innerHTML =
      `<div class="toast" role="status" aria-live="polite">` +
        `Dismissed ${escapeHtml(label)}. ` +
        `<button type="button" class="btn btn-sm" id="undo-dismiss-btn" ` +
        `style="margin-left:8px;background:transparent;border:1px solid #fff;color:#fff">Undo</button>` +
      `</div>`;
    const undoBtn = document.getElementById("undo-dismiss-btn");
    if (undoBtn) {
      undoBtn.addEventListener("click", function () {
        fetch(`/matches/${encodeURIComponent(d.job_id)}/undismiss`, { method: "POST" })
          .then(() => { window.location.href = "/matches"; });
      });
    }
    setTimeout(() => { toast.innerHTML = ""; }, 8000);
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  // Refresh cost meter when run completes
  document.addEventListener("runComplete", function (e) {
    const detail = e.detail || {};
    htmx.ajax("GET", "/api/cost/meter", { target: "#cost-meter", swap: "outerHTML" });

    const toast = document.getElementById("toast-container");
    if (toast) {
      const jobs = detail.new_jobs ?? 0;
      const matches = detail.new_matches ?? 0;
      const remaining = (detail.remaining ?? 0).toFixed(2);
      toast.innerHTML =
        `<div class="toast">✓ ${jobs} new jobs · ${matches} matches · $${remaining} remaining</div>`;
      setTimeout(() => { toast.innerHTML = ""; }, 6000);
    }
  });

  // Auto-hide the 50% gift-credit banner if user already dismissed it
  (function () {
    if (localStorage.getItem("dismissed_ladder_50")) {
      var b = document.getElementById("key-ladder-50");
      if (b) b.remove();
    }
  })();

  // Drag-and-drop on upload drop zones
  document.querySelectorAll(".drop-zone").forEach(function (zone) {
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      const input = zone.querySelector("input[type=file]");
      if (input && e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        zone.closest("form").submit();
      }
    });
    zone.addEventListener("click", () => zone.querySelector("input[type=file]")?.click());
  });
})();
