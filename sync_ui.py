"""
Codex History Selective Sync - tkinter GUI
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path
import sys

if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)
_backend_dir = Path(__file__).resolve().parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from sync_backend import get_status, make_backup, selective_sync, resolve_paths

BACKEND = Path(__file__).parent / "sync_backend.py"

def run_backend(*args: str) -> dict:
    cmd = args[0]
    paths = resolve_paths(None)
    if cmd == "status":
        return get_status(paths)
    elif cmd == "backup":
        bp = make_backup(paths, "manual")
        return {"backup_path": str(bp)}
    elif cmd == "selective-sync":
        target_provider = None
        target_model = None
        source_providers = []
        i = 1
        while i < len(args):
            if args[i] == "--target-provider" and i + 1 < len(args):
                target_provider = args[i + 1]
                i += 2
            elif args[i] == "--target-model" and i + 1 < len(args):
                target_model = args[i + 1]
                i += 2
            elif args[i] == "--source-providers" and i + 1 < len(args):
                source_providers = [s.strip() for s in args[i + 1].split(",")]
                i += 2
            else:
                i += 1
        if not target_provider or not source_providers:
            raise RuntimeError("缺少参数")
        return selective_sync(paths, target_provider, target_model, source_providers)
    else:
        raise RuntimeError(f"未知命令: {cmd}")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Codex 历史选择性同步")
        self.root.geometry("860x680")
        self.root.minsize(860, 680)
        self.root.configure(bg="#f6f8fb")

        self.latest_state: dict | None = None
        self.all_providers: list[str] = []
        self.source_vars: dict[str, tk.BooleanVar] = {}
        self.busy = False

        self._build_ui()
        self._refresh_state()

    def _build_ui(self):
        f = tk.Label(self.root, text="Codex 历史选择性同步",
                     font=("Microsoft YaHei UI", 16, "bold"),
                     bg="#f6f8fb", fg="#1a1a2e")
        f.pack(anchor="w", padx=24, pady=(16, 0))

        s = tk.Label(self.root,
                     text="勾选要从哪些 provider 迁出，选择迁到哪个 provider。每次操作前自动备份。",
                     font=("Microsoft YaHei UI", 9), bg="#f6f8fb", fg="#646478",
                     anchor="w", justify="left")
        s.pack(anchor="w", padx=26, pady=(4, 0))

        self.lbl_cur = tk.Label(self.root, text="加载中...",
                                font=("Microsoft YaHei UI", 9, "bold"),
                                bg="#f6f8fb", fg="#333")
        self.lbl_cur.pack(anchor="w", padx=26, pady=(12, 0))

        self.lbl_tot = tk.Label(self.root, text="", font=("Microsoft YaHei UI", 9),
                                bg="#f6f8fb", fg="#555")
        self.lbl_tot.pack(anchor="w", padx=26)

        self.lbl_st = tk.Label(self.root, text="加载中...",
                               font=("Microsoft YaHei UI", 9),
                               bg="#f6f8fb", fg="#1c54a0")
        self.lbl_st.pack(anchor="w", padx=26)

        self.prog = ttk.Progressbar(self.root, mode="indeterminate", length=790)
        self.prog.pack(padx=26, pady=(2, 0))

        main = tk.Frame(self.root, bg="#f6f8fb")
        main.pack(fill="both", expand=True, padx=26, pady=(10, 0))

        # Source frame
        sf = tk.LabelFrame(main, text="来源（勾选要迁出的 provider）",
                           font=("Microsoft YaHei UI", 9), bg="#f6f8fb",
                           padx=8, pady=4)
        sf.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.src_cv = tk.Canvas(sf, bg="white", highlightthickness=0)
        sb = tk.Scrollbar(sf, orient="vertical", command=self.src_cv.yview)
        self.src_in = tk.Frame(self.src_cv, bg="white")
        self.src_in.bind("<Configure>",
                         lambda e: self.src_cv.configure(
                             scrollregion=self.src_cv.bbox("all")))
        self.src_cv.create_window((0, 0), window=self.src_in, anchor="nw")
        self.src_cv.configure(yscrollcommand=sb.set)
        self.src_cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        br = tk.Frame(sf, bg="#f6f8fb")
        br.pack(fill="x", pady=(4, 0))
        tk.Button(br, text="全选", width=8, command=self._sel_all).pack(side="left", padx=(0, 4))
        tk.Button(br, text="取消全选", width=8, command=self._sel_none).pack(side="left")

        # Right panel
        rt = tk.Frame(main, bg="#f6f8fb")
        rt.pack(side="right", fill="both", expand=True)

        tf = tk.LabelFrame(rt, text="目标",
                           font=("Microsoft YaHei UI", 9), bg="#f6f8fb",
                           padx=8, pady=4)
        tf.pack(fill="x", pady=(0, 10))
        tk.Label(tf, text="迁到:", bg="#f6f8fb").pack(side="left")
        self.tgt_var = tk.StringVar()
        self.tgt_cb = ttk.Combobox(tf, textvariable=self.tgt_var,
                                   state="readonly", width=30)
        self.tgt_cb.pack(side="left", padx=(6, 0))
        self.tgt_cb.bind("<<ComboboxSelected>>", lambda e: self._upd_preview())

        pf = tk.LabelFrame(rt, text="预览",
                           font=("Microsoft YaHei UI", 9), bg="#f6f8fb",
                           padx=8, pady=4)
        pf.pack(fill="x", pady=(0, 10))
        self.lbl_pv = tk.Label(pf, text="请勾选来源并选择目标。",
                               font=("Microsoft YaHei UI", 9),
                               bg="#f6f8fb", fg="#555",
                               anchor="w", justify="left", wraplength=340)
        self.lbl_pv.pack(fill="x")

        # Buttons
        bf = tk.Frame(self.root, bg="#f6f8fb")
        bf.pack(fill="x", padx=26, pady=(0, 4))
        tk.Button(bf, text="刷新状态", width=12, height=2,
                  command=self._refresh_state).pack(side="left", padx=(0, 8))
        self.btn_sync = tk.Button(bf, text="执行同步", width=14, height=2,
                                  bg="#205bb1", fg="white",
                                  command=self._do_sync)
        self.btn_sync.pack(side="left", padx=(0, 8))
        tk.Button(bf, text="仅备份", width=10, height=2,
                  command=self._do_backup).pack(side="left")

        # Log
        lf = tk.LabelFrame(self.root, text="日志",
                           font=("Microsoft YaHei UI", 9), bg="#f6f8fb",
                           padx=4, pady=4)
        lf.pack(fill="both", expand=True, padx=26, pady=(0, 10))
        self.log = tk.Text(lf, height=10, wrap="word",
                           font=("Consolas", 9), bg="white", fg="#333",
                           state="disabled")
        ls = tk.Scrollbar(lf, command=self.log.yview)
        self.log.configure(yscrollcommand=ls.set)
        self.log.pack(side="left", fill="both", expand=True)
        ls.pack(side="right", fill="y")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool, msg: str = ""):
        self.busy = busy
        self.btn_sync.configure(state="disabled" if busy else "normal")
        if busy:
            self.lbl_st.configure(text=msg)
            self.prog.start(10)
        else:
            self.prog.stop()
            self.lbl_st.configure(text="就绪")

    def _refresh_state(self):
        def work():
            try:
                data = run_backend("status")
                self.root.after(0, lambda: self._apply_state(data))
                mv = data.get("movable_threads", 0)
                if mv > 0:
                    self.root.after(0, lambda: self._log(
                        f"状态已刷新。{mv} 条线程归属与当前不一致，可同步。"))
                else:
                    self.root.after(0, lambda: self._log(
                        "状态已刷新。所有线程归属一致，无需操作。"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("刷新失败", str(e)))
                self.root.after(0, lambda: self._log(f"刷新失败: {e}"))
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        self._set_busy(True, "正在加载状态...")
        threading.Thread(target=work, daemon=True).start()

    def _apply_state(self, data: dict):
        self.latest_state = data
        self.all_providers = [r["provider"] for r in data.get("provider_counts", [])]
        cur = data["current_provider"]

        self.lbl_cur.configure(
            text=f"当前: provider={cur}, 模型={data.get('current_model', 'N/A')}")
        self.lbl_tot.configure(
            text=f"总线程: {data['total_threads']} | "
                 f"会话文件: {data['session_file_count']} | "
                 f"侧边栏: {data.get('indexed_threads', 0)}")

        for w in self.src_in.winfo_children():
            w.destroy()
        self.source_vars.clear()

        for row in data.get("provider_counts", []):
            prov = row["provider"]
            cnt = row["count"]
            mark = " [当前]" if prov == cur else ""
            label = f"{prov}  ({cnt} 条){mark}"
            var = tk.BooleanVar(value=(prov != cur))
            self.source_vars[prov] = var
            cb = tk.Checkbutton(self.src_in, text=label, variable=var,
                                bg="white", anchor="w",
                                font=("Microsoft YaHei UI", 9),
                                command=self._upd_preview)
            cb.pack(fill="x", padx=4, pady=1)

        self.tgt_cb["values"] = self.all_providers
        if cur in self.all_providers:
            self.tgt_var.set(cur)

        self._upd_preview()

    def _checked(self) -> list[str]:
        return [p for p, v in self.source_vars.items() if v.get()]

    def _upd_preview(self):
        ck = self._checked()
        tg = self.tgt_var.get()
        if not tg or not ck:
            self.lbl_pv.configure(text="请勾选来源并选择目标。")
            return
        total = 0
        if self.latest_state:
            for row in self.latest_state.get("provider_counts", []):
                if row["provider"] in ck:
                    total += row["count"]
        self.lbl_pv.configure(
            text=f"将 {total} 条线程从 [{', '.join(ck)}] 迁到 [{tg}]")

    def _sel_all(self):
        for v in self.source_vars.values():
            v.set(True)
        self._upd_preview()

    def _sel_none(self):
        for v in self.source_vars.values():
            v.set(False)
        self._upd_preview()

    def _do_sync(self):
        ck = self._checked()
        tg = self.tgt_var.get()
        if not tg:
            messagebox.showwarning("未选择目标", "请先选择目标 provider。")
            return
        if not ck:
            messagebox.showwarning("未选择来源", "请至少勾选一个来源 provider。")
            return

        total = 0
        if self.latest_state:
            for row in self.latest_state.get("provider_counts", []):
                if row["provider"] in ck:
                    total += row["count"]

        msg = (f"即将把 {total} 条线程从以下 provider 迁出:\n"
               f"{', '.join(ck)}\n\n迁入目标: {tg}\n\n"
               f"操作前会自动备份。确定继续？")
        if not messagebox.askyesno("确认同步", msg):
            self._log("用户取消了同步。")
            return

        def work():
            try:
                self.root.after(0, lambda: self._set_busy(
                    True, "正在同步，Codex 忙时会自动等待..."))
                r = run_backend("selective-sync",
                                "--target-provider", tg,
                                "--source-providers", ",".join(ck))

                def done():
                    self._log(f"同步完成！数据库更新 {r['updated_rows']} 条，"
                              f"会话文件更新 {r['updated_session_files']} 个。")
                    self._log(f"备份文件: {r['backup_path']}")
                    t = r.get("timing", {})
                    self._log(f"耗时: {t.get('total_ms', 0) / 1000:.1f} 秒")
                    self._log(f"侧边栏索引已重建: {r['rewritten_index_entries']} 条")
                    self._apply_state(r["status"])
                    self._set_busy(False)
                    messagebox.showinfo("完成",
                                        "同步完成。如侧边栏未刷新，重启 Codex 即可。")

                self.root.after(0, done)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("同步失败", str(e)))
                self.root.after(0, lambda: self._log(f"同步失败: {e}"))
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=work, daemon=True).start()

    def _do_backup(self):
        def work():
            try:
                self.root.after(0, lambda: self._set_busy(True, "正在创建备份..."))
                r = run_backend("backup")
                self.root.after(0, lambda: self._log(f"备份完成: {r['backup_path']}"))
                self.root.after(0, lambda: self._refresh_state())
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("备份失败", str(e)))
                self.root.after(0, lambda: self._log(f"备份失败: {e}"))
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        self._set_busy(True, "正在创建备份...")
        threading.Thread(target=work, daemon=True).start()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
