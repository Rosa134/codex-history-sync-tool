
"""
Codex History Selective Sync - Web UI
Launches a local HTTP server and opens the browser.
No external dependencies (stdlib only).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BACKEND = Path(__file__).parent / "sync_backend.py"
PORT = 17890

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Codex 历史选择性同步</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;background:#f6f8fb;color:#333;padding:20px;max-width:900px;margin:0 auto}
h1{font-size:22px;color:#1a1a2e;margin-bottom:4px}
.sub{color:#646478;margin-bottom:20px;font-size:14px}
.status{background:white;border-radius:8px;padding:14px 18px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.status .cur{font-weight:bold;color:#1c54a0}
.status .info{color:#555;font-size:13px;margin-top:4px}
.grid{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}
.panel{background:white;border-radius:8px;padding:14px 18px;box-shadow:0 1px 3px rgba(0,0,0,.08);flex:1;min-width:280px}
.panel h3{font-size:14px;color:#333;margin-bottom:10px;border-bottom:1px solid #eee;padding-bottom:8px}
.src-item{display:flex;align-items:center;padding:4px 0;font-size:13px}
.src-item input{margin-right:8px;accent-color:#205bb1}
.preview{background:white;border-radius:8px;padding:14px 18px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:16px}
.preview p{font-size:14px;color:#333}
.actions{display:flex;gap:10px;margin-bottom:16px}
button{padding:10px 20px;border:none;border-radius:6px;font-size:14px;cursor:pointer;font-family:inherit}
.btn-sync{background:#205bb1;color:white}
.btn-sync:hover{background:#1a4d96}
.btn-refresh{background:#e8edf3;color:#333}
.btn-refresh:hover{background:#d0d8e3}
.btn-backup{background:#e8edf3;color:#333}
.btn-backup:hover{background:#d0d8e3}
button:disabled{opacity:.5;cursor:not-allowed}
.log{background:white;border-radius:8px;padding:14px 18px;box-shadow:0 1px 3px rgba(0,0,0,.08);max-height:240px;overflow-y:auto;font-family:Consolas,monospace;font-size:12px;color:#555;white-space:pre-wrap}
.spinner{display:none;width:20px;height:20px;border:2px solid #e0e0e0;border-top:2px solid #205bb1;border-radius:50%;animation:spin .8s linear infinite;margin-left:10px}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-row{display:flex;align-items:center}
</style>
</head>
<body>
<h1>Codex 历史选择性同步</h1>
<p class="sub">勾选要从哪些 provider 迁出，选择迁到哪个 provider。每次操作前自动备份。</p>

<div class="status">
  <div class="cur" id="currentLabel">加载中...</div>
  <div class="info" id="totalLabel"></div>
</div>

<div class="grid">
  <div class="panel">
    <h3>来源（勾选要迁出的 provider）</h3>
    <div id="sourceList"></div>
    <div style="margin-top:8px">
      <button class="btn-refresh" onclick="selectAll()" style="padding:4px 12px;font-size:12px">全选</button>
      <button class="btn-refresh" onclick="selectNone()" style="padding:4px 12px;font-size:12px">取消全选</button>
    </div>
  </div>
  <div class="panel">
    <h3>目标</h3>
    <div style="margin-bottom:10px">
      <label style="font-size:13px">迁到:</label>
      <select id="targetSelect" style="margin-left:6px;padding:4px 8px;font-size:13px;border:1px solid #ddd;border-radius:4px;min-width:200px" onchange="updatePreview()"></select>
    </div>
    <h3>预览</h3>
    <div class="preview" style="box-shadow:none;padding:8px 0"><p id="previewText">请勾选来源并选择目标。</p></div>
  </div>
</div>

<div class="actions loading-row">
  <button class="btn-refresh" onclick="refresh()">刷新状态</button>
  <button class="btn-sync" id="syncBtn" onclick="doSync()">执行同步</button>
  <button class="btn-refresh" onclick="doBackup()">仅备份</button>
  <div class="spinner" id="spinner"></div>
</div>

<div class="log" id="logBox"></div>

<script>
let state = null;

function log(msg) {
  const ts = new Date().toTimeString().slice(0,8);
  document.getElementById("logBox").textContent += "[" + ts + "] " + msg + "\n";
  const box = document.getElementById("logBox");
  box.scrollTop = box.scrollHeight;
}

function setBusy(b) {
  document.getElementById("syncBtn").disabled = b;
  document.getElementById("spinner").style.display = b ? "inline-block" : "none";
}

async function api(cmd, args={}) {
  const params = new URLSearchParams({cmd, ...args});
  const r = await fetch("/api?" + params.toString());
  return r.json();
}

function getChecked() {
  const boxes = document.querySelectorAll("#sourceList input[type=checkbox]");
  const checked = [];
  boxes.forEach(cb => { if(cb.checked) checked.push(cb.value); });
  return checked;
}

function selectAll() {
  document.querySelectorAll("#sourceList input[type=checkbox]").forEach(cb => cb.checked = true);
  updatePreview();
}

function selectNone() {
  document.querySelectorAll("#sourceList input[type=checkbox]").forEach(cb => cb.checked = false);
  updatePreview();
}

function updatePreview() {
  const checked = getChecked();
  const target = document.getElementById("targetSelect").value;
  const el = document.getElementById("previewText");
  if (!target || checked.length === 0) {
    el.textContent = "请勾选来源并选择目标。";
    return;
  }
  let total = 0;
  if (state) {
    state.provider_counts.forEach(row => {
      if (checked.includes(row.provider)) total += row.count;
    });
  }
  el.textContent = "将 " + total + " 条线程从 [" + checked.join(", ") + "] 迁到 [" + target + "]";
}

function applyState(data) {
  state = data;
  document.getElementById("currentLabel").textContent =
    "当前: provider=" + data.current_provider + ", 模型=" + (data.current_model || "N/A");
  document.getElementById("totalLabel").textContent =
    "总线程: " + data.total_threads + " | 会话文件: " + data.session_file_count + " | 侧边栏: " + (data.indexed_threads || 0);

  const srcDiv = document.getElementById("sourceList");
  srcDiv.innerHTML = "";
  const cur = data.current_provider;
  data.provider_counts.forEach(row => {
    const div = document.createElement("div");
    div.className = "src-item";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = row.provider;
    cb.checked = (row.provider !== cur);
    cb.onchange = updatePreview;
    div.appendChild(cb);
    const label = document.createElement("span");
    label.textContent = row.provider + " (" + row.count + " 条)" + (row.provider === cur ? " [当前]" : "");
    div.appendChild(label);
    srcDiv.appendChild(div);
  });

  const sel = document.getElementById("targetSelect");
  sel.innerHTML = "";
  data.provider_counts.forEach(row => {
    const opt = document.createElement("option");
    opt.value = row.provider;
    opt.textContent = row.provider;
    sel.appendChild(opt);
  });
  sel.value = cur;
  updatePreview();
}

async function refresh() {
  setBusy(true);
  try {
    const r = await api("status");
    if (r.ok) {
      applyState(r);
      log("状态已刷新。" + (r.movable_threads > 0 ? r.movable_threads + " 条线程归属与当前不一致，可同步。" : "所有线程归属一致，无需操作。"));
    } else {
      log("刷新失败: " + r.error);
    }
  } catch(e) {
    log("刷新失败: " + e);
  }
  setBusy(false);
}

async function doSync() {
  const checked = getChecked();
  const target = document.getElementById("targetSelect").value;
  if (!target) { alert("请先选择目标 provider。"); return; }
  if (checked.length === 0) { alert("请至少勾选一个来源 provider。"); return; }

  let total = 0;
  state.provider_counts.forEach(row => {
    if (checked.includes(row.provider)) total += row.count;
  });
  if (!confirm("即将把 " + total + " 条线程从以下 provider 迁出:\n" + checked.join(", ") + "\n\n迁入目标: " + target + "\n\n操作前会自动备份。确定继续？")) {
    log("用户取消了同步。");
    return;
  }

  setBusy(true);
  try {
    const r = await api("sync", {target: target, sources: checked.join(",")});
    if (r.ok) {
      log("同步完成！数据库更新 " + r.updated_rows + " 条，会话文件更新 " + r.updated_session_files + " 个。");
      log("备份文件: " + r.backup_path);
      log("侧边栏索引已重建: " + r.rewritten_index_entries + " 条");
      if (r.status) applyState(r.status);
      alert("同步完成。如侧边栏未刷新，重启 Codex 即可。");
    } else {
      log("同步失败: " + r.error);
    }
  } catch(e) {
    log("同步失败: " + e);
  }
  setBusy(false);
}

async function doBackup() {
  setBusy(true);
  try {
    const r = await api("backup");
    if (r.ok) {
      log("备份完成: " + r.backup_path);
      await refresh();
    } else {
      log("备份失败: " + r.error);
    }
  } catch(e) {
    log("备份失败: " + e);
  }
  setBusy(false);
}

refresh();
</script>
</body>
</html>"""


def run_backend_cli(*args: str) -> dict:
    proc = subprocess.run(
        ["py", "-3", str(BACKEND), "--json", *args],
        capture_output=True, text=True
    )
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"JSON parse failed: {proc.stdout[:200]}"}
    return {"ok": False, "error": proc.stderr or "No output"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress logs

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self._serve_html()
        elif parsed.path == "/api":
            self._handle_api(parse_qs(parsed.query))
        else:
            self.send_error(404)

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def _handle_api(self, params: dict):
        cmd = params.get("cmd", [""])[0]
        result = {"ok": False, "error": "Unknown command"}

        try:
            if cmd == "status":
                result = run_backend_cli("status")
            elif cmd == "sync":
                target = params.get("target", [""])[0]
                sources = params.get("sources", [""])[0]
                result = run_backend_cli("selective-sync",
                                         "--target-provider", target,
                                         "--source-providers", sources)
            elif cmd == "backup":
                result = run_backend_cli("backup")
        except Exception as e:
            result = {"ok": False, "error": str(e)}

        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Server starting at {url}")
    threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
