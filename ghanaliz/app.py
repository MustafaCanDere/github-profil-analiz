"""GitHub Profil Analiz - Tkinter arayüzü."""

import os
import queue
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import core

AI_FIXES = {"description", "topics", "readme", "license", "profile_bio", "profile_readme", "profile_readme_file"}

APP_TITLE = "GitHub Profil Analiz"
SEV_TAGS = {core.HIGH: "high", core.MEDIUM: "medium", core.LOW: "low"}


class TextDialog(tk.Toplevel):
    """Çok satırlı metin düzenleme penceresi (README vb. için)."""

    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.title(title)
        self.geometry("720x520")
        self.transient(parent)
        self.result = None
        self.txt = tk.Text(self, wrap="word", font=("Consolas", 10), undo=True)
        self.txt.insert("1.0", text)
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar, text="İptal", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Kaydet ve GitHub'a Gönder", command=self._ok).pack(side="right", padx=6)
        self.grab_set()
        self.wait_window()

    def _ok(self):
        self.result = self.txt.get("1.0", "end-1c")
        self.destroy()


def _topics(text):
    out = [re.sub(r"[^a-z0-9-]", "-", t.strip().lower()).strip("-")[:50] for t in text.split(",")]
    return [t for t in dict.fromkeys(out) if t][:20]


class Change:
    """AI'nin önerdiği tek bir değişiklik."""

    def __init__(self, iids, target, label, preview, apply, editable=False):
        self.iids, self.target, self.label = iids, target, label
        self.preview, self.apply, self.editable = preview, apply, editable
        self.enabled = True


class PreviewDialog(tk.Toplevel):
    """AI önerilerini gösterir; kullanıcı tek tıkla hepsini uygular."""

    def __init__(self, parent, changes):
        super().__init__(parent)
        self.title("AI önerileri — gözden geçir ve uygula")
        self.geometry("980x620")
        self.transient(parent)
        self.changes, self.ok, self.current = changes, False, None
        ttk.Label(self, padding=8, text="Uygulanmasını istemediklerinin işaretini kaldır (tıkla). "
                  "Metinleri sağ tarafta düzenleyebilirsin.").pack(fill="x")
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8)
        self.tree = ttk.Treeview(body, columns=("on",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Değişiklik")
        self.tree.heading("on", text="Uygula")
        self.tree.column("#0", width=330)
        self.tree.column("on", width=70, anchor="center", stretch=False)
        for n, c in enumerate(changes):
            self.tree.insert("", "end", iid=str(n), text=f"{c.target}: {c.label}", values=("✔",))
        self.tree.bind("<<TreeviewSelect>>", self._select)
        self.tree.bind("<Button-1>", self._toggle_click)
        body.add(self.tree, weight=1)
        self.txt = tk.Text(body, wrap="word", font=("Consolas", 10), undo=True)
        body.add(self.txt, weight=2)
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        self.count_lbl = ttk.Label(bar)
        self.count_lbl.pack(side="left")
        ttk.Button(bar, text="İptal", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Seçilenleri GitHub'a Uygula", command=self._ok).pack(side="right", padx=6)
        self._update_count()
        if changes:
            self.tree.selection_set("0")
        self.grab_set()
        self.wait_window()

    def _store(self):
        if self.current is not None and self.changes[self.current].editable:
            self.changes[self.current].preview = self.txt.get("1.0", "end-1c")

    def _select(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        self._store()
        self.current = int(sel[0])
        c = self.changes[self.current]
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", c.preview)
        if not c.editable:
            self.txt.config(state="disabled")

    def _toggle_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_column(event.x) == "#1":
            c = self.changes[int(iid)]
            c.enabled = not c.enabled
            self.tree.set(iid, "on", "✔" if c.enabled else "✖")
            self._update_count()

    def _update_count(self):
        n = sum(c.enabled for c in self.changes)
        self.count_lbl.config(text=f"{n}/{len(self.changes)} değişiklik uygulanacak")

    def _ok(self):
        self._store()
        self.ok = True
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x680")
        self.minsize(820, 520)
        self.client = None
        self.report = None
        self.me = None
        self.q = queue.Queue()
        self.item_issue = {}
        self.repo_map = {}
        self._build()
        self.after(100, self._poll)

    # ---------- arayüz ----------
    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("clam")
        style.configure("Score.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Treeview", rowheight=24)

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Kullanıcı adı:").grid(row=0, column=0, sticky="w")
        self.user_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.user_var, width=24)
        e.grid(row=0, column=1, padx=6)
        e.bind("<Return>", lambda _: self.start())
        ttk.Label(top, text="Token (isteğe bağlı):").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.token_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.token_var, width=36, show="•").grid(row=0, column=3, padx=6)
        self.fork_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Fork'ları dahil et", variable=self.fork_var).grid(row=0, column=4, padx=6)
        self.go_btn = ttk.Button(top, text="Analiz Et", command=self.start)
        self.go_btn.grid(row=0, column=5, padx=6)
        link = ttk.Label(top, text="Token nasıl alınır?", foreground="#0969da", cursor="hand2")
        link.grid(row=1, column=3, sticky="w", padx=6)
        link.bind("<Button-1>", lambda _: webbrowser.open(
            "https://github.com/settings/tokens/new?scopes=repo,user&description=GitHub%20Profil%20Analiz"))
        ttk.Label(top, text="Claude API anahtarı:").grid(row=2, column=2, sticky="w", padx=(12, 0), pady=(6, 0))
        self.ai_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        ttk.Entry(top, textvariable=self.ai_key_var, width=36, show="•").grid(row=2, column=3, padx=6, pady=(6, 0))
        self.ai_lang_var = tk.StringVar(value="Türkçe")
        ttk.Combobox(top, textvariable=self.ai_lang_var, values=("Türkçe", "English"), width=10,
                     state="readonly").grid(row=2, column=4, padx=6, pady=(6, 0))
        self.ai_btn = ttk.Button(top, text="🤖 AI ile Tümünü Düzelt", command=self.ai_fix_all, state="disabled")
        self.ai_btn.grid(row=2, column=5, padx=6, pady=(6, 0))
        klink = ttk.Label(top, text="API anahtarı nasıl alınır?", foreground="#0969da", cursor="hand2")
        klink.grid(row=3, column=3, sticky="w", padx=6)
        klink.bind("<Button-1>", lambda _: webbrowser.open("https://platform.claude.com/settings/keys"))

        info = ttk.Frame(self, padding=(10, 0))
        info.pack(fill="x")
        self.score_lbl = ttk.Label(info, text="—", style="Score.TLabel", width=8)
        self.score_lbl.pack(side="left")
        self.summary_lbl = ttk.Label(info, text="Bir kullanıcı adı girip 'Analiz Et'e bas.")
        self.summary_lbl.pack(side="left", padx=10)
        self.pbar = ttk.Progressbar(info, length=220, mode="determinate")
        self.pbar.pack(side="right")

        pane = ttk.PanedWindow(self, orient="vertical")
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        tf = ttk.Frame(pane)
        self.tree = ttk.Treeview(tf, columns=("sev", "fix"), show="tree headings")
        self.tree.heading("#0", text="Sorun")
        self.tree.heading("sev", text="Önem")
        self.tree.heading("fix", text="Otomatik düzeltme")
        self.tree.column("#0", width=560)
        self.tree.column("sev", width=90, anchor="center")
        self.tree.column("fix", width=140, anchor="center")
        self.tree.tag_configure("high", foreground="#cf222e")
        self.tree.tag_configure("medium", foreground="#9a6700")
        self.tree.tag_configure("low", foreground="#57606a")
        self.tree.tag_configure("done", foreground="#1a7f37")
        self.tree.tag_configure("group", font=("Segoe UI", 10, "bold"))
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _: self.fix_selected())
        pane.add(tf, weight=4)

        bf = ttk.Frame(pane)
        self.detail = tk.Text(bf, height=4, wrap="word", relief="flat", background=self.cget("bg"))
        self.detail.pack(fill="x")
        btns = ttk.Frame(bf)
        btns.pack(fill="x", pady=(6, 0))
        self.fix_btn = ttk.Button(btns, text="Seçileni Düzelt", command=self.fix_selected, state="disabled")
        self.fix_btn.pack(side="left")
        ttk.Button(btns, text="GitHub'da Aç", command=self.open_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="Raporu Kaydet (.md)", command=self.save_report).pack(side="right")
        pane.add(bf, weight=1)

        self.status = ttk.Label(self, text="Hazır", anchor="w", padding=(10, 2))
        self.status.pack(fill="x", side="bottom")

    # ---------- analiz ----------
    def start(self):
        user = self.user_var.get().strip()
        if not user:
            messagebox.showwarning(APP_TITLE, "Lütfen bir GitHub kullanıcı adı gir.")
            return
        self.go_btn.config(state="disabled")
        self.ai_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.item_issue.clear()
        self.client = core.GitHubClient(self.token_var.get())
        threading.Thread(target=self._worker, args=(user, self.fork_var.get()), daemon=True).start()

    def _worker(self, user, forks):
        try:
            me = self.client.me()
            rep = core.analyze(self.client, user, forks, lambda m, p: self.q.put(("progress", m, p)))
            self.q.put(("done", rep, me))
        except core.GitHubError as e:
            msg = "Kullanıcı bulunamadı." if e.status == 404 else str(e)
            if e.status == 401:
                msg = "Token geçersiz veya süresi dolmuş."
            self.q.put(("error", msg))
        except Exception as e:  # beklenmeyen hata
            self.q.put(("error", f"Beklenmeyen hata: {e}"))

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    self.status.config(text=msg[1])
                    self.pbar["value"] = msg[2]
                elif msg[0] == "done":
                    self._show(msg[1], msg[2])
                elif msg[0] == "call":
                    msg[1](*msg[2:])
                elif msg[0] == "error":
                    self.go_btn.config(state="normal")
                    self.status.config(text="Hata")
                    messagebox.showerror(APP_TITLE, msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _show(self, rep, me):
        self.report, self.me = rep, me
        self.ai_btn.config(state="normal" if rep.issues else "disabled")
        self.repo_map = {r["name"]: r for r in rep.repos}
        self.go_btn.config(state="normal")
        color = "#1a7f37" if rep.score >= 80 else "#9a6700" if rep.score >= 50 else "#cf222e"
        self.score_lbl.config(text=f"{rep.score}/100", foreground=color)
        u = rep.user
        self.summary_lbl.config(
            text=f"{u.get('name') or u['login']}  •  {len(rep.repos)} repo incelendi  •  "
                 f"{len(rep.issues)} sorun  •  {u.get('followers', 0)} takipçi")
        for target, issues in rep.by_target().items():
            parent = self.tree.insert("", "end", text=f"{target}  ({len(issues)})", open=True, tags=("group",))
            for i in issues:
                iid = self.tree.insert(parent, "end", text=i.title,
                                       values=(i.severity, "Var" if i.fix else "—"), tags=(SEV_TAGS[i.severity],))
                self.item_issue[iid] = i
        if not rep.issues:
            self.tree.insert("", "end", text="Harika! Hiç sorun bulunamadı. 🎉", tags=("done",))
        can_fix = me and me["login"].lower() == u["login"].lower()
        note = "" if can_fix else "  (Düzeltme için bu hesaba ait bir token gir.)"
        self.status.config(text=f"Analiz tamamlandı. Kalan API limiti: {self.client.remaining}{note}")

    # ---------- seçim ----------
    def _selected_issue(self):
        sel = self.tree.selection()
        return (sel[0], self.item_issue.get(sel[0])) if sel else (None, None)

    def _on_select(self, _):
        iid, issue = self._selected_issue()
        self.detail.delete("1.0", "end")
        if issue:
            self.detail.insert("1.0", f"{issue.target} — {issue.title}\n\n{issue.detail}")
        self.fix_btn.config(state="normal" if issue and issue.fix and "done" not in self.tree.item(iid, "tags")
                            else "disabled")

    def open_selected(self):
        if not self.report:
            return
        login = self.report.user["login"]
        _, issue = self._selected_issue()
        if issue and issue.target != "Profil":
            webbrowser.open(f"https://github.com/{login}/{issue.target}")
        else:
            webbrowser.open(f"https://github.com/{login}")

    def save_report(self):
        if not self.report:
            messagebox.showinfo(APP_TITLE, "Önce analiz yap.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")],
                                            initialfile=f"{self.report.user['login']}-analiz.md")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(core.export_markdown(self.report))
            self.status.config(text=f"Rapor kaydedildi: {path}")

    # ---------- düzeltmeler ----------
    def fix_selected(self):
        iid, issue = self._selected_issue()
        if not issue or not issue.fix or "done" in self.tree.item(iid, "tags"):
            return
        login = self.report.user["login"]
        if not self.me or self.me["login"].lower() != login.lower():
            messagebox.showwarning(APP_TITLE,
                                   "Düzeltme yapmak için bu hesaba ait bir token girip tekrar analiz etmelisin.\n\n"
                                   "Token izinleri: 'repo' ve 'user'.")
            return
        handler = getattr(self, f"_fix_{issue.fix}", None)
        try:
            if handler and handler(login, issue):
                self.tree.item(iid, text="✓ " + issue.title, tags=("done",))
                self.fix_btn.config(state="disabled")
                self.status.config(text=f"Düzeltildi: {issue.target} — {issue.title}")
        except core.GitHubError as e:
            hint = "\n\nToken'ın 'repo' ve 'user' izinlerine sahip olduğundan emin ol." if e.status in (403, 404) else ""
            messagebox.showerror(APP_TITLE, f"İşlem başarısız: {e}{hint}")

    def _ask(self, title, prompt, initial=""):
        val = simpledialog.askstring(title, prompt, initialvalue=initial, parent=self)
        return val.strip() if val and val.strip() else None

    def _fix_description(self, login, issue):
        val = self._ask("Açıklama", f"'{issue.target}' için kısa açıklama:")
        if val:
            self.client.update_repo(login, issue.target, description=val)
            return True

    def _fix_topics(self, login, issue):
        sugg = ", ".join(core.suggest_topics(self.repo_map[issue.target]))
        val = self._ask("Konu etiketleri", "Virgülle ayrılmış etiketler (küçük harf, tire kullanılabilir):", sugg)
        if val:
            self.client.set_topics(login, issue.target, _topics(val))
            return True

    def _fix_license(self, login, issue):
        holder = self.report.user.get("name") or login
        if messagebox.askyesno(APP_TITLE, f"'{issue.target}' reposuna MIT lisansı (LICENSE) eklensin mi?"):
            self.client.put_file(login, issue.target, "LICENSE", core.mit_license(holder), "Add MIT license")
            return True

    def _fix_readme(self, login, issue):
        dlg = TextDialog(self, f"README.md — {issue.target}", core.readme_template(self.repo_map[issue.target]))
        if dlg.result:
            self.client.put_file(login, issue.target, "README.md", dlg.result, "Add README")
            return True

    def _fix_archive(self, login, issue):
        if messagebox.askyesno(APP_TITLE, f"'{issue.target}' reposu arşivlensin mi?\n"
                                          "Arşivlenen repo salt okunur olur (GitHub ayarlarından geri alınabilir)."):
            self.client.update_repo(login, issue.target, archived=True)
            return True

    def _fix_homepage_pages(self, login, issue):
        url = f"https://{login.lower()}.github.io/{issue.target}/"
        if messagebox.askyesno(APP_TITLE, f"Website alanı '{url}' olarak ayarlansın mı?"):
            self.client.update_repo(login, issue.target, homepage=url)
            return True

    def _profile_field(self, field, title, prompt):
        val = self._ask(title, prompt)
        if val:
            self.client.update_profile(**{field: val})
            return True

    def _fix_profile_name(self, login, issue):
        return self._profile_field("name", "Görünen ad", "Profilde görünecek ad:")

    def _fix_profile_bio(self, login, issue):
        return self._profile_field("bio", "Biyografi", "Kısa biyografi (en fazla 160 karakter):")

    def _fix_profile_location(self, login, issue):
        return self._profile_field("location", "Konum", "Konum (ör. İstanbul, Türkiye):")

    def _fix_profile_blog(self, login, issue):
        return self._profile_field("blog", "Web sitesi", "Web sitesi / portföy bağlantısı:")

    def _fix_profile_twitter(self, login, issue):
        return self._profile_field("twitter_username", "X / Twitter", "X (Twitter) kullanıcı adı (@ olmadan):")

    def _fix_profile_readme(self, login, issue):
        dlg = TextDialog(self, f"Profil README — {login}/{login}", core.profile_readme_template(self.report.user))
        if dlg.result:
            self.client.create_repo(login, "Profil README")
            self.client.put_file(login, login, "README.md", dlg.result, "Add profile README")
            return True

    def _fix_profile_readme_file(self, login, issue):
        dlg = TextDialog(self, f"Profil README — {login}/{login}", core.profile_readme_template(self.report.user))
        if dlg.result:
            self.client.put_file(login, login, "README.md", dlg.result, "Add profile README")
            return True

    # ---------- AI ile toplu düzeltme ----------
    def ai_fix_all(self):
        if not self.report:
            return
        login = self.report.user["login"]
        if not self.me or self.me["login"].lower() != login.lower():
            messagebox.showwarning(APP_TITLE, "AI ile düzeltme için bu hesaba ait bir GitHub token'ı girip "
                                              "tekrar analiz etmelisin (izinler: 'repo' ve 'user').")
            return
        if not self.ai_key_var.get().strip():
            messagebox.showwarning(APP_TITLE, "Claude API anahtarını gir. 'API anahtarı nasıl alınır?' "
                                              "bağlantısından yeni bir anahtar oluşturabilirsin.")
            return
        todo = {}
        for iid, issue in self.item_issue.items():
            if issue.fix in AI_FIXES and "done" not in self.tree.item(iid, "tags"):
                todo.setdefault(issue.target, {})[issue.fix] = iid
        if not todo:
            messagebox.showinfo(APP_TITLE, "AI'nin düzeltebileceği bir eksik kalmadı.")
            return
        n_repo = sum(1 for t in todo if t != "Profil")
        if not messagebox.askyesno(APP_TITLE, f"Claude, {n_repo} repo ve profilin için öneriler hazırlayacak.\n"
                                              "Bu işlem Claude API hesabından ücret düşer ve birkaç dakika sürebilir.\n\n"
                                              "Hiçbir değişiklik sen onaylamadan GitHub'a gönderilmez. Devam edilsin mi?"):
            return
        self.ai_btn.config(state="disabled")
        self.go_btn.config(state="disabled")
        threading.Thread(target=self._ai_worker, args=(login, todo), daemon=True).start()


    def _ai_worker(self, login, todo):
        from . import ai  # anthropic paketini yalnızca gerektiğinde yükle
        gh, changes, errors = self.client, [], []
        try:
            bot = ai.Assistant(self.ai_key_var.get(), self.ai_lang_var.get())
        except Exception as e:
            self.q.put(("call", self._ai_done, [], [f"Claude istemcisi başlatılamadı: {e}"]))
            return
        targets = [t for t in todo if t != "Profil"] + (["Profil"] if "Profil" in todo else [])
        for n, target in enumerate(targets):
            fixes = todo[target]
            self.q.put(("progress", f"AI hazırlıyor: {target} ({n + 1}/{len(targets)})", int(100 * n / len(targets))))
            try:
                if target == "Profil":
                    changes += self._profile_changes(bot, login, fixes)
                else:
                    changes += self._repo_changes(bot, gh, login, target, fixes)
            except ai.AIError as e:
                errors.append(f"{target}: {e}")
                if "anahtar" in str(e) or "izni" in str(e):
                    break
            except core.GitHubError as e:
                errors.append(f"{target}: {e}")
        self.q.put(("progress", "AI önerileri hazır.", 100))
        self.q.put(("call", self._ai_done, changes, errors))


    def _repo_changes(self, bot, gh, login, name, fixes):
        repo = self.repo_map[name]
        out = []
        if "license" in fixes:
            holder = self.report.user.get("name") or login
            text = core.mit_license(holder)
            out.append(Change([fixes["license"]], name, "MIT lisansı ekle", text,
                              lambda c: gh.put_file(login, name, "LICENSE", c.preview, "Add MIT license")))
        if not fixes.keys() & {"description", "topics", "readme"}:
            return out
        res = bot.repo_fixes(gh, login, repo)
        if "description" in fixes and res["description"]:
            out.append(Change([fixes["description"]], name, "Açıklama", res["description"],
                              lambda c: gh.update_repo(login, name, description=c.preview.strip()), editable=True))
        if "topics" in fixes and res["topics"]:
            out.append(Change([fixes["topics"]], name, "Etiketler", ", ".join(res["topics"]),
                              lambda c: gh.set_topics(login, name, _topics(c.preview)), editable=True))
        if "readme" in fixes and res["readme"]:
            out.append(Change([fixes["readme"]], name, "README.md", res["readme"],
                              lambda c: gh.put_file(login, name, "README.md", c.preview, "Add README"), editable=True))
        return out


    def _profile_changes(self, bot, login, fixes):
        gh, out = self.client, []
        wants = fixes.keys() & {"profile_bio", "profile_readme", "profile_readme_file"}
        if not wants:
            return out
        res = bot.profile_fixes(self.report.user, self.report.repos)
        if "profile_bio" in fixes and res["bio"]:
            out.append(Change([fixes["profile_bio"]], "Profil", "Biyografi", res["bio"],
                              lambda c: gh.update_profile(bio=c.preview.strip()[:160]), editable=True))
        if res["profile_readme"]:
            if "profile_readme" in fixes:
                def apply(c):
                    gh.create_repo(login, "Profil README")
                    gh.put_file(login, login, "README.md", c.preview, "Add profile README")
                out.append(Change([fixes["profile_readme"]], "Profil", f"Profil README ({login}/{login})",
                                  res["profile_readme"], apply, editable=True))
            elif "profile_readme_file" in fixes:
                out.append(Change([fixes["profile_readme_file"]], "Profil", "Profil README.md", res["profile_readme"],
                                  lambda c: gh.put_file(login, login, "README.md", c.preview, "Add profile README"),
                                  editable=True))
        return out


    def _ai_done(self, changes, errors):
        self.go_btn.config(state="normal")
        self.ai_btn.config(state="normal")
        if not changes:
            messagebox.showerror(APP_TITLE, "AI öneri üretemedi.\n\n" + "\n".join(errors[:10]))
            self.status.config(text="AI önerisi üretilemedi.")
            return
        if errors:
            messagebox.showwarning(APP_TITLE, "Bazı öneriler hazırlanamadı:\n\n" + "\n".join(errors[:10]))
        dlg = PreviewDialog(self, changes)
        chosen = [c for c in changes if c.enabled] if dlg.ok else []
        if not chosen:
            self.status.config(text="AI önerileri uygulanmadı.")
            return
        self.ai_btn.config(state="disabled")
        self.go_btn.config(state="disabled")
        threading.Thread(target=self._ai_apply, args=(chosen,), daemon=True).start()


    def _ai_apply(self, chosen):
        done, errors = [], []
        for n, c in enumerate(chosen):
            self.q.put(("progress", f"Uygulanıyor: {c.target} — {c.label}", int(100 * n / len(chosen))))
            try:
                c.apply(c)
                done.append(c)
            except core.GitHubError as e:
                errors.append(f"{c.target} — {c.label}: {e}")
        self.q.put(("progress", "Tamamlandı.", 100))
        self.q.put(("call", self._ai_applied, done, errors))


    def _ai_applied(self, done, errors):
        self.go_btn.config(state="normal")
        self.ai_btn.config(state="normal")
        for c in done:
            for iid in c.iids:
                issue = self.item_issue[iid]
                self.tree.item(iid, text="✓ " + issue.title, tags=("done",))
        msg = f"{len(done)} değişiklik GitHub'a uygulandı."
        self.status.config(text=msg)
        if errors:
            messagebox.showwarning(APP_TITLE, msg + "\n\nBaşarısız olanlar:\n" + "\n".join(errors[:10]))
        else:
            messagebox.showinfo(APP_TITLE, msg + " Puanını görmek için tekrar analiz edebilirsin.")


def main():
    App().mainloop()
