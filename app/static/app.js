/* Valya Scan — interface */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => (v === null || v === undefined ? "" : String(v)).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const eur = v => (v === null || v === undefined || v === "") ? "—" : Number(v).toLocaleString("fr-FR", {style: "currency", currency: "EUR", maximumFractionDigits: 2});
const dash = v => (v === null || v === undefined || v === "") ? "—" : esc(v);
const frDate = d => d ? String(d).slice(0, 10).split("-").reverse().join("/") + (String(d).length > 10 ? " " + String(d).slice(11, 16) : "") : "—";

const S = {udid: null, recovery: null, paired: false, scan: null, fiche: null, ticketsActifs: [], piecesCompat: [],
           meta: {statuts: [], etats: [], ticket_statuts: [], qualites: [], categories: []},
           job: null, jobSince: 0, jobTimer: null, settings: {}, lastDevKey: "", scanning: false, live: null};

const TESTS = [
  ["Écran / affichage", "Affiche une image toute blanche puis toute noire : pas de taches, pixels morts, lignes ni marquage."],
  ["Tactile (tout l'écran)", "Maintiens une icône et fais-la glisser dans les 4 coins et sur les bords : elle doit suivre le doigt sans sauter."],
  ["Face ID / Touch ID", "Réglages › Face ID et code : configure un visage (ou une empreinte) et déverrouille avec."],
  ["True Tone", "Centre de contrôle › appui long sur la luminosité : le bouton True Tone doit être présent (absent = écran non appairé)."],
  ["Caméra arrière", "Appareil photo : teste chaque objectif (0,5× / 1× / 2–5×), la mise au point et la vidéo."],
  ["Caméra avant", "Prends un selfie et une vidéo selfie : image nette, pas de tache."],
  ["Flash", "Centre de contrôle › lampe torche."],
  ["Haut-parleur", "Mets une musique à fond : son clair, pas de grésillement."],
  ["Écouteur interne", "Appelle la messagerie et écoute à l'oreille."],
  ["Micro", "Dictaphone : enregistre et réécoute. Puis une vidéo selfie pour le micro du haut."],
  ["Capteur de proximité", "Pendant un appel, couvre le haut de l'écran : il doit s'éteindre."],
  ["Boutons volume", "Appuie sur + et − : la jauge de volume bouge."],
  ["Bouton latéral", "Verrouille puis réveille l'écran."],
  ["Bouton silencieux / Action", "Bascule ou appuie : le mode silencieux change."],
  ["Vibreur", "Passe en mode silencieux : ça doit vibrer."],
  ["Wi-Fi / Bluetooth", "Connecte-toi à un Wi-Fi et active le Bluetooth."],
  ["Réseau / appels", "Insère une SIM : réseau présent et appel sortant OK."],
  ["Charge (câble)", "Branché à l'ordinateur : l'éclair s'affiche sur la batterie (la jauge en direct le montre aussi)."],
  ["Charge sans fil", "Pose-le sur un chargeur MagSafe / Qi."],
  ["Boussole / gyroscope", "App Boussole, puis fais pivoter l'écran : tout réagit."],
];

/* ------------------------------------------------------------ utilitaires */
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
function openBig(title, html) {
  $("#mb-title").textContent = title; $("#mb-body").innerHTML = html;
  $("#m-big").classList.remove("hidden");
  return $("#mb-body");
}
const closeBig = () => $("#m-big").classList.add("hidden");
document.addEventListener("click", e => {
  for (const id of ["m-big", "m-tests"]) {
    const m = $("#" + id);
    if (!m.classList.contains("hidden") && (e.target === m || (m.contains(e.target) && e.target.hasAttribute("data-close")))) m.classList.add("hidden");
  }
  const c = e.target.closest("[data-copy]");
  if (c) navigator.clipboard.writeText(c.dataset.copy).then(() => toast("Copié : " + c.dataset.copy));
});
document.addEventListener("keydown", e => { if (e.key === "Escape") { closeBig(); $("#m-tests").classList.add("hidden"); } });
const opts = (list, v, empty = true) => (empty ? `<option value=""></option>` : "") + list.map(x => `<option ${x === v ? "selected" : ""}>${esc(x)}</option>`).join("");
const formData = root => { const o = {}; $$("[name]", root).forEach(i => o[i.name] = i.type === "checkbox" ? i.checked : i.value); return o; };
function beep() {
  if (S.settings.son_connexion === false) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)(), o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(ctx.destination); g.gain.setValueAtTime(.08, ctx.currentTime);
    o.start(); o.frequency.setValueAtTime(1320, ctx.currentTime + .09); g.gain.exponentialRampToValueAtTime(.0001, ctx.currentTime + .25); o.stop(ctx.currentTime + .26);
  } catch (e) {}
}
const timeline = list => list && list.length ? `<div class="timeline">${list.map(ev => `<div class="ev ev-${esc(ev.type)}"><span>${frDate(ev.date)}</span><p>${esc(ev.texte)}</p></div>`).join("")}</div>` : "<p class='muted'>Rien pour l'instant.</p>";

/* ------------------------------------------------------------ navigation */
function show(view) {
  $$(".nav").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach(v => v.classList.toggle("hidden", v.id !== "view-" + view));
  if (view === "stock") loadStock();
  if (view === "taches") loadJobs();
  if (view === "reglages") loadSettings();
  if (view === "reparations") loadTickets();
  if (view === "pieces") loadParts();
}
$$(".nav").forEach(b => b.onclick = () => show(b.dataset.view));

/* ------------------------------------------------------------ état de l'appareil */
async function poll() {
  let d;
  try { d = await api("/api/status"); } catch (e) {
    $("#conn").className = "conn"; $("#conn-txt").textContent = "App arrêtée"; $("#conn-live").textContent = "Relance Valya Scan"; return;
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
  if (S.udid && S.paired) { conn.className = "conn on"; $("#conn-txt").textContent = S.scan ? S.scan.modele : "iPhone connecté"; }
  else if (S.udid) { conn.className = "conn warn"; $("#conn-txt").textContent = "En attente de confiance"; }
  else if (S.recovery) { conn.className = "conn warn"; $("#conn-txt").textContent = "Mode récupération"; }
  else { conn.className = "conn"; $("#conn-txt").textContent = devs.erreur ? "Outils manquants" : "Aucun iPhone"; $("#conn-live").textContent = ""; }

  const showDiag = S.udid && S.paired && S.scan && S.scan.udid === S.udid;
  $("#dev-empty").classList.toggle("hidden", !!(S.udid || S.recovery));
  if (devs.erreur && !S.udid) $("#dev-empty .muted").textContent = devs.erreur;
  $("#dev-pair").classList.toggle("hidden", !(S.udid && !S.paired));
  if (S.udid && !S.paired) $("#pair-msg").textContent = (d.appairage[S.udid] || {}).message || "";
  $("#dev-recovery").classList.toggle("hidden", !S.recovery);
  if (S.recovery) $("#rec-msg").textContent = `${S.recovery.nom || "iPhone"} — mode ${S.recovery.MODE || "?"}. Tu peux le faire redémarrer normalement ou réinstaller iOS.`;
  $("#diag").classList.toggle("hidden", !showDiag);
  $("#tools-sub").textContent = S.udid && S.paired ? "Sur l'iPhone branché : " + (S.scan ? S.scan.modele : "") : (S.recovery ? "iPhone en mode récupération : seules la sortie et la restauration sont possibles." : "Branche et déverrouille un iPhone pour utiliser ces outils.");
  $$("[data-act], #btn-backup, #btn-crash, #btn-syslog, #btn-apps, #btn-rename").forEach(b => b.disabled = !(S.udid && S.paired));
  $$("[data-restore]").forEach(b => b.disabled = !((S.udid && S.paired) || S.recovery));
  $$("#btn-exit-rec, #btn-exit-rec2").forEach(b => b.disabled = !S.recovery);
  $("#btn-refresh").disabled = !(S.udid && S.paired);

  if (key !== S.lastDevKey) {
    const wasEmpty = !S.lastDevKey.split("|")[0];
    S.lastDevKey = key;
    if (!S.udid) { $("#dev-sub").textContent = "Branche un iPhone en USB et déverrouille-le."; }
    else if (S.paired && (!S.scan || S.scan.udid !== S.udid)) { if (wasEmpty) beep(); runScan(); }
  }
  if (showDiag) refreshLive();
}
async function refreshLive() {
  try {
    const l = await api("/api/live/" + S.udid);
    S.live = l;
    const txt = l.niveau != null ? `Batterie ${l.niveau} %${l.en_charge ? " · en charge ⚡" : ""}` : "";
    $("#conn-live").textContent = txt;
    const el = $("#live-charge"); if (el) el.textContent = txt || "—";
  } catch (e) {}
}
function renderTools(t) {
  $("#tools-list").innerHTML = Object.entries(t).map(([k, v]) =>
    `<div class="row between"><span>${esc(k)}</span><span class="${v.ok ? "pos" : "neg"}">${v.ok ? "✓" : "absent"}</span></div>`).join("");
}

$("#btn-refresh").onclick = e => runScan(e.currentTarget);
$("#btn-pair").onclick = e => busy(e.currentTarget, async () => {
  const d = await api("/api/pair/" + S.udid, {method: "POST"});
  toast(d.ok ? "Appairage OK" : d.message, d.ok ? "ok" : "err"); S.lastDevKey = ""; poll();
});

async function runScan(btn) {
  if (!S.udid || S.scanning) return;
  S.scanning = true;
  $("#dev-loading").classList.remove("hidden"); $("#dev-sub").textContent = "Diagnostic en cours…";
  try {
    await busy(btn, async () => {
      const d = await api("/api/scan/" + S.udid, {method: "POST"});
      S.scan = d.diagnostic; S.fiche = d.fiche; S.ticketsActifs = d.tickets_actifs || []; S.piecesCompat = d.pieces_compatibles || [];
      renderDiag();
      $("#diag").classList.remove("hidden");
      if (d.synchro) toast(d.synchro);
    });
  } finally { S.scanning = false; $("#dev-loading").classList.add("hidden"); }
}

/* ------------------------------------------------------------ page « iPhone branché » */
function ringColor(p) { return p >= 85 ? "var(--ok)" : p >= 80 ? "var(--warn)" : "var(--danger)"; }
const kv = rows => `<dl class="kv">${rows.map(([k, v, copy]) => `<dt>${k}</dt><dd ${copy && v ? `class="copy" data-copy="${esc(v)}" title="Cliquer pour copier"` : ""}>${dash(v)}</dd>`).join("")}</dl>`;

function workflowState(f) {
  const labels = (f.scans || []).map(s => s.etiquette);
  return {avant: (f.scans || []).find(s => s.etiquette === "Avant réparation"), apres: (f.scans || []).find(s => s.etiquette === "Après réparation"), labels};
}

function renderDiag() {
  const d = S.scan, f = S.fiche, b = d.batterie || {}, st = d.stockage || {}, v = d.verdict || {niveau: "warn", titre: "?"};
  $("#dev-sub").textContent = `${d.modele}${st.capacite ? " · " + st.capacite : ""} — fiche ${f.reference} — lu à ${d.scanne_le.slice(11, 16)}`;
  const tests = f.tests || {}, nOk = Object.values(tests).filter(x => x === "ok").length, nKo = Object.values(tests).filter(x => x === "ko").length;
  const wf = workflowState(f);
  const tag = (txt, k) => `<span class="tag ${k || ""}">${esc(txt)}</span>`;
  const act = d.activation === "Activated" || d.activation === "FactoryActivated";
  const pct = b.sante;
  const alerts = (d.alertes || []).map(a => `<div class="alert ${a.niveau}">${esc(a.texte)}</div>`).join("");
  const ticketBanner = S.ticketsActifs.map(t => `<div class="alert info row between"><span>🔧 Réparation client en cours : <b>${esc(t.numero)}</b> — ${esc(t.probleme)} (${esc(t.statut)})</span><button class="btn small" data-open-ticket="${t.id}">Ouvrir</button></div>`).join("");

  $("#diag").innerHTML = `
    <div class="verdict v-${v.niveau}">
      <div class="v-icon">${v.niveau === "ok" ? "✓" : v.niveau === "danger" ? "✕" : "!"}</div>
      <div class="v-txt"><small>${esc(f.reference)} · ${esc(d.nom_appareil || "")}</small><h2>${esc(v.titre)} — ${esc(d.modele)} ${st.capacite ? esc(st.capacite) : ""}</h2><p>${esc(v.texte)}</p></div>
      <div class="v-tags">
        ${tag(act ? "Activé" : "Non activé", act ? "ok" : "danger")}
        ${d.localiser === null ? tag("Localiser : ?", "warn") : tag(d.localiser ? "Localiser ACTIVÉ" : "Localiser OFF", d.localiser ? "danger" : "ok")}
        ${tag("Batterie " + (pct != null ? pct + " %" : "?"), pct == null ? "warn" : pct >= 85 ? "ok" : pct >= 80 ? "warn" : "danger")}
        ${tag(d.origine, d.origine_niveau)}
      </div>
    </div>
    ${ticketBanner}
    <div class="actions-bar">
      <button class="act" id="a-tests"><b>🧪 Tests guidés</b><small>${nOk + nKo ? `${nOk} OK${nKo ? " · " + nKo + " défaut(s)" : ""}` : "Écran, Face ID, caméras…"}</small></button>
      <button class="act" id="a-fiche"><b>📋 Fiche & historique</b><small>${esc(f.reference)} · ${esc(f.statut)}</small></button>
      <button class="act" id="a-ticket"><b>🔧 Réparation client</b><small>Bon de dépôt, suivi</small></button>
      <button class="act" id="a-repair"><b>🔩 Noter une intervention</b><small>Pièce posée, coût</small></button>
      <a class="act" href="/rapport/${f.id}" target="_blank"><b>📄 Rapport de vente</b><small>PDF pour l'acheteur</small></a>
    </div>
    <div class="card workflow">
      <div class="row between wrap"><h3>Suivi d'une réparation (avant / après)</h3><span class="muted small">Pour prouver ce qui a été changé</span></div>
      <div class="wf-steps">
        <div class="wf ${wf.avant ? "done" : ""}"><span>1</span><div><b>Photo « avant »</b><small>${wf.avant ? "Enregistrée le " + frDate(wf.avant.date) : "Avant d'ouvrir le téléphone"}</small></div>
          <button class="btn small" data-mark="Avant réparation">${wf.avant ? "Refaire" : "Marquer ce diagnostic"}</button></div>
        <div class="wf ${wf.apres ? "done" : ""}"><span>2</span><div><b>Répare, rebranche, puis « après »</b><small>${wf.apres ? "Enregistrée le " + frDate(wf.apres.date) : "Le diagnostic se relance tout seul au branchement"}</small></div>
          <button class="btn small" data-mark="Après réparation" ${wf.avant ? "" : "disabled"}>Marquer ce diagnostic</button></div>
        <div class="wf ${wf.avant && wf.apres ? "" : "off"}"><span>3</span><div><b>Comparer</b><small>Batterie, iOS, numéros de série…</small></div>
          <button class="btn small primary" id="wf-compare" ${wf.avant && wf.apres ? "" : "disabled"}>Voir l'avant / après</button></div>
      </div>
    </div>
    ${alerts ? `<div class="alerts">${alerts}</div>` : ""}
    <div class="grid2">
      <div class="card"><h3>Batterie</h3>
        <div class="gauge">
          <div class="ring" style="--p:${pct || 0};--c:${ringColor(pct || 0)}"><b>${pct != null ? pct + "%" : "?"}</b></div>
          ${kv([["Santé", pct != null ? pct + " %" : "non lisible"], ["Cycles", b.cycles], ["Capacité d'origine", b.capacite_origine ? b.capacite_origine + " mAh" : null],
               ["Capacité actuelle", b.capacite_max ? b.capacite_max + " mAh" : null], ["Température", b.temperature ? b.temperature + " °C" : null],
               ["N° série batterie", b.serie_batterie, 1]])}
        </div>
        <p class="small muted" style="margin:10px 0 0">Charge en direct : <b id="live-charge">—</b></p>
        ${pct == null ? `<p class="small muted">Santé non lisible par câble sur cette version d'iOS : vérifie dans Réglages › Batterie.</p>` : ""}
      </div>
      <div class="card"><h3>Identifiants <span class="muted small">(clic = copier)</span></h3>${kv([["Numéro de série", d.serie, 1], ["IMEI", d.imei, 1], ["IMEI 2", d.imei2, 1],
        ["Référence", d.numero_modele, 1], ["Région", d.region], ["Modèle interne", (d.product_type || "") + " · " + (d.hardware || "")],
        ["iOS", (d.ios || "") + " (" + (d.build || "") + ")"], ["Modem", d.modem], ["ICCID (SIM)", d.iccid, 1]])}
        ${d.imei ? `<a class="btn small ghost" href="https://www.imei.info/?imei=${encodeURIComponent(d.imei)}" target="_blank" rel="noopener">Vérifier l'IMEI en ligne ↗</a>` : ""}
      </div>
      <div class="card"><h3>Stockage</h3>
        ${st.capacite ? `<div class="row between"><b>${esc(st.capacite)}</b><span class="muted">${st.utilise_pct}% utilisé</span></div><div class="bar"><i style="width:${st.utilise_pct}%"></i></div>
          ${st.utilise_pct > 10 && f.statut !== "Client (réparation)" ? `<p class="small muted">Il reste des données : pense à une restauration (Outils) avant la vente.</p>` : ""}` : `<p class="muted">${esc(st.erreur || "Non lisible")}</p>`}
        <h3 style="margin-top:16px">Pièces d'origine & opérateur</h3>
        <p class="small muted">Non lisibles par câble (Apple ne les expose pas). Sur l'iPhone :<br>
        • <b>Réglages › Général › Informations › Historique des pièces et réparations</b> : « Pièce inconnue » = pièce non d'origine.<br>
        • <b>… › Verrouillage opérateur</b> : doit indiquer « Aucune restriction SIM ».</p>
      </div>
      <div class="card"><h3>Pièces compatibles en stock</h3>
        ${S.piecesCompat.length ? `<table class="recap">${S.piecesCompat.map(p => `<tr><td>${esc(p.nom)}</td><td class="muted">${esc(p.qualite || "")}</td><td>${eur(p.cout)}</td><td class="${p.alerte ? "neg" : ""}">${p.quantite} en stock</td></tr>`).join("")}</table>`
          : `<p class="muted small">Aucune pièce enregistrée pour « ${esc(d.modele)} ». Ajoute tes pièces dans l'onglet Pièces (champ « Compatible » : ex. « iPhone 13, 13 Pro »).</p>`}
      </div>
    </div>`;
  $("#a-tests").onclick = () => openTests();
  $("#a-fiche").onclick = () => openPhone(f.id);
  $("#a-ticket").onclick = () => S.ticketsActifs.length ? openTicket(S.ticketsActifs[0].id) : openTicket(null, {appareil: d.modele + (st.capacite ? " " + st.capacite : ""), imei: d.imei, phone_id: f.id});
  $("#a-repair").onclick = () => openPhone(f.id, "rep");
  $$("[data-open-ticket]").forEach(b => b.onclick = () => openTicket(+b.dataset.openTicket));
  $$("[data-mark]").forEach(b => b.onclick = e => busy(e.currentTarget, async () => {
    const sid = (S.fiche.scans || [])[0].id;
    await api(`/api/scans/${sid}/label`, {method: "POST", body: {etiquette: b.dataset.mark}});
    S.fiche = (await api("/api/phones/" + S.fiche.id)).fiche; renderDiag();
    toast(b.dataset.mark === "Avant réparation" ? "« Avant » enregistré. Tu peux réparer, puis rebrancher l'iPhone." : "« Après » enregistré.", "ok");
  }));
  const cmp = $("#wf-compare");
  if (cmp) cmp.onclick = () => { const w = workflowState(S.fiche); showCompare(S.fiche.id, w.avant.id, w.apres.id); };
}

/* ------------------------------------------------------------ tests guidés */
let T = {i: 0, res: {}};
function openTests(start = 0) {
  if (!S.fiche) return;
  T = {i: start, res: Object.assign({}, S.fiche.tests || {})};
  renderTest(); $("#m-tests").classList.remove("hidden");
}
function renderTest() {
  if (T.i >= TESTS.length) return finishTests();
  const [name, help] = TESTS[T.i], cur = T.res[name];
  $("#t-bar").style.width = (T.i / TESTS.length * 100) + "%";
  $("#t-count").textContent = `Test ${T.i + 1} sur ${TESTS.length}` + (cur ? ` · déjà noté : ${cur === "ok" ? "fonctionne" : cur === "ko" ? "défaut" : "passé"}` : "");
  $("#t-name").textContent = name;
  let extra = "";
  if (name === "Charge (câble)" && S.live && S.live.en_charge) extra = " ✅ Valya Scan voit que l'iPhone charge en ce moment.";
  $("#t-help").textContent = help + extra;
  $("#t-prev").disabled = T.i === 0;
}
$$("#m-tests [data-res]").forEach(b => b.onclick = () => { T.res[TESTS[T.i][0]] = b.dataset.res; T.i++; renderTest(); });
$("#t-prev").onclick = () => { if (T.i > 0) { T.i--; renderTest(); } };
async function finishTests() {
  $("#m-tests").classList.add("hidden");
  try {
    const d = await api("/api/phones/" + S.fiche.id, {method: "PUT", body: {tests: T.res}});
    S.fiche = Object.assign(S.fiche, {tests: d.fiche.tests}); S.fiche = d.fiche;
    const ko = Object.entries(T.res).filter(([, v]) => v === "ko").map(([k]) => k);
    toast(ko.length ? "Tests enregistrés. Défauts : " + ko.join(", ") : "Tests enregistrés : tout fonctionne ✓", ko.length ? "err" : "ok");
    if (S.scan) renderDiag();
  } catch (e) { toast(e.message, "err"); }
}

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
  const mode = b.dataset.restore, ipsw = ($("#ipsw-in").value || "").trim();
  let html;
  if (mode === "effacer") {
    html = `<div class="alert danger">TOUTES les données de l'iPhone seront effacées. Si Localiser est activé, l'iPhone restera bloqué sur le compte iCloud du propriétaire après la restauration.</div>
      <p>Tape <b>EFFACER</b> pour confirmer :</p><input id="conf-erase" autocomplete="off">`;
  } else {
    html = `<p>iOS va être mis à jour vers la dernière version signée par Apple${ipsw ? " (fichier " + esc(ipsw) + ")" : ""}. Les données sont conservées, mais fais une sauvegarde avant par sécurité.</p>
      <p class="muted small">Le téléchargement peut faire plusieurs Go. Ne débranche pas l'iPhone avant la fin.</p>`;
  }
  if (!await confirmBox(mode === "effacer" ? "Restauration complète" : "Mise à jour iOS", html, "Lancer", mode === "effacer")) return;
  const body = {mode, ipsw, confirmation: mode === "effacer" ? ($("#conf-erase") || {}).value : null};
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

/* ------------------------------------------------------------ mes téléphones */
let stockTimer;
$("#q").oninput = () => { clearTimeout(stockTimer); stockTimer = setTimeout(loadStock, 250); };
$("#f-statut").onchange = loadStock;
async function loadStock() {
  const d = await api(`/api/phones?q=${encodeURIComponent($("#q").value)}&statut=${encodeURIComponent($("#f-statut").value)}`).catch(e => toast(e.message, "err"));
  if (!d) return;
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
    <td><span class="st">${esc(p.statut)}</span></td>
    <td>${p.localiser ? '<span class="tag danger">iCloud</span>' : ""}${p.sheets_ligne ? '<span class="tag ok">Sheets</span>' : ""}</td></tr>`).join("")
    : `<tr><td colspan="10" class="muted" style="text-align:center;padding:30px">Aucun téléphone. Branche un iPhone pour créer la première fiche.</td></tr>`;
  $$("#tbl tbody tr[data-id]").forEach(tr => tr.onclick = () => openPhone(+tr.dataset.id));
}

async function openPhone(id, tab = "infos") {
  const d = await api("/api/phones/" + id).catch(e => toast(e.message, "err"));
  if (!d) return;
  const p = d.fiche, diag = p.dernier_diagnostic || {};
  const parts = (await api("/api/parts").catch(() => ({pieces: []}))).pieces;
  const tabs = [["infos", "Infos & prix"], ["rep", `Interventions (${p.reparations.length})`], ["hist", "Historique"],
                ["cmp", "Avant / après"], ["diag", `Diagnostics (${p.scans.length})`]];
  const body = openBig(`${p.reference} · ${p.modele || ""} ${p.stockage || ""}`, `
    <div class="tabs">${tabs.map(([k, l]) => `<button class="tab ${k === tab ? "active" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>
    <div data-pane="infos" class="${tab === "infos" ? "" : "hidden"}">
      <div class="grid2">
        <div>
          <div class="row gap"><label class="grow">Modèle<input name="modele" value="${esc(p.modele)}"></label><label class="grow">Stockage<input name="stockage" value="${esc(p.stockage)}"></label></div>
          <div class="row gap"><label class="grow">Couleur<input name="couleur" value="${esc(p.couleur)}"></label><label class="grow">Batterie (%)<input name="sante_batterie" value="${esc(p.sante_batterie)}"></label></div>
          <div class="row gap"><label class="grow">État<select name="etat">${opts(S.meta.etats, p.etat)}</select></label><label class="grow">Statut<select name="statut">${opts(S.meta.statuts, p.statut)}</select></label></div>
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
          <p class="small">Tests : ${Object.keys(p.tests).length ? Object.entries(p.tests).map(([k, v]) => `<span class="tag ${v === "ok" ? "ok" : v === "ko" ? "danger" : ""}">${esc(k)}</span>`).join(" ") : "<span class='muted'>pas encore faits</span>"}</p>
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
      ${repairForm(parts, p.modele)}
      ${repairTable(p.reparations)}
    </div>
    <div data-pane="hist" class="${tab === "hist" ? "" : "hidden"}">
      ${p.tickets.length ? `<p class="small">Fiches de réparation : ${p.tickets.map(t => `<a href="#" data-open-ticket="${t.id}">${esc(t.numero)} (${esc(t.statut)})</a>`).join(", ")}</p>` : ""}
      ${timeline(p.historique)}
    </div>
    <div data-pane="cmp" class="${tab === "cmp" ? "" : "hidden"}">
      ${p.scans.length < 2 ? "<p class='muted'>Il faut au moins deux diagnostics (branche l'iPhone avant et après la réparation).</p>" : `
      <div class="row gap wrap"><label class="grow">Avant<select id="cmp-a">${p.scans.map((s, i) => `<option value="${s.id}" ${s.etiquette === "Avant réparation" || (i === 1 && !p.scans.some(x => x.etiquette === "Avant réparation")) ? "selected" : ""}>${frDate(s.date)}${s.etiquette ? " — " + esc(s.etiquette) : ""}</option>`).join("")}</select></label>
      <label class="grow">Après<select id="cmp-b">${p.scans.map((s, i) => `<option value="${s.id}" ${s.etiquette === "Après réparation" || (i === 0 && !p.scans.some(x => x.etiquette === "Après réparation")) ? "selected" : ""}>${frDate(s.date)}${s.etiquette ? " — " + esc(s.etiquette) : ""}</option>`).join("")}</select></label>
      <button class="btn primary" id="cmp-go" style="margin-top:8px">Comparer</button></div><div id="cmp-out"></div>`}
    </div>
    <div data-pane="diag" class="${tab === "diag" ? "" : "hidden"}">
      <table class="recap"><tr><th>Date</th><th>Étiquette</th><th></th></tr>${p.scans.map(s => `<tr><td>${frDate(s.date)}</td><td>${esc(s.etiquette || "")}</td><td><button class="btn small" data-scan="${s.id}">Voir</button></td></tr>`).join("")}</table>
      <div id="scan-view">${diagSummary(diag)}</div>
    </div>`);
  $$("[data-tab]", body).forEach(b => b.onclick = () => {
    $$("[data-tab]", body).forEach(x => x.classList.toggle("active", x === b));
    $$("[data-pane]", body).forEach(x => x.classList.toggle("hidden", x.dataset.pane !== b.dataset.tab));
  });
  const infos = $("[data-pane=infos]", body);
  $("#mp-save").onclick = e => busy(e.currentTarget, async () => {
    await api("/api/phones/" + id, {method: "PUT", body: formData(infos)}); toast("Fiche enregistrée", "ok");
    openPhone(id); loadStock(); refreshCurrent(id);
  });
  $("#mp-del").onclick = async () => {
    if (!await confirmBox("Supprimer la fiche ?", `<p>${esc(p.reference)} et tout son historique seront supprimés de Valya Scan (le Google Sheets n'est pas modifié).</p>`, "Supprimer", true)) return;
    await api("/api/phones/" + id, {method: "DELETE"}); closeBig(); loadStock(); toast("Fiche supprimée");
  };
  $("#mp-sheets").onclick = e => sendToSheets(id, e.currentTarget, infos);
  bindRepairForm(body, async data => {
    await api(`/api/phones/${id}/repairs`, {method: "POST", body: data}); toast("Intervention enregistrée", "ok");
    openPhone(id, "rep"); loadStock(); refreshCurrent(id);
  });
  $$("[data-rdel]", body).forEach(b => b.onclick = async () => {
    if (!await confirmBox("Supprimer l'intervention ?", "<p class='muted'>Si une pièce du stock avait été utilisée, elle y est remise.</p>", "Supprimer", true)) return;
    await api(`/api/phones/${id}/repairs/${b.dataset.rdel}`, {method: "DELETE"}); openPhone(id, "rep");
  });
  $$("[data-scan]", body).forEach(b => b.onclick = async () => { const s = await api("/api/scans/" + b.dataset.scan); $("#scan-view").innerHTML = diagSummary(s.diagnostic); });
  $$("[data-open-ticket]", body).forEach(a => a.onclick = ev => { ev.preventDefault(); openTicket(+a.dataset.openTicket); });
  const go = $("#cmp-go");
  if (go) go.onclick = () => showCompare(id, +$("#cmp-a").value, +$("#cmp-b").value, $("#cmp-out"));
}
async function refreshCurrent(id) {
  if (S.fiche && S.fiche.id === id && S.scan) { S.fiche = (await api("/api/phones/" + id)).fiche; renderDiag(); }
}
function repairForm(parts, modele) {
  const m = (modele || "").toLowerCase().replace("iphone", "").trim();
  const sorted = parts.slice().sort((a, b) => ((b.compatible || "").toLowerCase().includes(m) ? 1 : 0) - ((a.compatible || "").toLowerCase().includes(m) ? 1 : 0));
  return `<div class="card repair-form">
    <div class="row gap wrap">
      <label class="grow">Pièce du stock (optionnel)<select name="part_id"><option value="">— Saisie libre —</option>${sorted.map(p =>
        `<option value="${p.id}" ${p.quantite <= 0 ? "disabled" : ""}>${esc(p.nom)} · ${esc(p.qualite || "")} · ${p.quantite} en stock${m && (p.compatible || "").toLowerCase().includes(m) ? " ★" : ""}</option>`).join("")}</select></label>
      <label class="grow">Intervention<input name="piece" placeholder="ex. Remplacement écran"></label>
    </div>
    <div class="row gap wrap">
      <label>Qualité<select name="qualite">${opts(S.meta.qualites, "")}</select></label>
      <label>Coût (€)<input name="cout" placeholder="auto si pièce du stock" style="max-width:150px"></label>
      <label class="grow">Note (fournisseur, détail…)<input name="note"></label>
      <button class="btn primary" data-add-repair style="margin-top:8px">Ajouter</button>
    </div>
    <p class="small muted" style="margin:0">Pièce non d'origine Apple (écran, batterie, caméra) : un message « Pièce inconnue » peut apparaître dans Réglages. C'est normal et ça doit être signalé à l'acheteur ou au client.</p>
  </div>`;
}
function bindRepairForm(root, onSubmit) {
  const btn = $("[data-add-repair]", root);
  if (!btn) return;
  btn.onclick = e => busy(e.currentTarget, async () => onSubmit(formData($(".repair-form", root))));
}
const repairTable = reps => `<table class="recap"><tr><th>Date</th><th>Intervention</th><th>Qualité</th><th>Coût</th><th>Note</th><th></th></tr>
  ${reps.map(r => `<tr><td>${frDate(r.date)}</td><td>${esc(r.piece)}</td><td>${esc(r.qualite || "")}</td><td>${eur(r.cout)}</td><td class="muted">${esc(r.note)}</td><td><button class="btn small ghost" data-rdel="${r.id}">×</button></td></tr>`).join("")
    || `<tr><td colspan="6" class="muted">Aucune intervention.</td></tr>`}</table>`;

function diagSummary(d) {
  if (!d || !d.modele) return "<p class='muted'>Pas de diagnostic.</p>";
  const b = d.batterie || {}, st = d.stockage || {};
  const rows = [["Date", d.scanne_le], ["Verdict", (d.verdict || {}).titre], ["Modèle", d.modele + " (" + d.product_type + ")"], ["iOS", d.ios], ["Série", d.serie], ["IMEI", d.imei],
    ["Référence", d.numero_modele], ["Origine", d.origine], ["Région", d.region], ["Activation", d.activation],
    ["Localiser", d.localiser == null ? "non déterminé" : d.localiser ? "ACTIVÉ" : "désactivé"], ["Batterie", b.sante != null ? b.sante + " % · " + (b.cycles ?? "?") + " cycles" : "—"],
    ["N° série batterie", b.serie_batterie], ["Stockage", st.capacite ? st.capacite + " (" + st.utilise_pct + " % utilisé)" : "—"]];
  return `${(d.alertes || []).map(a => `<div class="alert ${a.niveau}" style="margin-bottom:6px">${esc(a.texte)}</div>`).join("")}
    <dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${dash(v)}</dd>`).join("")}</dl>`;
}
async function showCompare(pid, a, b, target) {
  try {
    const c = (await api(`/api/phones/${pid}/compare?a=${a}&b=${b}`)).comparaison;
    const n = c.lignes.filter(l => l.change).length;
    const html = `<p class="muted small">Avant : ${frDate(c.avant.date)} · Après : ${frDate(c.apres.date)}</p>
      <div class="alert ${n ? "info" : "ok"}">${n ? n + " élément(s) ont changé — en jaune ci-dessous." : "Aucun changement détecté entre les deux diagnostics."}</div>
      <table class="recap cmp"><tr><th>Élément</th><th>Avant</th><th>Après</th></tr>${c.lignes.map(l => `<tr class="${l.change ? "changed" : ""}"><td>${esc(l.champ)}</td><td>${dash(l.avant === true ? "oui" : l.avant === false ? "non" : l.avant)}</td><td>${dash(l.apres === true ? "oui" : l.apres === false ? "non" : l.apres)}</td></tr>`).join("")}</table>
      <p class="small muted">Un changement de « N° série batterie » prouve que la batterie a été remplacée. Pour l'écran et les caméras, Apple n'expose pas de numéro par câble : consigne-les dans les interventions.</p>`;
    if (target) target.innerHTML = html; else openBig("Avant / après réparation", html);
  } catch (e) { toast(e.message, "err"); }
}

async function sendToSheets(id, btn, infos) {
  await busy(btn, async () => {
    await api("/api/phones/" + id, {method: "PUT", body: formData(infos)});
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

/* ------------------------------------------------------------ réparations clients */
let tFilter = "actifs", tTimer;
$("#tq").oninput = () => { clearTimeout(tTimer); tTimer = setTimeout(loadTickets, 250); };
$("#btn-new-ticket").onclick = () => openTicket(null, S.scan && S.fiche ? {appareil: S.scan.modele + (S.scan.stockage && S.scan.stockage.capacite ? " " + S.scan.stockage.capacite : ""), imei: S.scan.imei, phone_id: S.fiche.id} : {});
async function loadTickets() {
  const q = encodeURIComponent($("#tq").value);
  const url = tFilter === "actifs" ? `/api/tickets?actifs=1&q=${q}` : tFilter === "tous" ? `/api/tickets?q=${q}` : `/api/tickets?statut=${encodeURIComponent(tFilter)}&q=${q}`;
  const d = await api(url).catch(e => toast(e.message, "err"));
  if (!d) return;
  const cnt = d.compteurs, actifs = d.statuts.filter(s => !["Rendu", "Annulé"].includes(s)).reduce((n, s) => n + (cnt[s] || 0), 0);
  $("#ticket-chips").innerHTML = [["actifs", "En cours", actifs], ...d.statuts.map(s => [s, s, cnt[s] || 0]), ["tous", "Toutes", null]]
    .map(([k, l, n]) => `<button class="chip ${tFilter === k ? "active" : ""}" data-chip="${esc(k)}">${esc(l)}${n != null ? ` <b>${n}</b>` : ""}</button>`).join("");
  $$("[data-chip]").forEach(c => c.onclick = () => { tFilter = c.dataset.chip; loadTickets(); });
  $("#ticket-list").innerHTML = d.tickets.length ? d.tickets.map(t => `<div class="tcard s-${esc(t.statut).replace(/\s/g, "")}" data-t="${t.id}">
      <div class="row between"><b>${esc(t.numero)} · ${esc(t.client_nom)}</b><span class="st">${esc(t.statut)}</span></div>
      <div>${esc(t.appareil || "Appareil ?")} — ${esc(t.probleme)}</div>
      <div class="row between small muted"><span>Déposé le ${frDate(t.date_depot)}${t.date_prevue ? " · prévu le " + frDate(t.date_prevue) : ""}</span><span>${t.devis != null ? "Devis " + eur(t.devis) : ""}</span></div>
    </div>`).join("") : `<p class="muted">Aucune réparation ${tFilter === "actifs" ? "en cours" : "ici"}.</p>`;
  $$("[data-t]").forEach(x => x.onclick = () => openTicket(+x.dataset.t));
}
async function refreshCounters() {
  try {
    const d = await api("/api/tickets?actifs=1"); const n = d.tickets.length;
    $("#rep-count").textContent = n; $("#rep-count").classList.toggle("hidden", !n);
    const p = (await api("/api/parts")).pieces.filter(x => x.alerte).length;
    $("#parts-alert").textContent = p; $("#parts-alert").classList.toggle("hidden", !p);
  } catch (e) {}
}

async function openTicket(id, preset = {}) {
  let t = preset, parts = [];
  if (id) { t = (await api("/api/tickets/" + id).catch(e => toast(e.message, "err")) || {}).ticket; if (!t) return; }
  parts = (await api("/api/parts").catch(() => ({pieces: []}))).pieces;
  const isNew = !id;
  const canLink = S.fiche && S.scan && S.udid && t.phone_id !== S.fiche.id;
  const steps = S.meta.ticket_statuts.filter(s => s !== "Annulé");
  const body = openBig(isNew ? "Nouvelle réparation client" : `${t.numero} · ${t.client_nom}`, `
    ${isNew ? "" : `<div class="stepper">${steps.map(s => `<button class="step ${s === t.statut ? "cur" : steps.indexOf(s) < steps.indexOf(t.statut) ? "done" : ""}" data-status="${esc(s)}">${esc(s)}</button>`).join("")}</div>`}
    <div class="grid2 tform">
      <div>
        <div class="row gap"><label class="grow">Nom du client *<input name="client_nom" value="${esc(t.client_nom)}"></label><label class="grow">Téléphone / Snap<input name="client_tel" value="${esc(t.client_tel)}"></label></div>
        <div class="row gap"><label class="grow">Appareil<input name="appareil" value="${esc(t.appareil)}" placeholder="ex. iPhone 13 128 Go"></label><label class="grow">IMEI<input name="imei" value="${esc(t.imei)}"></label></div>
        <label>Panne / demande *<textarea name="probleme" rows="2" placeholder="ex. Écran cassé, tactile OK">${esc(t.probleme)}</textarea></label>
        <label>État au dépôt (rayures, chocs, ce qui marche…)<textarea name="etat_depot" rows="2">${esc(t.etat_depot)}</textarea></label>
      </div>
      <div>
        <label>Diagnostic / travaux prévus<textarea name="diagnostic" rows="2">${esc(t.diagnostic)}</textarea></label>
        <div class="row gap"><label class="grow">Devis (€)<input name="devis" value="${esc(t.devis)}"></label><label class="grow">Acompte (€)<input name="acompte" value="${esc(t.acompte)}"></label><label class="grow">Prêt pour le<input type="date" name="date_prevue" value="${esc(t.date_prevue)}"></label></div>
        <label class="check"><input type="checkbox" name="info_piece" ${t.info_piece ? "checked" : ""}> Client informé : une pièce non d'origine Apple peut afficher « Pièce inconnue »</label>
        <label>Notes internes<textarea name="notes" rows="2">${esc(t.notes)}</textarea></label>
        <input type="hidden" name="phone_id" value="${esc(t.phone_id || "")}">
        <p class="small">${t.telephone ? `iPhone associé : <b>${esc(t.telephone.reference)}</b> · ${esc(t.telephone.modele)} · ${esc(t.telephone.serie)}` : t.phone_id ? "iPhone associé (branché)." : "<span class='muted'>Aucun iPhone associé : branche-le pour tracer les diagnostics avant/après.</span>"}
        ${canLink && !isNew ? `<button class="btn small" id="t-link">Associer l'iPhone branché (${esc(S.fiche.reference)})</button>` : ""}</p>
      </div>
    </div>
    <div class="row gap wrap between">
      <div class="row gap wrap">${isNew ? "" : `<button class="btn danger" id="t-del">Supprimer</button>`}</div>
      <div class="row gap wrap">
        ${isNew ? "" : `<a class="btn" href="/bon/${t.id}?type=depot" target="_blank">🖨 Bon de dépôt</a><a class="btn" href="/bon/${t.id}?type=restitution" target="_blank">🖨 Bon de restitution</a>`}
        <button class="btn primary" id="t-save">${isNew ? "Créer la fiche" : "Enregistrer"}</button>
      </div>
    </div>
    ${isNew ? "" : `
    <h3 style="margin-top:20px">Interventions ${t.reste_a_payer != null ? `<span class="muted small">· reste à payer : <b>${eur(t.reste_a_payer)}</b> · coût pièces : ${eur(t.cout_pieces)}</span>` : ""}</h3>
    ${t.phone_id ? repairForm(parts, (t.telephone || {}).modele || t.appareil) : "<p class='muted small'>Associe l'iPhone pour noter les interventions (et décompter les pièces).</p>"}
    ${repairTable(t.reparations)}
    <h3 style="margin-top:20px">Historique</h3>${timeline(t.historique)}`}`);
  const form = $(".tform", body);
  const save = async (extra = {}) => {
    const data = Object.assign(formData(form), extra);
    if (isNew) {
      const r = await api("/api/tickets", {method: "POST", body: data});
      toast(`Fiche ${r.ticket.numero} créée`, "ok"); openTicket(r.ticket.id);
    } else {
      await api("/api/tickets/" + t.id, {method: "PUT", body: data}); toast("Fiche enregistrée", "ok"); openTicket(t.id);
    }
    loadTickets(); refreshCounters();
  };
  $("#t-save").onclick = e => busy(e.currentTarget, () => save());
  $$("[data-status]", body).forEach(b => b.onclick = e => busy(e.currentTarget, () => save({statut: b.dataset.status})));
  const link = $("#t-link");
  if (link) link.onclick = e => busy(e.currentTarget, () => save({phone_id: S.fiche.id, imei: $("[name=imei]", form).value || S.scan.imei}));
  const del = $("#t-del");
  if (del) del.onclick = async () => {
    if (!await confirmBox("Supprimer la fiche de réparation ?", "<p class='muted'>Les interventions restent dans l'historique du téléphone.</p>", "Supprimer", true)) return;
    await api("/api/tickets/" + t.id, {method: "DELETE"}); closeBig(); loadTickets(); refreshCounters();
  };
  bindRepairForm(body, async data => {
    await api(`/api/tickets/${t.id}/repairs`, {method: "POST", body: data}); toast("Intervention enregistrée", "ok");
    openTicket(t.id); refreshCounters();
  });
  $$("[data-rdel]", body).forEach(b => b.onclick = async () => {
    if (!await confirmBox("Supprimer l'intervention ?", "<p class='muted'>La pièce est remise en stock.</p>", "Supprimer", true)) return;
    await api(`/api/phones/${t.phone_id}/repairs/${b.dataset.rdel}`, {method: "DELETE"}); openTicket(t.id);
  });
}

/* ------------------------------------------------------------ pièces */
let pTimer;
$("#pq").oninput = () => { clearTimeout(pTimer); pTimer = setTimeout(loadParts, 250); };
$("#btn-new-part").onclick = () => openPart(null);
let PARTS = [];
async function loadParts() {
  const d = await api("/api/parts?q=" + encodeURIComponent($("#pq").value)).catch(e => toast(e.message, "err"));
  if (!d) return;
  PARTS = d.pieces;
  $("#parts-tbl tbody").innerHTML = PARTS.length ? PARTS.map(p => `<tr>
    <td><b>${esc(p.nom)}</b></td><td>${esc(p.categorie || "")}</td><td class="muted">${esc(p.compatible || "")}</td><td>${esc(p.qualite || "")}</td>
    <td class="muted">${esc(p.fournisseur || "")}</td><td>${eur(p.cout)}</td>
    <td><div class="qty"><button class="btn small ghost" data-q="${p.id}" data-d="-1">−</button><b class="${p.alerte ? "neg" : ""}">${p.quantite}</b><button class="btn small ghost" data-q="${p.id}" data-d="1">+</button></div></td>
    <td><button class="btn small" data-pe="${p.id}">Modifier</button></td></tr>`).join("")
    : `<tr><td colspan="8" class="muted" style="text-align:center;padding:30px">Aucune pièce. Ajoute tes écrans, batteries… pour suivre ton stock et tes coûts.</td></tr>`;
  $$("[data-q]").forEach(b => b.onclick = async () => {
    const p = PARTS.find(x => x.id === +b.dataset.q);
    await api("/api/parts/" + p.id, {method: "PUT", body: {quantite: Math.max(0, p.quantite + +b.dataset.d)}}).catch(e => toast(e.message, "err"));
    loadParts(); refreshCounters();
  });
  $$("[data-pe]").forEach(b => b.onclick = () => openPart(PARTS.find(x => x.id === +b.dataset.pe)));
}
function openPart(p) {
  p = p || {quantite: 1, seuil: 1};
  const body = openBig(p.id ? "Modifier la pièce" : "Nouvelle pièce", `<div class="pform">
    <label>Nom *<input name="nom" value="${esc(p.nom)}" placeholder="ex. Écran OLED iPhone 13"></label>
    <div class="row gap"><label class="grow">Catégorie<select name="categorie">${opts(S.meta.categories, p.categorie)}</select></label><label class="grow">Qualité<select name="qualite">${opts(S.meta.qualites, p.qualite)}</select></label></div>
    <label>Compatible avec (sépare par des virgules)<input name="compatible" value="${esc(p.compatible)}" placeholder="ex. iPhone 13, iPhone 13 Pro"></label>
    <div class="row gap"><label class="grow">Fournisseur<input name="fournisseur" value="${esc(p.fournisseur)}"></label><label class="grow">Coût unitaire (€)<input name="cout" value="${esc(p.cout)}"></label></div>
    <div class="row gap"><label class="grow">Quantité<input name="quantite" value="${esc(p.quantite)}"></label><label class="grow">Alerte quand il en reste ≤<input name="seuil" value="${esc(p.seuil)}"></label></div>
    <div class="row gap between">${p.id ? `<button class="btn danger" id="p-del">Supprimer</button>` : "<span></span>"}<button class="btn primary" id="p-save">Enregistrer</button></div></div>`);
  $("#p-save").onclick = e => busy(e.currentTarget, async () => {
    await api(p.id ? "/api/parts/" + p.id : "/api/parts", {method: p.id ? "PUT" : "POST", body: formData($(".pform", body))});
    closeBig(); loadParts(); refreshCounters(); toast("Pièce enregistrée", "ok");
  });
  const del = $("#p-del");
  if (del) del.onclick = async () => { if (await confirmBox("Supprimer cette pièce ?", "", "Supprimer", true)) { await api("/api/parts/" + p.id, {method: "DELETE"}); closeBig(); loadParts(); refreshCounters(); } };
}

/* ------------------------------------------------------------ réglages */
async function loadSettings() {
  const d = await api("/api/settings").catch(e => toast(e.message, "err"));
  if (!d) return;
  S.settings = d.reglages;
  $("#data-dir").textContent = "Données enregistrées dans : " + d.dossier_donnees;
  $$("[data-set]").forEach(i => { const v = d.reglages[i.dataset.set]; if (i.type === "checkbox") i.checked = !!v; else i.value = v ?? ""; });
  $("#key-state").textContent = d.reglages.service_account_path ? "✓ Clé enregistrée." : "Aucune clé pour l'instant.";
  if (!d.google_dispo) $("#key-state").textContent += " ⚠️ Modules manquants : relance Valya Scan.";
}
$$("[data-save-set]").forEach(b => b.onclick = e => {
  const body = {};
  $$("[data-set]").forEach(i => body[i.dataset.set] = i.type === "checkbox" ? i.checked : i.value.trim());
  busy(e.currentTarget, async () => { await api("/api/settings", {method: "POST", body}); toast("Réglages enregistrés", "ok"); loadSettings(); });
});
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

/* ------------------------------------------------------------ démarrage */
(async () => {
  try { S.meta = await api("/api/meta"); } catch (e) {}
  try { S.settings = (await api("/api/settings")).reglages; } catch (e) {}
  poll(); refreshCounters();
  setInterval(poll, 3000);
  setInterval(refreshCounters, 30000);
})();
