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
  let lastHtml = "";

  let lastGapMarkdown = "";
  let lastGapJson = null;
  let lastTestCasesMarkdown = "";
  let lastTestCasesJson = null;
  let lastReleaseGapMarkdown = "";
  let lastReleaseGapJson = null;

  const SEVERITY_CLASS = { High: "severity-pill--high", Medium: "severity-pill--medium", Low: "severity-pill--low" };
  const SEVERITY_EMOJI = { High: "🔴", Medium: "🟠", Low: "🟡" };

  // Each entry: { id, name, files: File[] } -- one per folder the user has added.
  let folderGroups = [];
  // Each entry: { id, file: File } -- one per .zip archive the user has added.
  let zipEntries = [];
  let nextSourceId = 1;

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
    $("gap-requirements-file").addEventListener("change", (e) => {
      $("gap-req-file-name").textContent = e.target.files.length ? e.target.files[0].name : "";
    });
    $("release-user-stories-file").addEventListener("change", (e) => {
      $("release-user-stories-file-name").textContent = e.target.files.length ? e.target.files[0].name : "";
    });
    $("release-notes-file").addEventListener("change", (e) => {
      $("release-notes-file-name").textContent = e.target.files.length ? e.target.files[0].name : "";
    });
  }

  function initSourceUploads() {
    const folderInput = $("source-folder-input");
    const zipInput = $("source-zip-input");

    $("add-folder-btn").addEventListener("click", () => folderInput.click());
    $("add-zip-btn").addEventListener("click", () => zipInput.click());

    folderInput.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      if (files.length) {
        const topLevelName = (files[0].webkitRelativePath || files[0].name).split("/")[0];
        folderGroups.push({ id: nextSourceId++, name: topLevelName, files });
        renderSourceChips();
      }
      folderInput.value = "";
    });

    zipInput.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      files.forEach((file) => zipEntries.push({ id: nextSourceId++, file }));
      if (files.length) renderSourceChips();
      zipInput.value = "";
    });

    renderSourceChips();
  }

  function renderSourceChips() {
    const folderList = $("folder-chip-list");
    folderList.innerHTML = "";
    folderGroups.forEach((group) => {
      folderList.appendChild(
        makeChip(`${group.name} (${group.files.length} file${group.files.length === 1 ? "" : "s"})`, () => {
          folderGroups = folderGroups.filter((g) => g.id !== group.id);
          renderSourceChips();
        })
      );
    });

    const zipList = $("zip-chip-list");
    zipList.innerHTML = "";
    zipEntries.forEach((entry) => {
      zipList.appendChild(
        makeChip(entry.file.name, () => {
          zipEntries = zipEntries.filter((z) => z.id !== entry.id);
          renderSourceChips();
        })
      );
    });

    $("no-sources-hint").classList.toggle("hidden", folderGroups.length > 0 || zipEntries.length > 0);
  }

  function makeChip(label, onRemove) {
    const li = document.createElement("li");
    li.className = "chip";
    const span = document.createElement("span");
    span.textContent = label;
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "chip__remove";
    removeBtn.textContent = "×";
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", onRemove);
    li.appendChild(span);
    li.appendChild(removeBtn);
    return li;
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
    if (isLoading) $("loading-overlay-text").textContent = "Reviewing source code against requirements\u2026";
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
      folderGroups.forEach((group) => {
        group.files.forEach((f) => {
          const relPath = f.webkitRelativePath || f.name;
          form.append("source_files", f, relPath);
        });
      });
      zipEntries.forEach((entry) => {
        form.append("source_zip", entry.file, entry.file.name);
      });
    }

    form.append("top_k", $("opt-top-k").value || "5");
    form.append("min_score", $("opt-min-score").value || "0.02");
    form.append("use_llm", $("opt-use-llm").checked ? "true" : "false");

    return form;
  }

  async function runReview() {
    clearError();
    $("results").classList.add("hidden");

    const useExample = $("use-example-source").checked;
    if (!useExample && folderGroups.length === 0 && zipEntries.length === 0) {
      showError("Add at least one source folder or .zip archive, or check \"Use bundled example app\".");
      return;
    }

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
      lastHtml = data.html;
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

  // -------------------------------------------------------------------
  // Gap Analysis & Test Case Generation
  // -------------------------------------------------------------------

  async function loadGapExampleRequirements() {
    const res = await fetch("/api/example/requirements");
    if (!res.ok) return;
    const data = await res.json();
    $("gap-requirements-text").value = data.text;
    document.querySelector('.tab[data-tab="gap-req-paste"]').click();
  }

  function showGapError(message) {
    const box = $("gap-error-box");
    box.textContent = message;
    box.classList.remove("hidden");
  }

  function clearGapError() {
    $("gap-error-box").classList.add("hidden");
    $("gap-error-box").textContent = "";
  }

  function setGapLoading(isLoading, text) {
    $("loading-overlay-text").textContent = text || "Working\u2026";
    $("loading-overlay").classList.toggle("hidden", !isLoading);
    $("run-gap-analysis").disabled = isLoading;
    $("run-test-cases").disabled = isLoading;
  }

  function buildGapRequirementsFormData() {
    const form = new FormData();
    const reqText = $("gap-requirements-text").value;
    const reqFile = $("gap-requirements-file").files[0];
    if (reqFile) {
      form.append("requirements_file", reqFile);
    } else {
      form.append("requirements_text", reqText);
    }
    return form;
  }

  function hasGapRequirementsInput() {
    return Boolean($("gap-requirements-text").value.trim()) || Boolean($("gap-requirements-file").files[0]);
  }

  async function runGapAnalysisUI() {
    clearGapError();
    $("gap-results").classList.add("hidden");
    $("tc-results").classList.add("hidden");

    if (!hasGapRequirementsInput()) {
      showGapError("Paste or upload a requirements document first.");
      return;
    }

    setGapLoading(true, "Analyzing requirements for gaps\u2026");
    try {
      const res = await fetch("/api/gap-analysis", { method: "POST", body: buildGapRequirementsFormData() });
      const data = await res.json();
      if (!res.ok) {
        showGapError(data.error || "Gap analysis failed.");
        return;
      }
      lastGapMarkdown = data.markdown;
      lastGapJson = data.report;
      renderGapResults(data);
    } catch (err) {
      showGapError(`Network error: ${err}`);
    } finally {
      setGapLoading(false);
    }
  }

  function renderGapResults(data) {
    const report = data.report;
    const pct = Math.round(report.overall_readiness_score * 100);
    const ring = $("gap-readiness-ring");
    ring.style.background = `conic-gradient(#35c47a ${pct * 3.6}deg, #2a2f4a 0deg)`;
    $("gap-readiness-value").textContent = `${pct}%`;
    $("gap-results-meta").textContent =
      `${data.feature_count} feature(s) analyzed \u00b7 ${report.total_gap_count} gap(s) identified \u00b7 ` +
      `${pct}% of acceptance criteria are ready for test-case generation.`;

    const container = $("gap-feature-cards");
    container.innerHTML = "";
    report.features.forEach((feature, idx) => {
      container.appendChild(renderGapFeatureCard(feature, idx === 0));
    });
    if (report.document_level_design_gaps && report.document_level_design_gaps.length) {
      container.appendChild(renderDocumentLevelGaps(report.document_level_design_gaps));
    }

    $("gap-results").classList.remove("hidden");
    $("gap-results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderFindingsHtml(findings) {
    if (!findings || !findings.length) {
      return "<p class=\"gap-finding\"><em>No gaps identified.</em></p>";
    }
    return findings
      .map(
        (f) => `
        <div class="gap-finding">
          <span class="severity-pill ${SEVERITY_CLASS[f.severity] || ""}">${SEVERITY_EMOJI[f.severity] || ""} ${escapeHtml(f.severity)}</span>
          ${escapeHtml(f.description)}
          <p><strong>Recommendation:</strong> ${escapeHtml(f.recommendation)}</p>
        </div>`
      )
      .join("");
  }

  function renderGapFeatureCard(feature, openByDefault) {
    const card = document.createElement("div");
    card.className = "feature-card" + (openByDefault ? " open" : "");

    const pct = Math.round(feature.readiness_score * 100);
    const header = document.createElement("div");
    header.className = "feature-card__header";
    header.innerHTML = `
      <div class="feature-card__title">
        <strong>${escapeHtml(feature.id)}: ${escapeHtml(feature.title)}</strong>
        <span>${feature.user_story_gaps.length} user-story gap(s) \u00b7 ${feature.design_gaps.length} design gap(s)</span>
      </div>
      <div class="feature-card__badges">
        <span class="coverage-chip">${pct}% test-data ready</span>
        <span class="chevron">\u25b6</span>
      </div>
    `;
    header.addEventListener("click", () => card.classList.toggle("open"));

    const body = document.createElement("div");
    body.className = "feature-card__body";

    let testDataRowsHtml = "";
    if (!feature.test_data_requirements.length) {
      testDataRowsHtml = `<tr><td colspan="3"><em>No acceptance criteria to analyze.</em></td></tr>`;
    } else {
      testDataRowsHtml = feature.test_data_requirements
        .map((r) => {
          const fieldsHtml = r.data_fields.length
            ? r.data_fields.map((f) => `<span class="test-data-chip">${escapeHtml(f)}</span>`).join("")
            : "<em>none identified</em>";
          const missingHtml = r.missing_info.length
            ? r.missing_info.map((m) => `<div>${escapeHtml(m)}</div>`).join("")
            : `<span class="status-pill status-pill--ready">\u2705 Ready</span>`;
          return `
            <tr>
              <td>${escapeHtml(r.criterion_id)}: ${escapeHtml(r.criterion_text)}</td>
              <td>${fieldsHtml}</td>
              <td>${missingHtml}</td>
            </tr>`;
        })
        .join("");
    }

    body.innerHTML = `
      ${feature.description ? `<p class="feature-card__desc">${escapeHtml(feature.description)}</p>` : ""}
      <p class="gap-subheading">User Story Gaps</p>
      ${renderFindingsHtml(feature.user_story_gaps)}
      <p class="gap-subheading">Design Gaps</p>
      ${renderFindingsHtml(feature.design_gaps)}
      <p class="gap-subheading">Mandatory Information for Test-Case Generation</p>
      <table class="criteria-table">
        <thead><tr><th>Acceptance Criterion</th><th>Identified Data Fields</th><th>Missing Mandatory Info</th></tr></thead>
        <tbody>${testDataRowsHtml}</tbody>
      </table>
    `;

    card.appendChild(header);
    card.appendChild(body);
    return card;
  }

  function renderDocumentLevelGaps(findings) {
    const card = document.createElement("div");
    card.className = "feature-card open";
    card.innerHTML = `
      <div class="feature-card__header">
        <div class="feature-card__title">
          <strong>Document-Level Design Gaps</strong>
          <span>Non-functional categories not mentioned anywhere in the document</span>
        </div>
      </div>
      <div class="feature-card__body" style="display:block;">
        ${renderFindingsHtml(findings)}
      </div>
    `;
    return card;
  }

  async function runTestCasesUI() {
    clearGapError();
    $("tc-results").classList.add("hidden");

    if (!hasGapRequirementsInput()) {
      showGapError("Paste or upload a requirements document first.");
      return;
    }

    setGapLoading(true, "Generating draft test cases with test data\u2026");
    try {
      const res = await fetch("/api/test-cases", { method: "POST", body: buildGapRequirementsFormData() });
      const data = await res.json();
      if (!res.ok) {
        showGapError(data.error || "Test case generation failed.");
        return;
      }
      lastTestCasesMarkdown = data.markdown;
      lastTestCasesJson = data.suite;
      renderTestCases(data);
    } catch (err) {
      showGapError(`Network error: ${err}`);
    } finally {
      setGapLoading(false);
    }
  }

  function renderTestCases(data) {
    const suite = data.suite;
    const pct = Math.round(suite.readiness_score * 100);
    const ring = $("tc-readiness-ring");
    ring.style.background = `conic-gradient(#35c47a ${pct * 3.6}deg, #2a2f4a 0deg)`;
    $("tc-readiness-value").textContent = `${pct}%`;
    $("tc-results-meta").textContent =
      `${suite.total_test_cases} test case(s) generated across ${data.feature_count} feature(s) \u00b7 ` +
      `${suite.ready_count} ready to automate as-is (${pct}%).`;

    const tbody = $("tc-table-body");
    tbody.innerHTML = "";
    suite.test_cases.forEach((tc) => {
      const tr = document.createElement("tr");
      const testDataHtml = tc.test_data.map((r) => `<span class="test-data-chip">${escapeHtml(r.field)} = ${escapeHtml(r.value)}</span>`).join("");
      const statusClass = tc.is_ready ? "status-pill--ready" : "status-pill--needs-clarification";
      const statusText = tc.is_ready ? "\u2705 Ready" : "\ud83d\udfe0 Needs Clarification";
      tr.innerHTML = `
        <td><code>${escapeHtml(tc.id)}</code></td>
        <td>${escapeHtml(tc.title)}</td>
        <td>${escapeHtml(tc.type)}</td>
        <td>${escapeHtml(tc.priority)}</td>
        <td>${testDataHtml}</td>
        <td>${escapeHtml(tc.expected_result)}</td>
        <td><span class="status-pill ${statusClass}">${statusText}</span></td>
      `;
      tbody.appendChild(tr);
    });

    $("tc-results").classList.remove("hidden");
    $("tc-results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function exportTestCases(format) {
    if (!hasGapRequirementsInput()) {
      showGapError("Paste or upload a requirements document first.");
      return;
    }
    clearGapError();
    const form = buildGapRequirementsFormData();
    form.append("format", format);
    setGapLoading(true, `Preparing ${format.toUpperCase()} export\u2026`);
    try {
      const res = await fetch("/api/export/test-cases", { method: "POST", body: form });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showGapError(data.error || `Export to ${format} failed.`);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `test-cases.${format === "markdown" ? "md" : format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showGapError(`Network error: ${err}`);
    } finally {
      setGapLoading(false);
    }
  }

  // -------------------------------------------------------------------
  // Release Notes Gap Analyzer
  // -------------------------------------------------------------------

  function showReleaseGapError(message) {
    $("release-gap-error-box").textContent = message;
    $("release-gap-error-box").classList.remove("hidden");
  }

  function buildReleaseGapFormData() {
    const form = new FormData();
    const storiesFile = $("release-user-stories-file").files[0];
    const notesFile = $("release-notes-file").files[0];
    if (storiesFile) form.append("user_stories_file", storiesFile);
    else form.append("user_stories_text", $("release-user-stories-text").value);
    if (notesFile) form.append("release_notes_file", notesFile);
    else form.append("release_notes_text", $("release-notes-text").value);
    return form;
  }

  async function runReleaseGapAnalysisUI() {
    $("release-gap-error-box").classList.add("hidden");
    $("release-gap-results").classList.add("hidden");
    $("loading-overlay-text").textContent = "Comparing User Stories with Development Release Notes\u2026";
    $("loading-overlay").classList.remove("hidden");
    $("run-release-gap-analysis").disabled = true;
    try {
      const res = await fetch("/api/release-gap-analysis", {
        method: "POST",
        body: buildReleaseGapFormData(),
      });
      const data = await res.json();
      if (!res.ok) {
        showReleaseGapError(data.error || "Release gap analysis failed.");
        return;
      }
      lastReleaseGapMarkdown = data.markdown;
      lastReleaseGapJson = data.report;
      renderReleaseGapResults(data.report);
    } catch (err) {
      showReleaseGapError(`Network error: ${err}`);
    } finally {
      $("loading-overlay").classList.add("hidden");
      $("run-release-gap-analysis").disabled = false;
    }
  }

  function renderReleaseGapResults(report) {
    const validation = report.release_validation;
    const passed = validation.validation_status === "PASSED";
    $("release-validation-status").textContent = validation.validation_status;
    $("release-validation-status").className = passed ? "validation-passed" : "validation-failed";
    $("release-validation-meta").textContent =
      `User Stories: ${validation.user_stories_release || "Not identified"} \u00b7 ` +
      `Development Release Notes: ${validation.development_release_notes_release || "Not identified"} \u00b7 ` +
      validation.message;

    const comparison = $("release-gap-comparison");
    comparison.classList.toggle("hidden", !passed);
    if (passed) {
      const summary = report.executive_summary;
      $("release-gap-summary").textContent =
        `${summary.total_user_stories_analyzed} User Story(s) analyzed \u00b7 ` +
        `${summary.total_covered} covered \u00b7 ${summary.total_partially_covered} partially covered \u00b7 ` +
        `${summary.total_missing} missing \u00b7 ${summary.total_contradictory} contradictory \u00b7 ` +
        `${summary.total_needs_clarification} need clarification.`;
      const tbody = $("release-gap-table-body");
      tbody.innerHTML = "";
      report.findings.forEach((finding) => {
        const statusClass = {
          "Covered": "status-pill--met",
          "Partially Covered": "status-pill--partial",
          "Missing": "status-pill--not-met",
          "Contradictory": "status-pill--not-met",
          "Needs Clarification": "status-pill--needs-review",
        }[finding.status] || "";
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${escapeHtml(finding.gap_id || "\u2014")}</td>
          <td>${escapeHtml(finding.ticket)}</td>
          <td>${escapeHtml(finding.feature)}</td>
          <td>${escapeHtml(finding.fact.evidence)}</td>
          <td>${escapeHtml(finding.development_release_note_evidence)}</td>
          <td><span class="status-pill ${statusClass}">${escapeHtml(finding.status)}</span></td>
          <td>${escapeHtml(finding.gap_category)}</td>
          <td>${escapeHtml(finding.recommendation)}</td>
        `;
        tbody.appendChild(tr);
      });
    }
    $("release-gap-results").classList.remove("hidden");
    $("release-gap-results").scrollIntoView({ behavior: "smooth", block: "start" });
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
    initSourceUploads();
    $("load-example-req").addEventListener("click", loadExampleRequirements);
    $("run-review").addEventListener("click", runReview);
    $("download-md").addEventListener("click", () => downloadFile("review-report.md", lastMarkdown, "text/markdown"));
    $("download-json").addEventListener("click", () =>
      downloadFile("review-report.json", JSON.stringify(lastJson, null, 2), "application/json")
    );
    $("download-html").addEventListener("click", () => downloadFile("rci-report.html", lastHtml, "text/html"));
    $("view-html").addEventListener("click", () => {
      const blob = new Blob([lastHtml], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    });

    $("gap-load-example-req").addEventListener("click", loadGapExampleRequirements);
    $("run-gap-analysis").addEventListener("click", runGapAnalysisUI);
    $("run-test-cases").addEventListener("click", runTestCasesUI);
    $("gap-download-md").addEventListener("click", () => downloadFile("gap-report.md", lastGapMarkdown, "text/markdown"));
    $("gap-download-json").addEventListener("click", () =>
      downloadFile("gap-report.json", JSON.stringify(lastGapJson, null, 2), "application/json")
    );
    document.querySelectorAll("[data-export-format]").forEach((btn) => {
      btn.addEventListener("click", () => exportTestCases(btn.dataset.exportFormat));
    });
    $("run-release-gap-analysis").addEventListener("click", runReleaseGapAnalysisUI);
    $("release-gap-download-md").addEventListener("click", () =>
      downloadFile("release-gap-report.md", lastReleaseGapMarkdown, "text/markdown")
    );
    $("release-gap-download-json").addEventListener("click", () =>
      downloadFile("release-gap-report.json", JSON.stringify(lastReleaseGapJson, null, 2), "application/json")
    );
  }

  document.addEventListener("DOMContentLoaded", init);
})();
