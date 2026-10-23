/* Valya Scan v3 — interface */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => (v === null || v === undefined ? "" : String(v)).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const eur = v => (v === null || v === undefined || v === "") ? "—" : Number(v).toLocaleString("fr-FR", {style: "currency", currency: "EUR", maximumFractionDigits: 2});
const dash = v => (v === null || v === undefined || v === "") ? "—" : esc(v);

const S = {udid: null, recovery: null, paired: false, scan: null, fiche: null, statuts: [], etats: [],
           job: null, jobSince: 0, jobTimer: null, settings: null, lastDevKey: ""};

const TESTS = ["Écran / affichage", "Tactile (tout l'écran)", "Face ID / Touch ID", "Caméra arrière", "Caméra avant",
  "Haut-parleur", "Écouteur interne", "Micro", "Boutons volume", "Bouton latéral", "Vibreur", "Wi-Fi / Bluetooth",
  "Réseau / appels", "Charge (câble)", "Charge sans fil", "True Tone", "Capteur de proximité", "Flash"];

async function api(url, opt = {}) {
  if (opt.body && !(opt.body instanceof FormData)) {
    opt.headers = {"Content-Type": "application/json"};
    opt.body = JSON.stringify(opt.body);
  }
  let r;
  try { r = await fetch(url, opt); } catch (e) { throw new Error("Valya Scan ne répond plus : la fenêtre Terminal a-t-elle été fermée ?"); }
  let d = {};
  try { d = await r.json(); } catch (e) {}
  if (!r.ok || d.ok === false) { const err = new Error(d.erreur || ("Erreur " + r.status)); err.data = d; throw err; }
  return d;
}
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "t " + kind; t.textContent = msg;
  $("#toast").appendChild(t);
  setTimeout(() => t.remove(), kind === "err" ? 8000 : 4000);
}
async function busy(btn, fn) {
  if (btn) btn.classList.add("loading");
  try { return await fn(); } catch (e) { toast(e.message, "err"); } finally { if (btn) btn.classList.remove("loading"); }
}
function confirmBox(title, html, okLabel = "Confirmer", danger = false) {
  return new Promise(res => {
    $("#mc-title").textContent = title; $("#mc-body").innerHTML = html;
    const ok = $("#mc-ok"); ok.textContent = okLabel; ok.className = "btn " + (danger ? "danger" : "primary");
    const m = $("#m-confirm"); m.classList.remove("hidden");
    const close = v => { m.classList.add("hidden"); ok.onclick = null; m.onclick = null; res(v); };
    ok.onclick = () => close(true);
    m.onclick = e => { if (e.target === m || e.target.hasAttribute("data-close")) close(false); };
  });
}

/* ------------------------------------------------------------ navigation */
function show(view) {
  $$(".nav").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach(v => v.classList.toggle("hidden", v.id !== "view-" + view));
  if (view === "stock") loadStock();
  if (view === "taches") loadJobs();
  if (view === "reglages") loadSettings();
}
$$(".nav").forEach(b => b.onclick = () => show(b.dataset.view));
document.addEventListener("click", e => {
  const m = e.target.closest(".modal");
  if (m && m.id === "m-phone" && (e.target === m || e.target.hasAttribute("data-close"))) m.classList.add("hidden");
});

/* ------------------------------------------------------------ état de l'appareil */
async function poll() {
  let d;
  try { d = await api("/api/status"); } catch (e) {
    $("#conn").className = "conn"; $("#conn-txt").textContent = "Serveur arrêté"; return;
  }
  $("#version").textContent = "v" + d.version;
  const busyN = d.taches_en_cours.length;
  $("#busy-count").textContent = busyN; $("#busy-count").classList.toggle("hidden", !busyN);
  renderTools(d.outils);
  const devs = d.appareils;
  S.udid = devs.normal[0] || null;
  S.recovery = devs.recovery;
  S.paired = S.udid ? !!(d.appairage[S.udid] || {}).ok : false;
  const key = [S.udid, S.paired, S.recovery && S.recovery.ECID].join("|");
  const conn = $("#conn");
  if (S.udid && S.paired) { conn.className = "conn on"; $("#conn-txt").textContent = "iPhone connecté"; }
  else if (S.udid) { conn.className = "conn warn"; $("#conn-txt").textContent = "En attente de confiance"; }
  else if (S.recovery) { conn.className = "conn warn"; $("#conn-txt").textContent = "Mode récupération"; }
  else { conn.className = "conn"; $("#conn-txt").textContent = devs.erreur ? "Outils manquants" : "Aucun iPhone"; }

  $("#dev-empty").classList.toggle("hidden", !!(S.udid || S.recovery));
  if (devs.erreur && !S.udid) $("#dev-empty p").textContent = devs.erreur;
  $("#dev-pair").classList.toggle("hidden", !(S.udid && !S.paired));
  if (S.udid && !S.paired) $("#pair-msg").textContent = (d.appairage[S.udid] || {}).message || "";
  $("#dev-recovery").classList.toggle("hidden", !S.recovery);
  if (S.recovery) $("#rec-msg").textContent = `${S.recovery.nom || "iPhone"} — mode ${S.recovery.MODE || "?"} — ECID ${S.recovery.ECID || "?"}. Tu peux le faire redémarrer normalement ou réinstaller iOS.`;
  $("#btn-scan").disabled = !(S.udid && S.paired);
  $("#tools-sub").textContent = S.udid && S.paired ? "Sur l'iPhone branché." : (S.recovery ? "iPhone en mode récupération : seules la sortie et la restauration sont possibles." : "Branche et déverrouille un iPhone pour utiliser ces outils.");
  $$("[data-act], #btn-backup, #btn-crash, #btn-syslog, #btn-apps, #btn-rename").forEach(b => b.disabled = !(S.udid && S.paired));
  $$("[data-restore]").forEach(b => b.disabled = !((S.udid && S.paired) || S.recovery));
  $$("#btn-exit-rec, #btn-exit-rec2").forEach(b => b.disabled = !S.recovery);

  if (key !== S.lastDevKey) {
    S.lastDevKey = key;
    if (!S.udid) { $("#diag").classList.add("hidden"); $("#dev-sub").textContent = "Branche un iPhone en USB et déverrouille-le."; }
    else if (S.paired && (!S.scan || S.scan.udid !== S.udid)) runScan();
  }
}
function renderTools(t) {
  $("#tools-list").innerHTML = Object.entries(t).map(([k, v]) =>
    `<div class="row between"><span>${esc(k)}</span><span class="${v.ok ? "pos" : "neg"}">${v.ok ? "✓" : "absent"}</span></div>`).join("");
}

$("#btn-refresh").onclick = () => { S.lastDevKey = ""; poll(); };
$("#btn-scan").onclick = e => runScan(e.currentTarget);
$("#btn-pair").onclick = e => busy(e.currentTarget, async () => {
  const d = await api("/api/pair/" + S.udid, {method: "POST"});
  toast(d.ok ? "Appairage OK" : d.message, d.ok ? "ok" : "err"); S.lastDevKey = ""; poll();
});

async function runScan(btn) {
  if (!S.udid) return;
  $("#dev-sub").textContent = "Diagnostic en cours… (10 à 20 secondes)";
  await busy(btn || $("#btn-scan"), async () => {
    const d = await api("/api/scan/" + S.udid, {method: "POST"});
    S.scan = d.diagnostic; S.fiche = d.fiche;
    renderDiag(); toast("Diagnostic enregistré : " + d.fiche.reference, "ok");
    if (d.synchro) toast(d.synchro);
  });
}

function ringColor(p) { return p >= 85 ? "var(--ok)" : p >= 80 ? "var(--warn)" : "var(--danger)"; }
function renderDiag() {
  const d = S.scan, f = S.fiche, b = d.batterie || {}, st = d.stockage || {};
  $("#dev-sub").textContent = `Diagnostic du ${d.scanne_le} — fiche ${f.reference}`;
  const tag = (txt, k) => `<span class="tag ${k || ""}">${esc(txt)}</span>`;
  const act = d.activation === "Activated" || d.activation === "FactoryActivated";
  const alerts = d.alertes.length ? d.alertes.map(a => `<div class="alert ${a.niveau}">${esc(a.texte)}</div>`).join("")
    : `<div class="alert ok">Aucun blocage détecté : activé, Localiser désactivé${b.sante ? ", batterie " + b.sante + " %" : ""}.</div>`;
  const kv = rows => `<dl class="kv">${rows.map(([k, v, copy]) => `<dt>${k}</dt><dd ${copy && v ? `class="copy" data-copy="${esc(v)}" title="Copier"` : ""}>${dash(v)}</dd>`).join("")}</dl>`;
  const pct = b.sante;
  $("#diag").innerHTML = `
    <div class="alerts">${alerts}</div>
    <div class="hero">
      <div class="card main">
        <span class="muted small">${esc(d.nom_appareil || "")}</span>
        <h2>${esc(d.modele)} ${st.capacite ? "· " + esc(st.capacite) : ""}</h2>
        <div class="muted">iOS ${dash(d.ios)} (${dash(d.build)}) · ${dash(d.couleur)}</div>
        <div class="tags">
          ${tag(act ? "Activé" : "Non activé : " + (d.activation || "?"), act ? "ok" : "danger")}
          ${d.localiser === null ? tag("Localiser : non déterminé", "warn") : tag(d.localiser ? "Localiser ACTIVÉ" : "Localiser désactivé", d.localiser ? "danger" : "ok")}
          ${tag(d.origine, d.origine_niveau)}
          ${tag("Code : " + (d.code_actif ? "oui" : "non"))}
          ${d.sim ? tag("SIM : " + d.sim.replace("kCTSIMSupportSIMStatus", "")) : ""}
        </div>
        <div class="row gap wrap" style="margin-top:16px">
          <button class="btn primary" id="open-fiche">Ouvrir la fiche ${esc(f.reference)}</button>
          <a class="btn" href="/rapport/${f.id}" target="_blank">Rapport de vente</a>
        </div>
      </div>
      <div class="card">
        <h3>Batterie</h3>
        <div class="gauge">
          <div class="ring" style="--p:${pct || 0};--c:${ringColor(pct || 0)}"><b>${pct != null ? pct + "%" : "?"}</b></div>
          ${kv([["Cycles", b.cycles], ["Capacité d'origine", b.capacite_origine ? b.capacite_origine + " mAh" : null],
               ["Capacité actuelle", b.capacite_max ? b.capacite_max + " mAh" : null], ["Température", b.temperature ? b.temperature + " °C" : null],
               ["Charge", b.niveau != null ? b.niveau + " %" + (b.en_charge ? " (en charge)" : "") : null]])}
        </div>
        ${b.erreur ? `<p class="small neg">${esc(b.erreur)}</p>` : ""}
        ${pct == null && !b.erreur ? `<p class="small muted">Santé non lisible sur cette version d'iOS : vérifie dans Réglages › Batterie.</p>` : ""}
      </div>
    </div>
    <div class="grid2">
      <div class="card"><h3>Identifiants</h3>${kv([["Numéro de série", d.serie, 1], ["IMEI", d.imei, 1], ["IMEI 2", d.imei2, 1],
        ["Référence modèle", d.numero_modele, 1], ["Région", d.region], ["Modèle interne", d.product_type + " · " + (d.hardware || "")],
        ["ECID", d.ecid, 1], ["Modem", d.modem], ["Wi-Fi", d.wifi], ["Bluetooth", d.bluetooth], ["ICCID (SIM)", d.iccid]])}</div>
      <div class="card"><h3>Stockage</h3>
        ${st.capacite ? `<div class="row between"><b>${esc(st.capacite)}</b><span class="muted">${st.utilise_pct}% utilisé</span></div><div class="bar"><i style="width:${st.utilise_pct}%"></i></div>` : `<p class="muted">${esc(st.erreur || "Non lisible")}</p>`}
        <h3 style="margin-top:18px">Pièces d'origine</h3>
        <p class="small muted">Apple ne communique pas l'historique des pièces par USB. Vérifie sur l'iPhone : <b>Réglages › Général › Informations › Historique des pièces et réparations</b> (iOS 15.2+). Un message « Pièce inconnue » = pièce non d'origine.</p>
        <h3 style="margin-top:18px">Blocage opérateur</h3>
        <p class="small muted">Non lisible par câble : teste avec une carte SIM d'un autre opérateur, ou vérifie dans <b>Réglages › Général › Informations › Verrouillage opérateur</b> (« Aucune restriction SIM »).</p>
      </div>
    </div>
    <div class="card" style="margin-top:14px"><div class="row between"><h3>Tests manuels</h3><span class="muted small">Coche ce qui fonctionne : c'est enregistré dans la fiche et affiché sur le rapport.</span></div>
      <div class="checklist" id="checklist">${TESTS.map(t => `<label><input type="checkbox" data-test="${esc(t)}" ${(f.tests || {})[t] ? "checked" : ""}>${esc(t)}</label>`).join("")}</div></div>`;
  $("#diag").classList.remove("hidden");
  $("#open-fiche").onclick = () => openPhone(f.id);
  $$("#checklist input").forEach(i => i.onchange = saveTests);
}
async function saveTests() {
  const tests = {};
  $$("#checklist input").forEach(i => { if (i.checked) tests[i.dataset.test] = true; });
  try { const d = await api("/api/phones/" + S.fiche.id, {method: "PUT", body: {tests}}); S.fiche = d.fiche; }
  catch (e) { toast(e.message, "err"); }
}
document.addEventListener("click", e => {
  const c = e.target.closest("[data-copy]");
  if (c) { navigator.clipboard.writeText(c.dataset.copy).then(() => toast("Copié : " + c.dataset.copy)); }
});

/* ------------------------------------------------------------ outils */
$$("[data-act]").forEach(b => b.onclick = async e => {
  const a = b.dataset.act, labels = {redemarrer: "Redémarrer l'iPhone ?", eteindre: "Éteindre l'iPhone ?", recuperation: "Mettre l'iPhone en mode récupération ?"};
  if (!await confirmBox(labels[a], "<p class='muted'>La commande est envoyée immédiatement.</p>")) return;
  busy(e.currentTarget, async () => { const d = await api(`/api/action/${S.udid}/${a}`, {method: "POST"}); toast(d.message, "ok"); S.lastDevKey = ""; });
});
$("#btn-rename").onclick = e => busy(e.currentTarget, async () => {
  const d = await api(`/api/action/${S.udid}/renommer`, {method: "POST", body: {nom: $("#rename-in").value}}); toast(d.message, "ok");
});
$$("#btn-exit-rec, #btn-exit-rec2").forEach(b => b.onclick = e => busy(e.currentTarget, async () => {
  const d = await api("/api/recovery/exit", {method: "POST"}); toast(d.message, "ok");
}));
$$("[data-restore]").forEach(b => b.onclick = async () => {
  const mode = b.dataset.restore, ipsw = $("#ipsw-in").value.trim();
  let html, conf = null;
  if (mode === "effacer") {
    html = `<div class="alert danger">TOUTES les données de l'iPhone seront effacées. Si Localiser est activé, l'iPhone restera bloqué sur le compte iCloud du propriétaire après la restauration.</div>
      <p>Tape <b>EFFACER</b> pour confirmer :</p><input id="conf-erase" autocomplete="off">`;
  } else {
    html = `<p>iOS va être mis à jour vers la dernière version signée par Apple${ipsw ? " (fichier " + esc(ipsw) + ")" : ""}. Les données sont conservées, mais fais une sauvegarde avant par sécurité.</p>
      <p class="muted small">Le téléchargement peut faire plusieurs Go. Ne débranche pas l'iPhone avant la fin.</p>`;
  }
  if (!await confirmBox(mode === "effacer" ? "Restauration complète" : "Mise à jour iOS", html, "Lancer", mode === "effacer")) return;
  if (mode === "effacer") conf = ($("#conf-erase") || {}).value;
  const body = {mode, ipsw, confirmation: conf};
  if (S.udid && S.paired) body.udid = S.udid; else if (S.recovery) body.ecid = S.recovery.ECID;
  try { const d = await api("/api/jobs/restore", {method: "POST", body}); openJob(d.tache.id); } catch (e) { toast(e.message, "err"); }
});
$("#btn-backup").onclick = e => busy(e.currentTarget, async () => { const d = await api("/api/jobs/backup/" + S.udid, {method: "POST"}); openJob(d.tache.id); });
$("#btn-crash").onclick = e => busy(e.currentTarget, async () => { const d = await api("/api/jobs/crash/" + S.udid, {method: "POST"}); openJob(d.tache.id); });
$("#btn-syslog").onclick = e => busy(e.currentTarget, async () => { const d = await api("/api/jobs/syslog/" + S.udid, {method: "POST"}); openJob(d.tache.id); });
$("#btn-apps").onclick = e => busy(e.currentTarget, async () => {
  const d = await api("/api/apps/" + S.udid), box = $("#apps-out");
  box.classList.remove("hidden");
  box.innerHTML = `<h3>${d.apps.length} app(s) installée(s) par l'utilisateur</h3>` + (d.apps.length ?
    `<table class="recap"><tr><th>Nom</th><th>Identifiant</th><th>Version</th></tr>${d.apps.map(a => `<tr><td>${esc(a.nom)}</td><td class="muted">${esc(a.id)}</td><td>${esc(a.version)}</td></tr>`).join("")}</table>` : "<p class='muted'>Aucune : l'iPhone est propre.</p>");
});

/* ------------------------------------------------------------ tâches */
async function loadJobs() {
  try {
    const d = await api("/api/jobs");
    $("#jobs-list").innerHTML = d.taches.length ? d.taches.map(j => `<div class="job ${S.job === j.id ? "active" : ""}" data-job="${j.id}">
      <b>${esc(j.label)}</b><br><small>${new Date(j.started * 1000).toLocaleTimeString("fr-FR")} · ${esc(j.status)}</small></div>`).join("")
      : "<p class='muted'>Aucune tâche pour l'instant.</p>";
    $$("[data-job]").forEach(x => x.onclick = () => openJob(+x.dataset.job));
  } catch (e) {}
}
function openJob(id) {
  show("taches");
  S.job = id; S.jobSince = 0; $("#console").textContent = ""; $("#job-result").innerHTML = "";
  clearTimeout(S.jobTimer); tickJob(); loadJobs();
}
async function tickJob() {
  if (!S.job) return;
  let d;
  try { d = (await api(`/api/jobs/${S.job}?since=${S.jobSince}`)).tache; } catch (e) { return; }
  const c = $("#console"), atBottom = c.scrollTop + c.clientHeight >= c.scrollHeight - 30;
  if (d.lines.length) { c.textContent += d.lines.join("\n") + "\n"; if (c.textContent.length > 400000) c.textContent = c.textContent.slice(-300000); }
  if (atBottom) c.scrollTop = c.scrollHeight;
  S.jobSince = d.next;
  $("#job-title").textContent = `${d.label} — ${d.status}`;
  $("#btn-stop").classList.toggle("hidden", d.status !== "en cours");
  if (d.result) renderJobResult(d);
  if (d.status === "en cours") S.jobTimer = setTimeout(tickJob, 800); else loadJobs();
}
function renderJobResult(d) {
  const r = d.result;
  if (d.kind === "crash") {
    $("#job-result").innerHTML = `<div class="alert ${r.nb_panics ? "warn" : "ok"}">${r.nb_panics} panic(s) trouvé(s), ${r.nb_autres} autre(s) rapport(s).
      ${r.pistes.length ? "<br>Pistes : <b>" + r.pistes.map(esc).join(", ") + "</b>" : ""}</div>
      ${r.panics.slice(0, 8).map(p => `<div class="small"><b>${esc(p.fichier)}</b><br><span class="muted">${esc(p.raison || "(raison non lisible)")}</span></div>`).join("")}
      <p class="small muted">Dossier : ${esc(r.dossier)}</p>`;
  } else if (r.dossier) {
    $("#job-result").innerHTML = `<p class="small muted">Dossier : ${esc(r.dossier)}</p>`;
  }
}
$("#btn-stop").onclick = e => busy(e.currentTarget, async () => { await api(`/api/jobs/${S.job}/stop`, {method: "POST"}); });

/* ------------------------------------------------------------ stock */
let stockTimer;
$("#q").oninput = () => { clearTimeout(stockTimer); stockTimer = setTimeout(loadStock, 250); };
$("#f-statut").onchange = loadStock;
async function loadStock() {
  const d = await api(`/api/phones?q=${encodeURIComponent($("#q").value)}&statut=${encodeURIComponent($("#f-statut").value)}`).catch(e => toast(e.message, "err"));
  if (!d) return;
  S.statuts = d.statuts; S.etats = d.etats;
  const sel = $("#f-statut");
  if (sel.options.length <= 1) d.statuts.forEach(s => sel.add(new Option(s, s)));
  const k = d.stats;
  $("#kpis").innerHTML = [["En stock", k.en_stock], ["Vendus", k.vendus], ["Argent investi", eur(k.investi)],
    ["Bénéfice réalisé", eur(k.benefice)], ["Bénéfice potentiel", eur(k.benefice_potentiel)]]
    .map(([a, b]) => `<div class="kpi"><small>${a}</small><b>${b}</b></div>`).join("");
  $("#tbl tbody").innerHTML = d.telephones.length ? d.telephones.map(p => `<tr data-id="${p.id}">
    <td><b>${esc(p.reference)}</b></td><td>${esc(p.modele)}</td><td>${dash(p.stockage)}</td>
    <td>${p.sante_batterie != null ? p.sante_batterie + " %" : "—"}</td><td>${dash(p.etat)}</td>
    <td>${eur(p.prix_achat)}</td><td>${eur(p.prix_vente)}</td>
    <td class="${p.marge > 0 ? "pos" : p.marge < 0 ? "neg" : ""}">${eur(p.marge)}</td>
    <td><span class="st ${esc(p.statut)}">${esc(p.statut)}</span></td>
    <td>${p.localiser ? '<span class="tag danger">iCloud</span>' : ""}${p.sheets_ligne ? '<span class="tag ok">Sheets</span>' : ""}</td></tr>`).join("")
    : `<tr><td colspan="10" class="muted" style="text-align:center;padding:30px">Aucun téléphone. Lance un diagnostic pour créer la première fiche.</td></tr>`;
  $$("#tbl tbody tr[data-id]").forEach(tr => tr.onclick = () => openPhone(+tr.dataset.id));
}

async function openPhone(id, tab = "infos") {
  const d = await api("/api/phones/" + id).catch(e => toast(e.message, "err"));
  if (!d) return;
  S.statuts = d.statuts; S.etats = d.etats;
  const p = d.fiche;
  $("#mp-title").textContent = `${p.reference} · ${p.modele || ""} ${p.stockage || ""}`;
  const opt = (list, v) => `<option value=""></option>` + list.map(x => `<option ${x === v ? "selected" : ""}>${esc(x)}</option>`).join("");
  const diag = p.dernier_diagnostic || {};
  $("#mp-body").innerHTML = `
    <div class="tabs">${[["infos", "Infos & prix"], ["rep", `Réparations (${p.reparations.length})`], ["diag", "Dernier diagnostic"], ["hist", `Historique (${p.scans.length})`]]
      .map(([k, l]) => `<button class="tab ${k === tab ? "active" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>
    <div data-pane="infos" class="${tab === "infos" ? "" : "hidden"}">
      <div class="grid2">
        <div>
          <div class="row gap"><label class="grow">Modèle<input name="modele" value="${esc(p.modele)}"></label><label class="grow">Stockage<input name="stockage" value="${esc(p.stockage)}"></label></div>
          <div class="row gap"><label class="grow">Couleur<input name="couleur" value="${esc(p.couleur)}"></label><label class="grow">Batterie (%)<input name="sante_batterie" value="${esc(p.sante_batterie)}"></label></div>
          <div class="row gap"><label class="grow">État<select name="etat">${opt(S.etats, p.etat)}</select></label><label class="grow">Statut<select name="statut">${opt(S.statuts, p.statut)}</select></label></div>
          <label>IMEI<input name="imei" value="${esc(p.imei)}"></label>
          <label>Notes<textarea name="notes" rows="3">${esc(p.notes)}</textarea></label>
        </div>
        <div>
          <div class="row gap"><label class="grow">Prix d'achat (€)<input name="prix_achat" value="${esc(p.prix_achat)}"></label><label class="grow">Frais (€)<input name="frais" value="${esc(p.frais)}"></label></div>
          <div class="row gap"><label class="grow">Prix de vente (€)<input name="prix_vente" value="${esc(p.prix_vente)}"></label><label class="grow">Date d'achat<input type="date" name="date_achat" value="${esc(p.date_achat)}"></label></div>
          <label>Date de vente<input type="date" name="date_vente" value="${esc(p.date_vente)}"></label>
          <div class="card" style="padding:12px">
            <div class="row between"><span class="muted">Pièces / réparations</span><b>${eur(p.cout_reparations)}</b></div>
            <div class="row between"><span class="muted">Marge</span><b class="${p.marge > 0 ? "pos" : p.marge < 0 ? "neg" : ""}">${eur(p.marge)}</b></div>
            <p class="small muted" style="margin:6px 0 0">Marge = vente − achat − frais − pièces.</p>
          </div>
          <p class="small muted">Série : ${dash(p.serie)} · Activation : ${dash(p.activation)} · Localiser : ${p.localiser == null ? "?" : p.localiser ? "ACTIVÉ" : "désactivé"}${p.sheets_ligne ? " · Google Sheets ligne " + p.sheets_ligne : ""}</p>
        </div>
      </div>
      <div class="row gap wrap between" style="margin-top:6px">
        <button class="btn danger" id="mp-del">Supprimer</button>
        <div class="row gap wrap">
          <a class="btn" href="/rapport/${p.id}" target="_blank">Rapport de vente</a>
          <button class="btn" id="mp-sheets">Envoyer au Google Sheets</button>
          <button class="btn primary" id="mp-save">Enregistrer</button>
        </div>
      </div>
    </div>
    <div data-pane="rep" class="${tab === "rep" ? "" : "hidden"}">
      <div class="row gap"><input id="rp-piece" placeholder="Pièce / intervention (ex. Écran OLED)"><input id="rp-cout" placeholder="Coût €" style="max-width:110px"><input id="rp-note" placeholder="Note (fournisseur…)"><button class="btn primary" id="rp-add">Ajouter</button></div>
      <table class="recap"><tr><th>Date</th><th>Pièce</th><th>Coût</th><th>Note</th><th></th></tr>
      ${p.reparations.map(r => `<tr><td>${esc(r.date)}</td><td>${esc(r.piece)}</td><td>${eur(r.cout)}</td><td class="muted">${esc(r.note)}</td><td><button class="btn small ghost" data-rdel="${r.id}">×</button></td></tr>`).join("") || `<tr><td colspan="5" class="muted">Aucune réparation.</td></tr>`}</table>
    </div>
    <div data-pane="diag" class="${tab === "diag" ? "" : "hidden"}">${diagSummary(diag)}</div>
    <div data-pane="hist" class="${tab === "hist" ? "" : "hidden"}">
      <table class="recap"><tr><th>Date du scan</th><th></th></tr>${p.scans.map(s => `<tr><td>${esc(s.date)}</td><td><button class="btn small" data-scan="${s.id}">Voir</button></td></tr>`).join("")}</table>
      <div id="scan-view"></div>
    </div>`;
  $("#m-phone").classList.remove("hidden");
  $$("[data-tab]").forEach(b => b.onclick = () => {
    $$("[data-tab]").forEach(x => x.classList.toggle("active", x === b));
    $$("[data-pane]").forEach(x => x.classList.toggle("hidden", x.dataset.pane !== b.dataset.tab));
  });
  $("#mp-save").onclick = e => busy(e.currentTarget, async () => {
    const body = {};
    $$("[data-pane=infos] [name]").forEach(i => body[i.name] = i.value);
    await api("/api/phones/" + id, {method: "PUT", body}); toast("Fiche enregistrée", "ok");
    openPhone(id); loadStock();
  });
  $("#mp-del").onclick = async () => {
    if (!await confirmBox("Supprimer la fiche ?", `<p>${esc(p.reference)} et tout son historique seront supprimés de Valya Scan (le Google Sheets n'est pas modifié).</p>`, "Supprimer", true)) return;
    await api("/api/phones/" + id, {method: "DELETE"}); $("#m-phone").classList.add("hidden"); loadStock(); toast("Fiche supprimée");
  };
  $("#mp-sheets").onclick = e => sendToSheets(id, e.currentTarget);
  $("#rp-add").onclick = e => busy(e.currentTarget, async () => {
    await api(`/api/phones/${id}/repairs`, {method: "POST", body: {piece: $("#rp-piece").value, cout: $("#rp-cout").value, note: $("#rp-note").value}});
    openPhone(id, "rep"); loadStock();
  });
  $$("[data-rdel]").forEach(b => b.onclick = async () => { await api(`/api/phones/${id}/repairs/${b.dataset.rdel}`, {method: "DELETE"}); openPhone(id, "rep"); });
  $$("[data-scan]").forEach(b => b.onclick = async () => { const d = await api("/api/scans/" + b.dataset.scan); $("#scan-view").innerHTML = diagSummary(d.diagnostic); });
}
function diagSummary(d) {
  if (!d || !d.modele) return "<p class='muted'>Pas de diagnostic.</p>";
  const b = d.batterie || {}, st = d.stockage || {};
  const rows = [["Date", d.scanne_le], ["Modèle", d.modele + " (" + d.product_type + ")"], ["iOS", d.ios], ["Série", d.serie], ["IMEI", d.imei],
    ["Référence", d.numero_modele], ["Origine", d.origine], ["Région", d.region], ["Activation", d.activation],
    ["Localiser", d.localiser == null ? "non déterminé" : d.localiser ? "ACTIVÉ" : "désactivé"], ["Batterie", b.sante != null ? b.sante + " % · " + (b.cycles ?? "?") + " cycles" : "—"],
    ["Stockage", st.capacite ? st.capacite + " (" + st.utilise_pct + " % utilisé)" : "—"]];
  return `${(d.alertes || []).map(a => `<div class="alert ${a.niveau}" style="margin-bottom:6px">${esc(a.texte)}</div>`).join("")}
    <dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${dash(v)}</dd>`).join("")}</dl>`;
}

async function sendToSheets(id, btn) {
  await busy(btn, async () => {
    // on enregistre d'abord les modifications en cours
    const body = {}; $$("[data-pane=infos] [name]").forEach(i => body[i.name] = i.value);
    await api("/api/phones/" + id, {method: "PUT", body});
    const plan = (await api(`/api/phones/${id}/sheets/prepare`, {method: "POST"})).plan;
    const table = `<table class="recap"><tr><th>Colonne</th><th>Actuellement</th><th>Après</th></tr>${plan.recap.map(r =>
      `<tr><td>${esc(r.colonne)}</td><td class="muted">${dash(r.avant)}</td><td><b>${dash(r.apres)}</b></td></tr>`).join("")}</table>`;
    if (plan.problemes.length) {
      await confirmBox("Envoi impossible", `${plan.problemes.map(p => `<div class="alert danger" style="margin-bottom:6px">${esc(p)}</div>`).join("")}${table}<p class="small muted">Rien n'a été écrit.</p>`, "OK");
      return;
    }
    const go = await confirmBox(`${plan.mode === "ajout" ? "Ajouter" : "Mettre à jour"} la ligne ${plan.ligne} ?`,
      `<p class="small muted">Onglet « stock ». La colonne J (Marge) n'est pas touchée.</p>${table}`, "Valider et écrire");
    if (!go) { toast("Envoi annulé : rien n'a été écrit."); return; }
    const res = (await api(`/api/phones/${id}/sheets/write`, {method: "POST", body: {valide: true, ligne: plan.ligne, mode: plan.mode}})).resultat;
    if (res.tout_ok) toast(`Ligne ${res.ligne} écrite et vérifiée ✓`, "ok");
    else await confirmBox("Vérification : écarts détectés", `<table class="recap"><tr><th>Colonne</th><th>Attendu</th><th>Relu</th></tr>${res.verification.map(v =>
      `<tr><td>${esc(v.colonne)}</td><td>${esc(v.attendu)}</td><td class="${v.ok ? "pos" : "neg"}">${esc(v.lu)}</td></tr>`).join("")}</table><p class="small">Vérifie la ligne ${res.ligne} dans le Google Sheets.</p>`, "OK");
    openPhone(id); loadStock();
  });
}

/* ------------------------------------------------------------ réglages */
async function loadSettings() {
  const d = await api("/api/settings").catch(e => toast(e.message, "err"));
  if (!d) return;
  S.settings = d.reglages;
  $("#data-dir").textContent = "Données enregistrées dans : " + d.dossier_donnees;
  $$("[data-set]").forEach(i => { const v = d.reglages[i.dataset.set]; if (i.type === "checkbox") i.checked = !!v; else i.value = v ?? ""; });
  $("#key-state").textContent = d.reglages.service_account_path ? "✓ Clé enregistrée." : "Aucune clé pour l'instant.";
  if (!d.google_dispo) $("#key-state").textContent += " ⚠️ Module Google manquant : relance Valya Scan.";
}
async function saveSettings(btn) {
  const body = {};
  $$("[data-set]").forEach(i => body[i.dataset.set] = i.type === "checkbox" ? i.checked : i.value.trim());
  await busy(btn, async () => { await api("/api/settings", {method: "POST", body}); toast("Réglages enregistrés", "ok"); loadSettings(); });
}
$("#btn-save-set").onclick = e => saveSettings(e.currentTarget);
$("#btn-save-set2").onclick = e => saveSettings(e.currentTarget);
$("#key-file").onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  const fd = new FormData(); fd.append("cle", f);
  try { const d = await api("/api/settings/key", {method: "POST", body: fd}); toast("Clé enregistrée. Partage le Google Sheets avec : " + d.email, "ok"); $("#key-state").textContent = "✓ Clé enregistrée (" + d.email + ")"; }
  catch (err) { toast(err.message, "err"); }
  e.target.value = "";
};
$("#btn-test-sheets").onclick = e => busy(e.currentTarget, async () => {
  const r = (await api("/api/settings/test", {method: "POST"})).resultat;
  $("#test-out").innerHTML = `✓ Connecté à « ${esc(r.titre)} ». Onglet stock : ${r.stock_ok ? "trouvé" : "<span class='neg'>introuvable</span>"} · onglet scans : ${r.scans_ok ? "trouvé" : "absent (le journal des scans est désactivé)"}`;
});

poll();
setInterval(poll, 3000);
