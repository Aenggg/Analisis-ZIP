const DEFAULT_API_BASE = window.location.protocol === "file:"
  ? "http://localhost:8000"
  : window.location.origin;
let API_BASE = localStorage.getItem("p2pApiBase") || DEFAULT_API_BASE;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortHash(value) {
  if (!value) return "-";
  return value.length > 20 ? `${value.slice(0, 12)}...${value.slice(-8)}` : value;
}

function setNotice(box, message, type = "info") {
  const styles = {
    info: "border-cyan-200 bg-cyan-50 text-cyan-900",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
    error: "border-rose-200 bg-rose-50 text-rose-900",
  };
  box.innerHTML = `<div class="rounded border ${styles[type]} p-3">${escapeHtml(message)}</div>`;
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function pill(text, tone = "slate") {
  const styles = {
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    green: "border-emerald-200 bg-emerald-50 text-emerald-700",
    red: "border-rose-200 bg-rose-50 text-rose-700",
    cyan: "border-cyan-200 bg-cyan-50 text-cyan-700",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    violet: "border-violet-200 bg-violet-50 text-violet-800",
  };
  return `<span class="inline-flex rounded border px-2 py-1 text-xs font-semibold ${styles[tone]}">${escapeHtml(text)}</span>`;
}

function stat(label, value) {
  return `
    <div class="soft p-3">
      <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">${escapeHtml(label)}</p>
      <p class="mt-1 break-all text-sm font-medium">${escapeHtml(value)}</p>
    </div>
  `;
}

function renderActivity(items) {
  if (!items.length) {
    return `<div class="soft p-4 text-sm text-slate-500">Belum ada aktivitas registrasi ZIP pada node ini.</div>`;
  }

  return items.map((item) => `
    <div class="soft p-4">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="font-semibold text-slate-950">${escapeHtml(item.file_name || "ZIP tanpa nama")}</p>
          <p class="mt-1 break-all text-xs text-slate-500">${escapeHtml(item.file_hash)}</p>
        </div>
        ${pill(shortHash(item.block_hash), "violet")}
      </div>
      <div class="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-3">
        <span>Owner: <strong>${escapeHtml(item.owner || "-")}</strong></span>
        <span>Merkle: <strong>${escapeHtml(shortHash(item.merkle_root))}</strong></span>
        <span>Waktu: <strong>${escapeHtml(formatTime(item.timestamp))}</strong></span>
      </div>
    </div>
  `).join("");
}

function saveApiBase() {
  const input = document.getElementById("apiBaseInput");
  API_BASE = input.value.trim().replace(/\/$/, "");
  localStorage.setItem("p2pApiBase", API_BASE);
  loadAll();
}

function getFilenameFromDisposition(disposition) {
  if (!disposition) return "";
  const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch) return decodeURIComponent(utfMatch[1].replaceAll('"', ""));
  const quotedMatch = disposition.match(/filename="([^"]+)"/i);
  if (quotedMatch) return quotedMatch[1];
  const plainMatch = disposition.match(/filename=([^;]+)/i);
  return plainMatch ? plainMatch[1].trim() : "";
}

function renderUpload(box, data) {
  const broadcastOk = (data.broadcast || []).filter((item) => item.ok).length;
  box.innerHTML = `
    <div class="rounded border border-emerald-200 bg-emerald-50 p-4">
      <div class="flex items-center justify-between gap-3">
        <p class="font-bold text-emerald-900">Tersimpan dan dibroadcast</p>
        ${pill("OK", "green")}
      </div>
      <div class="mt-3 grid gap-2">
        ${stat("Hash SHA-256", data.file_hash)}
        ${stat("Merkle Root", data.merkle_root)}
        ${stat("Block", `#${data.block_index} - ${shortHash(data.block_hash)}`)}
        ${stat("Broadcast Peer", `${broadcastOk}/${(data.broadcast || []).length}`)}
      </div>
    </div>
  `;
}

function renderVerify(box, data) {
  const authentic = Boolean(data.authentic);
  const title = authentic ? "&check; ASLI" : "&times; PALSU";
  const panelClass = authentic
    ? "rounded border border-emerald-200 bg-emerald-50 p-4"
    : "rounded border border-rose-200 bg-rose-50 p-4";
  const titleClass = authentic ? "text-2xl font-black text-emerald-900" : "text-2xl font-black text-rose-900";
  const messageClass = authentic ? "mt-1 text-sm text-emerald-900" : "mt-1 text-sm text-rose-900";
  const status = authentic ? pill("Ceklis", "green") : pill("X", "red");
  const message = authentic
    ? "File ZIP masih sama dengan data yang tersimpan di blockchain."
    : (data.reason || "File ZIP tidak cocok dengan data yang tersimpan.");

  box.innerHTML = `
    <div class="${panelClass}">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="${titleClass}">${title}</p>
          <p class="${messageClass}">${escapeHtml(message)}</p>
        </div>
        ${status}
      </div>
      <div class="mt-3 grid gap-2">
        ${stat("File Diuji", data.uploaded_file_name || "-")}
        ${data.registered_file_name ? stat("Nama Terdaftar", data.registered_file_name) : ""}
        ${stat("Hash", data.file_hash || data.uploaded_file_hash || "-")}
        ${stat("Merkle Root", data.merkle_root || data.uploaded_merkle_root || "-")}
      </div>
    </div>
  `;
}

function renderPeers(data) {
  const box = document.getElementById("peerBox");
  const peers = Object.entries(data || {});
  const onlineCount = peers.filter(([, info]) => ["self", "online"].includes(info.status)).length;
  box.innerHTML = `
    <div class="surface p-5">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-bold">Pengguna dan Peer</h3>
          <p class="mt-1 text-xs text-slate-500">${onlineCount}/${peers.length} node aktif</p>
        </div>
        ${pill(`${peers.length} node`, "cyan")}
      </div>
      <div class="mt-4 space-y-2">
        ${peers.length ? peers.map(([url, info]) => `
          <div class="soft p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="break-all text-sm font-semibold">${escapeHtml(info.node_id || url)}</p>
              ${pill(info.status || "unknown", info.status === "self" || info.status === "online" ? "green" : "amber")}
            </div>
            <p class="mt-1 break-all text-xs text-slate-500">${escapeHtml(url)}</p>
            <p class="mt-1 text-xs text-slate-400">Sumber: ${escapeHtml(info.source || "-")}</p>
          </div>
        `).join("") : `<div class="soft p-3 text-sm text-slate-500">Belum ada peer dari konfigurasi.</div>`}
      </div>
    </div>
  `;
}

async function uploadFile() {
  const input = document.getElementById("uploadFileInput");
  const box = document.getElementById("uploadResult");

  if (!input.files.length) return setNotice(box, "Pilih file ZIP terlebih dahulu.", "error");
  if (!input.files[0].name.toLowerCase().endsWith(".zip")) return setNotice(box, "File harus berformat .zip.", "error");

  const fd = new FormData();
  fd.append("file", input.files[0]);
  setNotice(box, "Menghitung hash, membuat Merkle root, menyimpan block, lalu broadcast ke peer...");

  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json();
    return setNotice(box, err.detail || "Registrasi gagal.", "error");
  }
  renderUpload(box, await res.json());
  loadSummary();
}

async function verifyFile() {
  const input = document.getElementById("verifyFileInput");
  const box = document.getElementById("verifyResult");

  if (!input.files.length) return setNotice(box, "Pilih file ZIP yang ingin diverifikasi.", "error");
  if (!input.files[0].name.toLowerCase().endsWith(".zip")) return setNotice(box, "File verifikasi harus berformat .zip.", "error");

  const fd = new FormData();
  fd.append("file", input.files[0]);
  setNotice(box, "Mencocokkan ZIP dengan hash dan Merkle root pada blockchain...");

  const res = await fetch(`${API_BASE}/verify_file`, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json();
    return setNotice(box, err.detail || "Verifikasi gagal.", "error");
  }
  renderVerify(box, await res.json());
}

async function downloadFile() {
  const hash = document.getElementById("downloadHashInput").value.trim();
  const box = document.getElementById("downloadResult");
  if (!hash) return setNotice(box, "Hash SHA-256 wajib diisi.", "error");

  setNotice(box, "Mengecek chunk lokal dan mengambil chunk dari peer jika diperlukan...");
  const res = await fetch(`${API_BASE}/download/${hash}`);
  if (!res.ok) {
    const err = await res.json();
    return setNotice(box, err.detail || "Download gagal.", "error");
  }

  const blob = await res.blob();
  const filename = getFilenameFromDisposition(res.headers.get("content-disposition") || "") || "file-zip-tersimpan.zip";
  const fetched = res.headers.get("x-p2p-fetched-chunks") || "[]";
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);

  box.innerHTML = `
    <div class="rounded border border-emerald-200 bg-emerald-50 p-4">
      <p class="font-bold text-emerald-900">Download berhasil</p>
      <div class="mt-3 grid gap-2">
        ${stat("Nama File", filename)}
        ${stat("Chunk Diambil Dari Peer", fetched)}
      </div>
    </div>
  `;
}

async function syncChain() {
  const box = document.getElementById("syncResult");
  setNotice(box, "Mencari peer aktif lalu sinkronisasi ledger...");
  try {
    await fetch(`${API_BASE}/discover`, { method: "POST" });
  } catch (e) {
    // Sync tetap dicoba walau discovery manual gagal.
  }
  const res = await fetch(`${API_BASE}/sync`, { method: "POST" });
  const data = await res.json();
  box.innerHTML = `
    <div class="rounded border border-cyan-200 bg-cyan-50 p-4">
      <p class="font-bold text-cyan-900">Sinkronisasi selesai</p>
      <div class="mt-3 grid gap-2">
        ${stat("Panjang Chain Lokal", data.local_length)}
        ${stat("Status Lokal", data.local_valid ? "Valid" : "Tidak valid")}
        ${stat("Hasil Peer", JSON.stringify(data.results || []))}
      </div>
    </div>
  `;
  loadSummary();
}

async function validatePeers() {
  const box = document.getElementById("peerValidationResult");
  setNotice(box, "Memvalidasi chain pada peer...");
  const res = await fetch(`${API_BASE}/peers/validate`);
  const data = await res.json();
  const peers = data.peers || [];
  box.innerHTML = `
    <div class="space-y-2">
      ${peers.length ? peers.map((peer) => `
        <div class="soft p-3">
          <div class="flex items-center justify-between gap-3">
            <p class="break-all font-semibold">${escapeHtml(peer.peer)}</p>
            ${pill(peer.valid && peer.reachable ? "Valid" : "Bermasalah", peer.valid && peer.reachable ? "green" : "red")}
          </div>
          <p class="mt-1 text-xs text-slate-500">Length: ${escapeHtml(peer.length ?? "-")} | Same tip: ${escapeHtml(peer.same_tip ?? false)}</p>
        </div>
      `).join("") : `<div class="soft p-3 text-slate-500">Tidak ada peer untuk divalidasi.</div>`}
    </div>
  `;
  loadNodes();
}

async function loadNodes() {
  try {
    await fetch(`${API_BASE}/discover`, { method: "POST" });
  } catch (e) {
    // Panel peer tetap menampilkan node yang sudah diketahui.
  }
  const res = await fetch(`${API_BASE}/nodes`);
  renderPeers(await res.json());
}

async function loadSummary() {
  const box = document.getElementById("summaryBox");
  setNotice(box, "Memuat status blockchain...");
  const res = await fetch(`${API_BASE}/summary`);
  const data = await res.json();

  document.getElementById("activeNodeLabel").textContent = data.node_url || API_BASE;
  const activeNodeBadge = document.getElementById("activeNodeBadge");
  if (activeNodeBadge) activeNodeBadge.textContent = data.node_id || "node aktif";
  const chainHealth = document.getElementById("chainHealth");
  if (chainHealth) chainHealth.textContent = data.blockchain_valid ? "Valid" : "Perlu dicek";
  const samples = data.files_keys_sample?.length
    ? renderActivity(data.files_keys_sample)
    : renderActivity([]);

  box.innerHTML = `
    <div class="surface p-5">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        ${stat("Node ID", data.node_id || "-")}
        ${stat("Total Block", data.total_blocks)}
        ${stat("File ZIP", data.files_registered)}
        <div class="soft p-3">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Status Chain</p>
          <div class="mt-2">${pill(data.blockchain_valid ? "Valid" : "Tidak valid", data.blockchain_valid ? "green" : "red")}</div>
        </div>
      </div>
      <div class="mt-4">
        <div class="mb-3 flex items-center justify-between gap-3">
          <p class="text-xs font-bold uppercase tracking-wide text-slate-500">Aktivitas Multi Pengguna</p>
          ${pill(`${data.peers_configured || 0} peer konfigurasi`, "slate")}
        </div>
        <div class="grid gap-2">${samples}</div>
      </div>
    </div>
  `;
}

function loadAll() {
  document.getElementById("apiBaseInput").value = API_BASE;
  document.getElementById("activeNodeLabel").textContent = API_BASE;
  loadSummary();
  loadNodes();
}

window.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();
  loadAll();
});
