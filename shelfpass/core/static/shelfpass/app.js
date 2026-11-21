/* Shelfpass — progressive enhancements. Every page works without JavaScript. */
(function () {
  "use strict";

  // Tiny DOM builder that never interprets strings as HTML.
  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "text") el.textContent = value;
      else if (key === "class") el.className = value;
      else el.setAttribute(key, value === true ? "" : value);
    });
    for (var i = 2; i < arguments.length; i++) {
      var child = arguments[i];
      if (child === null || child === undefined || child === false) continue;
      el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return el;
  }

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  function normalize(s) {
    return (s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, " ").replace(/^(the|a|an) /, "").trim();
  }

  function formatDate(iso, monthOnly) {
    if (!iso) return "";
    var d = new Date(iso + "T12:00:00");
    var opts = monthOnly ? { month: "short", year: "numeric" } : { month: "short", day: "numeric", year: "numeric" };
    return d.toLocaleDateString(undefined, opts);
  }

  // ------------------------------------------------------------ generic ---

  document.addEventListener("change", function (e) {
    if (e.target.matches("[data-autosubmit]")) e.target.form.submit();
  });

  document.addEventListener("submit", function (e) {
    var form = e.target;
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) e.preventDefault();
  });

  document.addEventListener("click", function (e) {
    var printBtn = e.target.closest("[data-print]");
    if (printBtn) { e.preventDefault(); window.print(); return; }

    var copyBtn = e.target.closest("[data-copy-target]");
    if (copyBtn) {
      var target = document.getElementById(copyBtn.getAttribute("data-copy-target"));
      if (target && navigator.clipboard) {
        navigator.clipboard.writeText(target.textContent).then(function () {
          var label = copyBtn.querySelector("[data-label]") || copyBtn;
          var old = label.textContent;
          label.textContent = "Copied";
          setTimeout(function () { label.textContent = old; }, 1500);
        });
      }
    }
  });

  // ------------------------------------------------------------- intake ---

  var intake = document.getElementById("intake-form");
  if (intake) initIntake(intake);

  function initIntake(form) {
    var facilitySelect = form.querySelector("select[name='facility']");
    var idInput = form.querySelector("input[name='inmate_id']");
    var personField = form.querySelector("input[name='person_id']");
    var rulesUrl = form.getAttribute("data-rules-url");
    var personUrl = form.getAttribute("data-person-url");
    var sentTitles = [];

    var panel = document.getElementById("rule-panel");
    var empty = document.getElementById("rules-empty");
    var link = document.getElementById("rules-link");
    var slugs = {};

    // Facility <option> values are primary keys; the rules endpoint wants slugs.
    // The server renders slugs in data attributes when it can; fall back to the label.
    Array.prototype.forEach.call(facilitySelect.options, function (opt) {
      if (opt.dataset.slug) slugs[opt.value] = opt.dataset.slug;
    });

    function renderRules(data) {
      empty.hidden = true;
      panel.hidden = false;
      link.hidden = false;
      link.href = data.url;
      document.getElementById("rules-name").textContent = data.name;
      var verified = document.getElementById("rules-verified");
      verified.textContent = (data.is_sample ? "Sample data · " : "") +
        (data.last_verified ? "Rules last verified " + formatDate(data.last_verified) : "Rules not verified yet");

      var chips = document.getElementById("rules-chips");
      clear(chips);
      data.badges.forEach(function (b) {
        chips.appendChild(h("span", { class: "chip " + b.level, title: b.detail || null, text: b.label }));
      });

      var notes = document.getElementById("rules-notes");
      clear(notes);
      data.notes.forEach(function (n) { notes.appendChild(h("li", { text: n })); });

      var address = document.getElementById("rules-address");
      clear(address);
      var name = form.querySelector("input[name='name']").value || "Name";
      var id = idInput.value || "ID";
      var housing = form.querySelector("input[name='housing']").value || "";
      var recipient = (data.recipient_format || "{name} #{id}")
        .replace("{name}", name).replace("{id}", id).replace("{housing}", housing)
        .replace(/,\s*$/, "").replace(/\s+/g, " ");
      [recipient].concat(data.address).forEach(function (line, i) {
        address.appendChild(h(i === 0 ? "strong" : "span", { text: line }));
        address.appendChild(h("br"));
      });

      var rej = document.getElementById("rules-rejections");
      clear(rej);
      var r = data.rejections;
      if (r.total) {
        rej.appendChild(h("div", { class: "eyebrow", text: r.total + " rejection" + (r.total === 1 ? "" : "s") + " in the last " + Math.round(r.window_days / 30) + " months" }));
        var list = h("ul", { class: "mini-list" });
        r.reasons.forEach(function (reason) {
          list.appendChild(h("li", {}, h("span", { text: reason.label }), h("strong", { text: String(reason.count) })));
        });
        rej.appendChild(list);
        if (r.recent.length) {
          var recent = h("ul", { class: "mini-list", style: "margin-top:.6rem" });
          r.recent.forEach(function (e) {
            recent.appendChild(h("li", {},
              h("span", { class: "muted", style: "white-space:nowrap", text: formatDate(e.date, e.month_only) }),
              h("span", { text: (e.title ? "“" + e.title + "” — " : "") + e.reason })));
          });
          rej.appendChild(recent);
        }
      } else {
        rej.appendChild(h("p", { class: "small muted", text: "No rejections logged here in the last year." }));
      }
    }

    function loadRules() {
      var value = facilitySelect.value;
      if (!value) { panel.hidden = true; empty.hidden = false; link.hidden = true; return; }
      var slug = slugs[value];
      if (!slug) return;
      getJSON(rulesUrl.replace("SLUG", encodeURIComponent(slug))).then(renderRules).catch(function () {});
    }

    facilitySelect.addEventListener("change", loadRules);
    ["name", "housing"].forEach(function (n) {
      form.querySelector("input[name='" + n + "']").addEventListener("input", debounce(loadRules, 400));
    });
    loadRules();

    // ---- returning readers
    var matchBox = document.getElementById("person-match");

    function renderMatches(matches) {
      clear(matchBox);
      if (!matches.length) {
        matchBox.hidden = true;
        personField.value = "";
        sentTitles = [];
        checkDuplicates();
        return;
      }
      var m = matches[0];
      matchBox.hidden = false;
      var useBox = h("input", { type: "checkbox", id: "use-match", checked: true });
      matchBox.appendChild(h("div", { class: "row-between" },
        h("div", {},
          h("div", { class: "who", text: "Returning reader: " + m.name + " #" + m.inmate_id }),
          h("div", { class: "small", text: (m.facility || "No facility on file") + " · " + m.letters + " letter" + (m.letters === 1 ? "" : "s") + (m.last_letter ? ", last " + formatDate(m.last_letter) : "") })),
        h("a", { class: "btn btn-sm", href: m.url, target: "_blank", rel: "noopener", text: "View history" })));
      if (m.sent.length) {
        matchBox.appendChild(h("div", { class: "small", style: "margin-top:.5rem", text: "Already sent (" + m.sent_total + "): " + m.sent.map(function (s) { return s.title; }).join(" · ") }));
      }
      if (!m.active) matchBox.appendChild(h("div", { class: "small", style: "margin-top:.4rem", text: "Marked inactive — check whether they were released." }));
      matchBox.appendChild(h("label", { class: "check small", style: "margin-top:.6rem" }, useBox, " Use this record (update their facility if they moved)"));
      useBox.addEventListener("change", function () { personField.value = useBox.checked ? m.id : ""; });
      personField.value = m.id;
      if (!form.querySelector("input[name='name']").value) form.querySelector("input[name='name']").value = m.name;
      var housingInput = form.querySelector("input[name='housing']");
      if (!housingInput.value && m.housing) housingInput.value = m.housing;
      if (!facilitySelect.value && m.facility_id) { facilitySelect.value = String(m.facility_id); loadRules(); }
      sentTitles = m.sent;
      checkDuplicates();
    }

    var lookup = debounce(function () {
      var value = idInput.value.trim();
      if (value.replace(/[^0-9a-z]/gi, "").length < 3) { renderMatches([]); return; }
      getJSON(personUrl + "?inmate_id=" + encodeURIComponent(value)).then(function (d) { renderMatches(d.matches); }).catch(function () {});
    }, 350);
    idInput.addEventListener("input", lookup);
    if (idInput.value) lookup();

    // ---- already-sent warnings while typing
    var sentBox = document.getElementById("already-sent");
    function checkDuplicates() {
      clear(sentBox);
      var hits = [];
      form.querySelectorAll("input[name$='-description']").forEach(function (input) {
        var typed = normalize(input.value);
        if (typed.length < 4) return;
        sentTitles.forEach(function (s) {
          var title = normalize(s.title);
          if (title === typed || title.indexOf(typed) === 0 || typed.indexOf(title) === 0) hits.push(s);
        });
      });
      sentBox.hidden = !hits.length;
      hits.forEach(function (s) {
        sentBox.appendChild(h("div", { text: "Already sent “" + s.title + "”" + (s.date ? " on " + formatDate(s.date) : "") + "." }));
      });
    }
    form.addEventListener("input", function (e) { if (e.target.name && /-description$/.test(e.target.name)) checkDuplicates(); });

    // ---- dynamic item rows (Django formset)
    var rows = document.getElementById("item-rows");
    var total = form.querySelector("input[name='items-TOTAL_FORMS']");
    var template = document.getElementById("item-template");
    document.getElementById("add-item").addEventListener("click", function () {
      var index = parseInt(total.value, 10);
      var html = template.innerHTML.replace(/__prefix__/g, String(index));
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html; // server-rendered template, no user data
      var row = wrapper.firstElementChild;
      rows.appendChild(row);
      total.value = String(index + 1);
      row.querySelector("input").focus();
    });
    rows.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-remove-row]");
      if (!btn) return;
      var row = btn.closest("[data-item-row]");
      row.querySelectorAll("input").forEach(function (i) { i.value = ""; });
      if (rows.querySelectorAll("[data-item-row]").length > 1) row.hidden = true;
      checkDuplicates();
    });
  }

  // ------------------------------------------------- Open Library lookup ---

  var lookupBox = document.getElementById("ol-lookup");
  if (lookupBox) initLookup(lookupBox);

  function initLookup(box) {
    var input = box.querySelector("input[type='search']");
    var button = box.querySelector("button");
    var results = document.getElementById("ol-results");
    var url = box.getAttribute("data-url");
    var form = document.getElementById("book-form");

    function fill(book) {
      var set = function (name, value) {
        var el = form.querySelector("[name='" + name + "']");
        if (el && value !== undefined && value !== null && value !== "") el.value = value;
      };
      set("title", book.title);
      set("authors", book.authors);
      set("isbn", book.isbn);
      set("publisher", book.publisher);
      set("year", book.year);
      set("openlibrary_key", book.openlibrary_key);
      set("cover_id", book.cover_id);
      set("subjects_text", (book.subjects || []).join(", "));
      (book.content_flags || []).forEach(function (flag) {
        var cb = form.querySelector("input[name='content_flags'][value='" + flag + "']");
        if (cb) cb.checked = true;
      });
      clear(results);
      results.appendChild(h("div", { class: "alert alert-success", text: "Filled in from Open Library. Check the format and condition of your copy." }));
      form.querySelector("[name='format']").focus();
    }

    function search() {
      var q = input.value.trim();
      if (!q) return;
      clear(results);
      results.appendChild(h("p", { class: "small muted", text: "Searching Open Library…" }));
      getJSON(url + "?q=" + encodeURIComponent(q)).then(function (data) {
        clear(results);
        if (!data.results.length) {
          results.appendChild(h("p", { class: "small muted", text: "No matches (or Open Library is unreachable). You can type the details yourself." }));
          return;
        }
        data.results.forEach(function (book) {
          var cover = h("div", { class: "cover" }, book.cover_url ? h("img", { src: book.cover_url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : (book.title || "?").slice(0, 2).toUpperCase());
          var pick = h("button", { type: "button", class: "btn btn-sm", text: "Use" });
          pick.addEventListener("click", function () { fill(book); });
          results.appendChild(h("div", { class: "suggestion" }, cover,
            h("div", {},
              h("div", { class: "title", text: book.title }),
              h("div", { class: "small muted", text: [book.authors, book.year, book.isbn].filter(Boolean).join(" · ") })),
            pick));
        });
      }).catch(function () {
        clear(results);
        results.appendChild(h("p", { class: "small muted", text: "Open Library is unreachable right now. You can type the details yourself." }));
      });
    }
    button.addEventListener("click", search);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); search(); } });
  }
})();
