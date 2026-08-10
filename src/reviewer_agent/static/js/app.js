(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const STATUS_CLASS = {
    "Met": "status-pill--met",
    "Partially Met": "status-pill--partial",
    "Not Met": "status-pill--not-met",
    "Needs Manual Review": "status-pill--needs-review",
  };

  const STATUS_EMOJI = {
    "Met": "✅",
    "Partially Met": "🟡",
    "Not Met": "❌",
    "Needs Manual Review": "❓",
  };

  const STATUS_COLOR = {
    "Met": "#35c47a",
    "Partially Met": "#e8b93b",
    "Not Met": "#e5566d",
    "Needs Manual Review": "#8b90b3",
  };

  let lastMarkdown = "";
  let lastJson = null;

  function initTabs() {
    document.querySelectorAll(".tabs").forEach((tabGroup) => {
      const groupName = tabGroup.dataset.group;
      const tabs = tabGroup.querySelectorAll(".tab");
      tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
          tabs.forEach((t) => t.classList.remove("active"));
          tab.classList.add("active");
          document
            .querySelectorAll(`[data-tab-panel="${groupName}"]`)
            .forEach((panel) => panel.classList.add("hidden"));
          $(tab.dataset.tab).classList.remove("hidden");
        });
      });
    });
  }

  function initFileLabels() {
    $("requirements-file").addEventListener("change", (e) => {
      $("req-file-name").textContent = e.target.files.length ? e.target.files[0].name : "";
    });
    $("source-folder").addEventListener("change", (e) => {
      $("src-folder-name").textContent = e.target.files.length
        ? `${e.target.files.length} file(s) selected`
        : "";
    });
    $("source-zip").addEventListener("change", (e) => {
      $("src-zip-name").textContent = e.target.files.length ? e.target.files[0].name : "";
    });
  }

  async function loadExampleRequirements() {
    const res = await fetch("/api/example/requirements");
    if (!res.ok) return;
    const data = await res.json();
    $("requirements-text").value = data.text;
    document.querySelector('.tab[data-tab="req-paste"]').click();
  }

  function showError(message) {
    const box = $("error-box");
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function clearError() {
    $("error-box").classList.add("hidden");
    $("error-box").textContent = "";
  }

  function setLoading(isLoading) {
    $("loading-overlay").classList.toggle("hidden", !isLoading);
    $("run-review").disabled = isLoading;
  }

  function buildFormData() {
    const form = new FormData();

    const reqText = $("requirements-text").value;
    const reqFile = $("requirements-file").files[0];
    if (reqFile) {
      form.append("requirements_file", reqFile);
    } else {
      form.append("requirements_text", reqText);
    }

    const useExample = $("use-example-source").checked;
    if (useExample) {
      form.append("use_example_source", "true");
    } else {
      const zipFile = $("source-zip").files[0];
      const folderFiles = $("source-folder").files;
      if (zipFile) {
        form.append("source_zip", zipFile);
      } else if (folderFiles && folderFiles.length) {
        for (const f of folderFiles) {
          const relPath = f.webkitRelativePath || f.name;
          form.append("source_files", f, relPath);
        }
      }
    }

    form.append("top_k", $("opt-top-k").value || "5");
    form.append("min_score", $("opt-min-score").value || "0.02");
    form.append("use_llm", $("opt-use-llm").checked ? "true" : "false");

    return form;
  }

  async function runReview() {
    clearError();
    $("results").classList.add("hidden");

    const form = buildFormData();
    setLoading(true);
    try {
      const res = await fetch("/api/review", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) {
        showError(data.error || "The review failed.");
        return;
      }
      lastMarkdown = data.markdown;
      lastJson = data.report;
      renderResults(data);
    } catch (err) {
      showError(`Network error: ${err}`);
    } finally {
      setLoading(false);
    }
  }

  function renderResults(data) {
    const report = data.report;
    const coveragePct = Math.round(report.overall_coverage * 100);

    const ring = $("coverage-ring");
    ring.style.background = `conic-gradient(#35c47a ${coveragePct * 3.6}deg, #2a2f4a 0deg)`;
    $("coverage-value").textContent = `${coveragePct}%`;

    $("results-meta").textContent =
      `${data.feature_count} feature(s) checked across ${data.file_count} source file(s). ` +
      `Requirements: ${report.requirements_source} · Source: ${report.codebase_source}`;

    const container = $("feature-cards");
    container.innerHTML = "";
    report.features.forEach((feature, idx) => {
      container.appendChild(renderFeatureCard(feature, idx === 0));
    });

    const unmatchedSection = $("unmatched-section");
    const unmatchedList = $("unmatched-list");
    unmatchedList.innerHTML = "";
    if (report.unmatched_files && report.unmatched_files.length) {
      report.unmatched_files.forEach((path) => {
        const li = document.createElement("li");
        li.textContent = path;
        unmatchedList.appendChild(li);
      });
      unmatchedSection.classList.remove("hidden");
    } else {
      unmatchedSection.classList.add("hidden");
    }

    $("results").classList.remove("hidden");
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function statusCounts(criteria) {
    const counts = { "Met": 0, "Partially Met": 0, "Not Met": 0, "Needs Manual Review": 0 };
    criteria.forEach((c) => { counts[c.status] = (counts[c.status] || 0) + 1; });
    return counts;
  }

  function renderFeatureCard(feature, openByDefault) {
    const card = document.createElement("div");
    card.className = "feature-card" + (openByDefault ? " open" : "");

    const counts = statusCounts(feature.criteria);
    const coveragePct = Math.round(feature.coverage * 100);

    const header = document.createElement("div");
    header.className = "feature-card__header";
    header.innerHTML = `
      <div class="feature-card__title">
        <strong>${escapeHtml(feature.id)}: ${escapeHtml(feature.title)}</strong>
        <span>${feature.criteria.length} acceptance criteria · ${feature.matched_files.length} matched file(s)</span>
      </div>
      <div class="feature-card__badges">
        ${badgeIfPositive(counts["Met"], "Met")}
        ${badgeIfPositive(counts["Partially Met"], "Partially Met")}
        ${badgeIfPositive(counts["Not Met"], "Not Met")}
        ${badgeIfPositive(counts["Needs Manual Review"], "Needs Manual Review")}
        <span class="coverage-chip">${coveragePct}%</span>
        <span class="chevron">▶</span>
      </div>
    `;
    header.addEventListener("click", () => card.classList.toggle("open"));

    const body = document.createElement("div");
    body.className = "feature-card__body";

    const desc = feature.description
      ? `<p class="feature-card__desc">${escapeHtml(feature.description)}</p>`
      : "";
    const files = feature.matched_files.length
      ? feature.matched_files.map((f) => `<code>${escapeHtml(f)}</code>`).join(", ")
      : "<em>No matching source files were found.</em>";

    let rowsHtml = "";
    if (!feature.criteria.length) {
      rowsHtml = `<tr><td colspan="4"><em>No acceptance criteria were found for this feature.</em></td></tr>`;
    } else {
      rowsHtml = feature.criteria
        .map((c) => {
          const evidenceHtml = (c.evidence || [])
            .map(
              (e) =>
                `<span class="evidence-line"><code>${escapeHtml(e.file)}:${e.line_number}</code> — ${escapeHtml(e.snippet)}</span>`
            )
            .join("") || "—";
          return `
            <tr>
              <td>${escapeHtml(c.id)}: ${escapeHtml(c.text)}</td>
              <td><span class="status-pill ${STATUS_CLASS[c.status] || ""}">${STATUS_EMOJI[c.status] || ""} ${escapeHtml(c.status)}</span></td>
              <td>${Math.round(c.confidence * 100)}%</td>
              <td>${escapeHtml(c.rationale)}</td>
              <td>${evidenceHtml}</td>
            </tr>
          `;
        })
        .join("");
    }

    body.innerHTML = `
      ${desc}
      <p class="feature-card__files"><strong>Matched files:</strong> ${files}</p>
      <table class="criteria-table">
        <thead>
          <tr><th>Acceptance Criterion</th><th>Status</th><th>Confidence</th><th>Rationale</th><th>Evidence</th></tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    `;

    card.appendChild(header);
    card.appendChild(body);
    return card;
  }

  function badgeIfPositive(count, status) {
    if (!count) return "";
    return `<span class="status-pill ${STATUS_CLASS[status]}">${STATUS_EMOJI[status]} ${count}</span>`;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function downloadFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function init() {
    initTabs();
    initFileLabels();
    $("load-example-req").addEventListener("click", loadExampleRequirements);
    $("run-review").addEventListener("click", runReview);
    $("download-md").addEventListener("click", () => downloadFile("review-report.md", lastMarkdown, "text/markdown"));
    $("download-json").addEventListener("click", () =>
      downloadFile("review-report.json", JSON.stringify(lastJson, null, 2), "application/json")
    );
  }

  document.addEventListener("DOMContentLoaded", init);
})();
