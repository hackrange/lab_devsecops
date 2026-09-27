/*
 * The Local Lab control panel.  Every value from the server goes into the page
 * as text (textContent), never as HTML, so nothing it says can run as script.
 *
 * Author: Tim Rice
 */
(function () {
  "use strict";
  var POLL_MS = 5000;
  var state = null;
  var cards = {};
  var totpTimer = null;

  var $ = function (id) { return document.getElementById(id); };

  function api(path, body) {
    var opts = { credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.headers["X-HR-Request"] = "1";       // the server refuses changes without it
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { j._status = r.status; return j; });
    });
  }

  function gb(bytes) { return (bytes / 1073741824).toFixed(1) + " GB"; }
  function mb(bytes) { return bytes >= 1073741824 ? gb(bytes) : Math.round(bytes / 1048576) + " MB"; }
  function level(pct) { return pct >= 85 ? "high" : pct >= 60 ? "warn" : ""; }

  function setMeter(key, pct, value, note) {
    var bar = $(key + "-bar");
    bar.style.width = Math.min(100, Math.max(0, pct)) + "%";
    bar.className = level(pct);
    $(key + "-value").textContent = value;
    $(key + "-note").textContent = note;
  }

  var STATE_TEXT = {
    "running": "Running", "starting": "Starting", "stopping": "Stopping", "stopped": "Stopped",
    "not-installed": "Not installed yet", "cluster-stopped": "Cluster stopped", "missing": "Not set up",
    "resetting": "Resetting",
    "unknown": "Checking"
  };

  function copyButton(text) {
    var b = document.createElement("button");
    b.className = "small";
    b.textContent = "Copy";
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(text).then(function () {
        b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1200);
      });
    });
    return b;
  }

  function kv(label, value, secret) {
    var row = document.createElement("div");
    row.className = "kv";
    var l = document.createElement("span"); l.textContent = label;
    var c = document.createElement("code");
    row.appendChild(l); row.appendChild(c);
    if (secret) {
      c.textContent = "••••••••"; c.className = "secret masked";
      var show = document.createElement("button"); show.className = "small"; show.textContent = "Show";
      show.addEventListener("click", function () {
        var hidden = c.classList.toggle("masked");
        c.textContent = hidden ? "••••••••" : value;
        show.textContent = hidden ? "Show" : "Hide";
      });
      row.appendChild(show);
    } else {
      c.textContent = value;
    }
    row.appendChild(copyButton(value));
    return row;
  }

  function buildCard(comp) {
    var node = document.getElementById("component-template").content.firstElementChild.cloneNode(true);
    node.querySelector(".comp-name").textContent = comp.name;
    node.querySelector(".comp-week").textContent = comp.week;
    node.querySelector(".comp-desc").textContent = comp.desc;
    node.querySelector(".comp-start").addEventListener("click", function () { act(comp, "start"); });
    node.querySelector(".comp-stop").addEventListener("click", function () {
      if (confirm("Stop " + comp.name + "?  It stays stopped until you start it again (or the machine restarts).")) {
        act(comp, "stop");
      }
    });
    var reset = node.querySelector(".comp-reset");
    if (comp.resettable) {
      reset.hidden = false;
      reset.addEventListener("click", function () { resetOne(comp); });
    }
    $("components").appendChild(node);
    cards[comp.id] = node;
    return node;
  }

  function fillService(node, svc, door) {
    // Rebuilt only when something in it changed (the two step code, every 30
    // seconds), so a password the student chose to show stays shown.
    var sig = JSON.stringify([svc, door], function (k, v) { return k === "seconds" ? undefined : v; });
    if (node.dataset.sig === sig) return;
    node.dataset.sig = sig;
    var links = node.querySelector(".comp-links");
    var creds = node.querySelector(".comp-creds");
    links.textContent = ""; creds.textContent = "";
    if (!svc) return;
    var url = door === "lab" ? svc.inside : svc.outside;
    if (url) {
      var a = document.createElement("a");
      a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = url;
      links.appendChild(a);
    }
    svc.creds.forEach(function (pair) {
      if (pair[1]) creds.appendChild(kv(pair[0], pair[1], /password|token/.test(pair[0])));
    });
    if (svc.totp && svc.totp.code) {
      var row = document.createElement("div"); row.className = "kv";
      var l = document.createElement("span"); l.textContent = "two step code";
      var c = document.createElement("code"); c.className = "totp"; c.dataset.totp = "1";
      c.dataset.seconds = String(svc.totp.seconds); c.textContent = svc.totp.code + "  (" + svc.totp.seconds + "s)";
      row.appendChild(l); row.appendChild(c);
      // Copies the code showing when it is clicked (the text is refreshed as
      // the code changes), without the seconds countdown.
      var cb = document.createElement("button");
      cb.className = "small"; cb.textContent = "Copy";
      cb.addEventListener("click", function () {
        navigator.clipboard.writeText(c.textContent.split(" ")[0]).then(function () {
          cb.textContent = "Copied"; setTimeout(function () { cb.textContent = "Copy"; }, 1200);
        });
      });
      row.appendChild(cb);
      creds.appendChild(row);
    }
    if (svc.note) {
      var n = document.createElement("p"); n.className = "hint"; n.textContent = svc.note;
      creds.appendChild(n);
    }
  }

  function render() {
    var s = state, h = s.host || {};
    if (h.memory) {
      setMeter("cpu", h.cpu || 0, (h.cpu || 0).toFixed(0) + "%", h.cores + " cores, load " + (h.load || 0).toFixed(2));
      var mp = 100 * h.memory.used / h.memory.total;
      setMeter("mem", mp, mp.toFixed(0) + "%", gb(h.memory.used) + " of " + gb(h.memory.total) + " in use");
      var dp = 100 * h.disk.used / h.disk.total;
      setMeter("disk", dp, dp.toFixed(0) + "%", gb(h.disk.total - h.disk.used) + " free of " + gb(h.disk.total));
    }

    var acc = s.info.access;
    var pass = $("acc-pass");
    pass.dataset.value = acc.password;
    if (!pass.dataset.shown) { pass.textContent = "••••••••"; pass.classList.add("masked"); }
    else { pass.textContent = acc.password; }
    var web = $("acc-web"); web.href = acc.web_host; web.textContent = acc.web_host;
    $("acc-ssh").textContent = acc.ssh_host;
    $("acc-rdp").textContent = acc.rdp_host;
    $("acc-where").textContent = s.door === "lab"
      ? "You are in the lab desktop now.  The addresses above are for your own computer, on the same network."
      : "You are on your own computer.  The lab services open at the addresses on their cards below.";

    var services = {};
    s.info.services.forEach(function (x) { services[x.id] = x; });
    var running = 0, total = 0;
    s.components.forEach(function (comp) {
      var node = cards[comp.id] || buildCard(comp);
      var pill = node.querySelector(".comp-state");
      pill.textContent = STATE_TEXT[comp.state] || comp.state;
      pill.className = "pill comp-state pill-" + comp.state;
      var u = comp.usage || {};
      node.querySelector(".comp-usage").textContent =
        (comp.state === "running" || comp.state === "starting") ? ("CPU " + (u.cpu || 0).toFixed(1) + "%   Memory " + mb(u.mem || 0)) : "";
      var busy = comp.state === "starting" || comp.state === "stopping" || comp.state === "resetting";
      node.querySelector(".comp-reset").disabled = busy;
      var installed = comp.state !== "not-installed" && comp.state !== "cluster-stopped" && comp.state !== "missing";
      // One button at a time: Stop when it runs, Start when it is stopped,
      // a solid grey "Working..." while something is happening.
      var start = node.querySelector(".comp-start"), stop = node.querySelector(".comp-stop");
      start.hidden = comp.state === "running" || !installed;
      stop.hidden = !(comp.state === "running" || busy) || !installed;
      stop.disabled = busy;
      stop.textContent = busy ? "Working..." : "Stop";
      var err = node.querySelector(".comp-error");
      err.hidden = !comp.error; err.textContent = comp.error ? "Last try: " + comp.error : "";
      fillService(node, services[comp.id], s.door);
      if (comp.state !== "not-installed") { total++; if (comp.state === "running") running++; }
    });

    var sum = $("summary");
    if (running === total) { sum.textContent = "All running"; sum.className = "pill pill-running"; }
    else { sum.textContent = running + " of " + total + " running"; sum.className = "pill pill-starting"; }
    var ws = s.workstation || {};
    $("ws-usage").textContent = ws.running ? "CPU " + (ws.cpu || 0).toFixed(1) + "%   Memory " + mb(ws.mem || 0) : "not running";
    resetBanner(s.reset || {});
    $("updated").textContent = "Updated " + new Date().toLocaleTimeString();
    startTotpTicker();
  }

  function startTotpTicker() {
    if (totpTimer) return;
    totpTimer = setInterval(function () {
      document.querySelectorAll("[data-totp]").forEach(function (c) {
        var left = parseInt(c.dataset.seconds, 10) - 1;
        if (left <= 0) { refresh(); return; }
        c.dataset.seconds = String(left);
        c.textContent = c.textContent.split(" ")[0] + "  (" + left + "s)";
      });
    }, 1000);
  }

  // What each reset deletes, in words a student understands.
  var RESET_WHAT = {
    forgejo: "your repositories, pull requests and pipeline history on the Git server.  Git Code Review is reset with it, because it scans those repositories.  You get a fresh Git account",
    forgerepo: "your package registry rules and its download cache.  You get a fresh registry token and portal account",
    gcr: "your scans and findings in Git Code Review.  You get a fresh account",
    cluster: "everything in your Kubernetes cluster: every namespace, deployment and Helm release you made.  You get a fresh, empty cluster",
    keycloak: "every realm, client and user you made in Keycloak",
    kong: "every service, route, consumer and plugin you made in Kong",
    grafana: "your Grafana dashboards, and the logs and traces kept in Loki and Tempo"
  };
  var RESTARTS = { forgejo: 1, forgerepo: 1, gcr: 1 };

  function resetOne(comp) {
    var text = "Reset " + comp.name + " to how a fresh install left it?\n\n" +
      "This deletes " + RESET_WHAT[comp.id] + ".  It cannot be undone." +
      (RESTARTS[comp.id] ? "\n\nYour lab desktop restarts with the new login, and gets a new password: push any work first." : "");
    if (!confirm(text)) return;
    api("api/components/" + comp.id + "/reset", { confirm: comp.id }).then(function (r) {
      if (r._status === 401) return showLogin();
      if (!r.ok) alert(r.message || "The reset did not start.");
      refresh();
    });
  }

  function resetBanner(st) {
    var b = $("reset-banner");
    var names = { all: "the whole lab" };
    (state.components || []).forEach(function (c) { names[c.id] = c.name; });
    var what = names[st.target] || st.target;
    if (st.state === "running") {
      b.className = "banner"; b.hidden = false;
      b.textContent = "Resetting " + what + ".  This takes a few minutes; this page updates when it is done." +
        (st.target === "all" || RESTARTS[st.target] ? "  Your lab desktop will restart, so this page may disconnect: open it again in a few minutes." : "");
    } else if (st.state === "failed") {
      b.className = "banner failed"; b.hidden = false;
      b.textContent = "Resetting " + what + " did not finish.  Try again, and if it fails again run  hackrange-lab diag  on your Ubuntu machine and send the file for help.";
    } else {
      b.hidden = true;
    }
    $("reset-all").disabled = st.state === "running" || $("reset-all-confirm").value !== "RESET";
  }

  function act(comp, action) {
    api("api/components/" + comp.id + "/" + action, {}).then(function (r) {
      if (r._status === 401) return showLogin();
      refresh();
    });
  }

  // ---- the Labs tab -----------------------------------------------------
  var labsData = null;
  var openDays = {};

  function currentTab() { return location.hash === "#labs" ? "labs" : "control"; }

  function showTab() {
    // Signed out: only the sign-in card shows (the dashboard behind it would
    // be empty, and push the sign-in card off the bottom of the screen).
    if (!$("login").hidden) return;
    var tab = currentTab();
    document.querySelectorAll("[data-tab]").forEach(function (a) {
      a.classList.toggle("active", a.dataset.tab === tab);
    });
    $("app").hidden = tab !== "control";
    $("labs-view").hidden = tab !== "labs";
    if (tab === "labs") loadLabs();
  }

  function loadLabs() {
    return api("api/labs").then(function (d) {
      if (d._status === 401) return showLogin();
      labsData = d; renderLabs();
    });
  }

  function dayPill(day) {
    if (day.complete) return ["Complete", "pill lab-state pill-complete"];
    if (day.checked_at || day.self_confirmed) return ["In progress", "pill lab-state pill-progress"];
    return ["Not started", "pill lab-state pill-muted"];
  }

  function renderLabs() {
    var d = labsData, weeks = $("weeks");
    weeks.textContent = "";
    if (document.activeElement !== $("gh-user")) $("gh-user").value = d.github_user || "";
    var done = d.days.filter(function (x) { return x.complete; }).length;
    $("labs-done").textContent = String(done);
    $("labs-total").textContent = String(d.days.length);
    $("labs-bar").style.width = Math.round(100 * done / Math.max(d.days.length, 1)) + "%";
    var names = { 1: "Week 1: The developer workflow, and securing it", 2: "Week 2: Dependencies, containers, and the supply chain",
                  3: "Week 3: Infrastructure as code and Kubernetes", 4: "Week 4: Services, observability, compliance, and the capstone" };
    var lastWeek = 0;
    d.days.forEach(function (day) {
      if (day.week !== lastWeek) {
        lastWeek = day.week;
        var h = document.createElement("h2"); h.className = "week-head"; h.textContent = names[day.week] || ("Week " + day.week);
        weeks.appendChild(h);
      }
      var node = $("day-template").content.firstElementChild.cloneNode(true);
      node.querySelector(".lab-num").textContent = "Day " + day.day;
      node.querySelector(".lab-title").textContent = day.title;
      node.querySelector(".lab-score").textContent =
        (day.auto_passed + day.self_confirmed) + " of " + day.items.length;
      var p = dayPill(day), pill = node.querySelector(".lab-state");
      pill.textContent = p[0]; pill.className = p[1];
      var body = node.querySelector(".lab-body");
      body.hidden = !openDays[day.day];
      node.querySelector(".lab-head").addEventListener("click", function () {
        openDays[day.day] = body.hidden; body.hidden = !body.hidden;
      });
      var list = node.querySelector(".lab-items");
      day.items.forEach(function (it) {
        var li = document.createElement("li"); li.className = "lab-item";
        var text = document.createElement("div");
        var t = document.createElement("span"); t.textContent = it.text; text.appendChild(t);
        var how = document.createElement("span"); how.className = "how";
        if (it.kind === "auto") {
          var mark = document.createElement("span");
          mark.className = "lab-mark" + (it.state ? " " + it.state : "");
          mark.textContent = it.state === "pass" ? "✓" : it.state === "fail" ? "✗" : "?";
          li.appendChild(mark);
          how.textContent = it.github ? "Checked on your GitHub repository" : "Checked by the lab";
        } else {
          var box = document.createElement("input"); box.type = "checkbox";
          box.checked = it.state === "confirmed";
          box.title = "Tick when you have done this";
          box.addEventListener("change", function () {
            api("api/labs/" + day.day + "/items/" + it.id + "/confirm", { confirmed: box.checked }).then(function (r) {
              if (r._status === 401) return showLogin();
              if (r.days) { labsData = r; renderLabs(); }
            });
          });
          li.appendChild(box);
          how.textContent = "You tick this one: only you saw it";
        }
        text.appendChild(how);
        if (it.detail) {
          var det = document.createElement("span");
          det.className = "detail " + (it.state === "pass" ? "pass" : "fail");
          det.textContent = it.detail; text.appendChild(det);
        }
        li.appendChild(text); list.appendChild(li);
      });
      var btn = node.querySelector(".lab-check");
      btn.addEventListener("click", function () {
        btn.disabled = true; btn.textContent = "Checking...";
        openDays[day.day] = true;
        api("api/labs/" + day.day + "/check", {}).then(function (r) {
          if (r._status === 401) return showLogin();
          if (r.days) { labsData = r; renderLabs(); }
        });
      });
      node.querySelector(".lab-checked").textContent = day.checked_at
        ? "Last checked " + new Date(day.checked_at * 1000).toLocaleString() + (day.complete ? ".  Well done." : ".")
        : "Not checked yet.";
      weeks.appendChild(node);
    });
  }

  function refresh() {
    return api("api/state").then(function (s) {
      if (s._status === 401) return showLogin();
      state = s;
      $("login").hidden = true; $("tabs").hidden = false;
      if (currentTab() !== "control") { $("app").hidden = true; return; }
      $("app").hidden = false;
      $("signout").hidden = s.door === "lab";
      render();
    }).catch(function () {
      $("summary").textContent = "Cannot reach the lab"; $("summary").className = "pill pill-stopped";
    });
  }

  function showLogin() {
    $("app").hidden = true; $("labs-view").hidden = true; $("tabs").hidden = true;
    $("login").hidden = false; $("signout").hidden = true;
    $("summary").textContent = "Signed out"; $("summary").className = "pill pill-muted";
  }

  function wire() {
    document.querySelectorAll("[data-copy]").forEach(function (b) {
      b.addEventListener("click", function () {
        var el = $(b.dataset.copy);
        navigator.clipboard.writeText(el.dataset.value || el.textContent).then(function () {
          b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1200);
        });
      });
    });
    document.querySelectorAll("[data-reveal]").forEach(function (b) {
      b.addEventListener("click", function () {
        var el = $(b.dataset.reveal);
        if (el.dataset.shown) { delete el.dataset.shown; el.textContent = "••••••••"; el.classList.add("masked"); b.textContent = "Show"; }
        else { el.dataset.shown = "1"; el.textContent = el.dataset.value || ""; el.classList.remove("masked"); b.textContent = "Hide"; }
      });
    });
    $("login-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var f = e.target;
      api("api/login", { username: f.username.value, password: f.password.value }).then(function (r) {
        if (r.ok) { f.password.value = ""; $("login-error").hidden = true; refresh().then(showTab); }
        else { $("login-error").textContent = r.error || "That did not work."; $("login-error").hidden = false; }
      });
    });
    $("signout").addEventListener("click", function () { api("api/logout", {}).then(showLogin); });
    $("reset-all-confirm").addEventListener("input", function () {
      $("reset-all").disabled = this.value !== "RESET" || (state && state.reset && state.reset.state === "running");
    });
    $("reset-all").addEventListener("click", function () {
      if ($("reset-all-confirm").value !== "RESET") return;
      api("api/reset-all", { confirm: "RESET" }).then(function (r) {
        if (r._status === 401) return showLogin();
        $("reset-all-confirm").value = "";
        if (!r.ok) alert(r.message || "The reset did not start.");
        refresh();
      });
    });
  }

  wire();
  window.addEventListener("hashchange", showTab);
  $("gh-form").addEventListener("submit", function (e) {
    e.preventDefault();
    api("api/labs/github-user", { github_user: $("gh-user").value }).then(function (r) {
      if (r._status === 401) return showLogin();
      $("gh-msg").textContent = r.error ? r.error : "Saved.";
      if (r.days) { labsData = r; renderLabs(); }
    });
  });
  refresh().then(showTab);
  setInterval(function () { if (!$("app").hidden) refresh(); }, POLL_MS);
})();
