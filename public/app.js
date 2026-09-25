(function () {
  "use strict";

  const state = {
    cases: [],
    filters: { verdict: null, status: null, pattern: null },
    selected: null,
  };

  const fmtUsd = (n) =>
    "$" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const patternLabel = (p) => {
    if (!p || p === "none") return "no pattern matched";
    if (p === "undocumented") return "undocumented pattern";
    return p.replace(/_/g, " ");
  };

  function els() {
    return {
      stats: document.getElementById("stats"),
      filters: document.getElementById("filters"),
      list: document.getElementById("caseList"),
      detail: document.getElementById("detail"),
    };
  }

  function computeStats(cases) {
    const total = cases.length;
    const fraud = cases.filter((c) => c.case.verdict === "fraud").length;
    const legit = cases.filter((c) => c.case.verdict === "legitimate").length;
    const uncertain = cases.filter((c) => c.case.verdict === "uncertain").length;
    const sars = cases.filter((c) => c.sar.file).length;
    const exposure = cases.reduce((s, c) => s + (c.case.exposure_usd || 0), 0);
    const patterns = new Set(cases.map((c) => c.case.pattern).filter((p) => p && p !== "none"));
    return { total, fraud, legit, uncertain, sars, exposure, patterns: patterns.size };
  }

  function renderStats(cases) {
    const s = computeStats(cases);
    const { stats } = els();
    stats.innerHTML = `
      <div class="stat"><div class="value">${s.total}</div><div class="label">Cases investigated</div></div>
      <div class="stat fraud"><div class="value">${s.fraud}</div><div class="label">Confirmed fraud</div></div>
      <div class="stat legit"><div class="value">${s.legit}</div><div class="label">Cleared legitimate</div></div>
      <div class="stat"><div class="value">${s.uncertain}</div><div class="label">Escalated / uncertain</div></div>
      <div class="stat"><div class="value">${fmtUsd(s.exposure)}</div><div class="label">Total exposure</div></div>
      <div class="stat"><div class="value">${s.sars}</div><div class="label">SARs filed</div></div>
    `;
  }

  function count(cases, key, value) {
    return cases.filter((c) => {
      if (key === "verdict") return c.case.verdict === value;
      if (key === "status") return c.case.status === value;
      if (key === "pattern") return c.case.pattern === value;
      return false;
    }).length;
  }

  function renderFilters(cases) {
    const { filters } = els();
    const verdicts = ["fraud", "uncertain", "legitimate"];
    const statuses = [...new Set(cases.map((c) => c.case.status))];
    const patterns = [...new Set(cases.map((c) => c.case.pattern))];

    const group = (title, key, values, labelFn) => `
      <div>
        <div class="filter-group__title">${title}</div>
        <div class="filter-group">
          ${values
            .map((v) => {
              const active = state.filters[key] === v;
              return `<button class="chip${active ? " active" : ""}" data-key="${key}" data-value="${v}">
                <span>${labelFn ? labelFn(v) : v.replace(/_/g, " ")}</span>
                <span class="n">${count(cases, key, v)}</span>
              </button>`;
            })
            .join("")}
        </div>
      </div>
    `;

    filters.innerHTML =
      group("Verdict", "verdict", verdicts) +
      group("Status", "status", statuses) +
      group("Pattern", "pattern", patterns, patternLabel) +
      `<button class="chip" id="clearFilters"><span>Clear filters</span></button>`;

    filters.querySelectorAll(".chip[data-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.key;
        const value = btn.dataset.value;
        state.filters[key] = state.filters[key] === value ? null : value;
        render();
      });
    });
    filters.querySelector("#clearFilters").addEventListener("click", () => {
      state.filters = { verdict: null, status: null, pattern: null };
      render();
    });
  }

  function applyFilters(cases) {
    return cases.filter((c) => {
      if (state.filters.verdict && c.case.verdict !== state.filters.verdict) return false;
      if (state.filters.status && c.case.status !== state.filters.status) return false;
      if (state.filters.pattern && c.case.pattern !== state.filters.pattern) return false;
      return true;
    });
  }

  function renderList(filtered) {
    const { list } = els();
    if (filtered.length === 0) {
      list.innerHTML = `<div class="detail__empty"><p>No cases match the current filters.</p></div>`;
      return;
    }
    list.innerHTML = filtered
      .map((c) => {
        const finalRoute = c.next_best_actions.final[0]?.route || "auto";
        const selected = state.selected === c.case_id;
        return `
        <div class="case-card${selected ? " selected" : ""}" data-id="${c.case_id}">
          <div class="case-card__top">
            <span class="case-card__id">${c.case_id}</span>
            <span class="case-card__amt">${fmtUsd(c.case.exposure_usd)}</span>
          </div>
          <p class="case-card__summary">${c.case.summary}</p>
          <div class="case-card__tags">
            <span class="tag verdict-${c.case.verdict}">${c.case.verdict}</span>
            <span class="tag route-${finalRoute}">${finalRoute}</span>
            ${c.sar.file ? '<span class="tag sar">SAR</span>' : ""}
          </div>
        </div>`;
      })
      .join("");

    list.querySelectorAll(".case-card").forEach((card) => {
      card.addEventListener("click", () => {
        state.selected = card.dataset.id;
        render();
      });
    });
  }

  function actionColumn(stage, actions) {
    return `
      <div class="action-col">
        <div class="stage">${stage}</div>
        ${actions
          .map(
            (a) => `<div class="action-pill">
              <span class="name">${a.action.replace(/_/g, " ")}</span>
              <span class="tag route-${a.route}">${a.route}</span>
            </div>`
          )
          .join("")}
      </div>`;
  }

  function renderDetail(cases) {
    const { detail } = els();
    const c = cases.find((x) => x.case_id === state.selected);
    if (!c) {
      detail.innerHTML = `<div class="detail__empty"><p>Select a case from the list to open its file.</p></div>`;
      return;
    }

    const trigger = c.trigger || {};
    const initial = c.next_best_actions.initial || [];
    const final = c.next_best_actions.final || [];

    detail.innerHTML = `
      <div class="detail__inner">
        <div class="detail__header">
          <div>
            <h2>${c.case_id}</h2>
            <div class="sub">${trigger.opened_at || ""} &middot; opened via <b>${(trigger.trigger_type || "").replace(/_/g, " ")}</b> &middot; graph ref <code>${c.case.graph_case_id || "—"}</code></div>
          </div>
          <div class="detail__stamp verdict-${c.case.verdict}">${c.case.verdict}</div>
        </div>

        <div class="section">
          <h3 class="section__title">Trigger</h3>
          <p class="summary-text">${trigger.trigger_text || "—"}</p>
        </div>

        <div class="section">
          <h3 class="section__title">Case summary</h3>
          <p class="summary-text">${c.case.summary}</p>
          <div class="kv-grid" style="margin-top:16px;">
            <div class="kv"><div class="k">Status</div><div class="v">${c.case.status.replace(/_/g, " ")}</div></div>
            <div class="kv"><div class="k">Pattern</div><div class="v">${patternLabel(c.case.pattern)}</div></div>
            <div class="kv"><div class="k">Fraud probability</div><div class="v">${c.case.fraud_probability}</div></div>
            <div class="kv"><div class="k">Exposure</div><div class="v">${fmtUsd(c.case.exposure_usd)}</div></div>
            <div class="kv"><div class="k">Connected cards</div><div class="v">${c.case.connected_card_ids.length ? c.case.connected_card_ids.join(", ") : "—"}</div></div>
            <div class="kv"><div class="k">Similar prior cases</div><div class="v">${c.case.similar_prior_cases.length ? c.case.similar_prior_cases.join(", ") : "—"}</div></div>
          </div>
        </div>

        <div class="section">
          <h3 class="section__title">Evidence</h3>
          ${c.case.evidence
            .map(
              (e) => `<div class="evidence-item">
                <div class="claim">${e.claim}</div>
                <div class="meta"><span class="src">${e.source}</span>${e.ref}</div>
              </div>`
            )
            .join("")}
        </div>

        ${
          c.evidence_requests && c.evidence_requests.length
            ? `<div class="section">
                <h3 class="section__title">Evidence requested</h3>
                ${c.evidence_requests
                  .map(
                    (r) => `<div class="evidence-item">
                      <div class="claim">${r.type.replace(/_/g, " ")} &mdash; asked after step ${r.asked_after_step}</div>
                      <div class="meta">${r.assumed_response}</div>
                    </div>`
                  )
                  .join("")}
              </div>`
            : ""
        }

        <div class="section">
          <h3 class="section__title">Next best action</h3>
          <div class="action-flow">
            ${actionColumn("Before evidence", initial)}
            <div class="arrow">&rarr;</div>
            ${actionColumn("After evidence", final)}
          </div>
          ${c.next_best_actions.what_changed ? `<div class="what-changed">${c.next_best_actions.what_changed}</div>` : ""}
        </div>

        <div class="section">
          <h3 class="section__title">Suspicious activity report</h3>
          ${
            c.sar.file
              ? `<div class="sar-box">
                  <div class="kv-grid">
                    <div class="kv"><div class="k">Subjects</div><div class="v">${c.sar.subjects.join(", ") || "—"}</div></div>
                    <div class="kv"><div class="k">Amount</div><div class="v">${fmtUsd(c.sar.total_amount_usd)}</div></div>
                    <div class="kv"><div class="k">Activity dates</div><div class="v">${c.sar.activity_dates.join(", ") || "—"}</div></div>
                  </div>
                  <div class="narrative">${c.sar.narrative}</div>
                </div>`
              : `<p class="no-sar">Not filed &mdash; ${c.sar.reason || "policy threshold not met"}.</p>`
          }
        </div>

        <div class="section">
          <h3 class="section__title">Stop reason</h3>
          <p class="stop-reason">${c.stop_reason}</p>
        </div>

        <div class="section">
          <h3 class="section__title">Agent footprint</h3>
          <div class="agent-stats">
            <span><b>${c.tool_calls}</b> tool calls</span>
            <span><b>${c.tokens.toLocaleString()}</b> tokens</span>
            <span><b>${c.latency_s}s</b> latency</span>
          </div>
        </div>
      </div>
    `;
  }

  function render() {
    const filtered = applyFilters(state.cases);
    renderFilters(state.cases);
    renderList(filtered);
    renderDetail(state.cases);
  }

  fetch("data/cases.json")
    .then((r) => r.json())
    .then((cases) => {
      state.cases = cases;
      renderStats(cases);
      render();
    })
    .catch((err) => {
      document.getElementById("caseList").innerHTML =
        `<div class="detail__empty"><p>Could not load case data: ${err.message}</p></div>`;
    });
})();
