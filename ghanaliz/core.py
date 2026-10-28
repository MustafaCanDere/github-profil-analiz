"""GitHub profil ve repo analiz motoru (yalnızca standart kütüphane)."""

import base64
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

API = "https://api.github.com"
STALE_DAYS = 365

# Önem seviyeleri: puan hesabında kullanılır
HIGH, MEDIUM, LOW = "Yüksek", "Orta", "Düşük"
WEIGHTS = {HIGH: 10, MEDIUM: 5, LOW: 2}


class GitHubError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


@dataclass
class Issue:
    target: str          # "Profil" veya repo adı
    severity: str
    title: str
    detail: str
    fix: str = ""        # düzeltme kodu (ör. "description", "topics"); boşsa otomatik düzeltme yok


@dataclass
class Report:
    user: dict = field(default_factory=dict)
    repos: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    score: int = 100

    def by_target(self):
        out = {}
        for i in self.issues:
            out.setdefault(i.target, []).append(i)
        return out


class GitHubClient:
    def __init__(self, token=""):
        self.token = token.strip()
        self.ctx = ssl.create_default_context()
        self.remaining = None

    def request(self, method, path, body=None, accept="application/vnd.github+json"):
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", accept)
        req.add_header("User-Agent", "GitHub-Profil-Analiz")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                self.remaining = r.headers.get("X-RateLimit-Remaining")
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("message", e.reason)
            except Exception:
                msg = e.reason
            if e.code == 403 and "rate limit" in str(msg).lower():
                msg = "API istek limiti doldu. Token girerseniz limit saatte 5000 olur."
            raise GitHubError(e.code, msg) from None
        except urllib.error.URLError as e:
            raise GitHubError(0, f"Bağlantı hatası: {e.reason}") from None

    def get(self, path):
        return self.request("GET", path)

    def exists(self, path):
        try:
            self.get(path)
            return True
        except GitHubError as e:
            if e.status in (404, 409):  # 409: boş repo
                return False
            raise

    def paginate(self, path):
        items, page = [], 1
        sep = "&" if "?" in path else "?"
        while True:
            chunk = self.get(f"{path}{sep}per_page=100&page={page}")
            items.extend(chunk)
            if len(chunk) < 100:
                return items
            page += 1

    # ---- kimlik ----
    def me(self):
        return self.get("/user") if self.token else None

    # ---- düzeltme işlemleri ----
    def update_repo(self, owner, repo, **fields):
        return self.request("PATCH", f"/repos/{owner}/{repo}", fields)

    def set_topics(self, owner, repo, topics):
        return self.request("PUT", f"/repos/{owner}/{repo}/topics", {"names": topics})

    def put_file(self, owner, repo, path, content, message):
        body = {"message": message, "content": base64.b64encode(content.encode()).decode()}
        return self.request("PUT", f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}", body)

    def update_profile(self, **fields):
        return self.request("PATCH", "/user", fields)

    def create_repo(self, name, description="", auto_init=False):
        return self.request("POST", "/user/repos",
                            {"name": name, "description": description, "auto_init": auto_init})

    # ---- okuma yardımcıları (AI bağlamı için) ----
    def get_tree(self, owner, repo, branch):
        """Repodaki dosya yollarını döndürür (boş repo için boş liste)."""
        try:
            tree = self.get(f"/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(branch)}?recursive=1")
        except GitHubError as e:
            if e.status in (404, 409):
                return []
            raise
        return [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]

    def get_text(self, owner, repo, path, limit=6000):
        """Bir dosyanın metnini döndürür; bulunamazsa ya da ikiliyse None."""
        try:
            f = self.get(f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}")
        except GitHubError as e:
            if e.status in (404, 409):
                return None
            raise
        if not isinstance(f, dict) or f.get("encoding") != "base64":
            return None
        try:
            return base64.b64decode(f["content"]).decode("utf-8")[:limit]
        except (UnicodeDecodeError, ValueError):
            return None


def _days_since(iso):
    if not iso:
        return None
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def analyze(client, username, include_forks=False, progress=None):
    """Kullanıcıyı analiz eder ve Report döndürür. progress(mesaj, yüzde) çağrılır."""
    say = progress or (lambda m, p: None)
    rep = Report()
    say("Profil okunuyor...", 2)
    user = client.get(f"/users/{urllib.parse.quote(username)}")
    rep.user = user
    login = user["login"]
    add = rep.issues.append

    # ---- profil kontrolleri ----
    if not user.get("name"):
        add(Issue("Profil", MEDIUM, "Görünen ad yok", "Profilinde gerçek adın/takma adın görünmüyor.", "profile_name"))
    if not user.get("bio"):
        add(Issue("Profil", HIGH, "Biyografi (bio) boş", "Kısa bir tanıtım cümlesi ziyaretçilere kim olduğunu anlatır.", "profile_bio"))
    if not user.get("location"):
        add(Issue("Profil", LOW, "Konum belirtilmemiş", "Konum eklemek yerel fırsatlarda görünmeni sağlar.", "profile_location"))
    if not user.get("blog"):
        add(Issue("Profil", LOW, "Web sitesi / bağlantı yok", "Portföy, LinkedIn veya kişisel site bağlantısı ekleyebilirsin.", "profile_blog"))
    if not user.get("twitter_username"):
        add(Issue("Profil", LOW, "Sosyal hesap bağlantısı yok", "X/Twitter kullanıcı adı eklenebilir.", "profile_twitter"))
    if user.get("public_repos", 0) == 0:
        add(Issue("Profil", HIGH, "Hiç herkese açık repo yok", "Profilde gösterilecek bir proje bulunmuyor."))
    if user.get("followers", 0) == 0:
        add(Issue("Profil", LOW, "Takipçi yok", "Projelerini paylaşarak ve başkalarını takip ederek görünürlüğünü artırabilirsin."))

    say("Profil README kontrol ediliyor...", 6)
    if not client.exists(f"/repos/{login}/{login}"):
        add(Issue("Profil", HIGH, "Profil README reposu yok",
                  f"'{login}/{login}' adında bir repo oluşturup README.md eklersen profil sayfanın en üstünde görünür.",
                  "profile_readme"))
    elif not client.exists(f"/repos/{login}/{login}/readme"):
        add(Issue("Profil", HIGH, "Profil reposunda README yok",
                  f"'{login}/{login}' reposu var ama README.md içermiyor.", "profile_readme_file"))

    # ---- repolar ----
    say("Repolar listeleniyor...", 10)
    repos = client.paginate(f"/users/{login}/repos?type=owner&sort=pushed")
    if not include_forks:
        repos = [r for r in repos if not r.get("fork")]
    repos = [r for r in repos if r["name"].lower() != login.lower()]
    rep.repos = repos

    for n, r in enumerate(repos, 1):
        name = r["name"]
        say(f"İnceleniyor: {name} ({n}/{len(repos)})", 10 + int(85 * n / max(len(repos), 1)))
        if r.get("archived"):
            continue
        empty = r.get("size", 0) == 0
        if empty:
            add(Issue(name, HIGH, "Repo boş", "Repoda hiç dosya yok. İçerik ekle ya da sil/arşivle."))
        if not r.get("description"):
            add(Issue(name, HIGH, "Açıklama (description) yok", "Repo listesinde ne olduğu anlaşılmıyor.", "description"))
        if not r.get("topics"):
            add(Issue(name, MEDIUM, "Konu etiketi (topics) yok", "Etiketler reponun aramalarda bulunmasını sağlar.", "topics"))
        if not r.get("license"):
            add(Issue(name, MEDIUM, "Lisans yok", "Lisanssız kod yasal olarak başkaları tarafından kullanılamaz.",
                      "" if empty else "license"))
        if not empty and not client.exists(f"/repos/{login}/{name}/readme"):
            add(Issue(name, HIGH, "README yok", "Projenin ne yaptığını, nasıl kurulduğunu anlatan README.md eksik.", "readme"))
        days = _days_since(r.get("pushed_at"))
        if days is not None and days > STALE_DAYS:
            add(Issue(name, LOW, f"Uzun süredir güncellenmemiş ({days} gün)",
                      "Bakımı bitmiş projeleri arşivlemek profilini daha düzenli gösterir.", "archive"))
        if not r.get("homepage") and r.get("has_pages"):
            add(Issue(name, LOW, "GitHub Pages var ama ana sayfa bağlantısı yok",
                      "Repo ayarlarına Pages adresini 'Website' olarak ekle.", "homepage_pages"))
        if not r.get("language") and not empty:
            add(Issue(name, LOW, "Dil algılanamadı", "Repo yalnızca doküman/ikili dosya içeriyor olabilir."))

    penalty = sum(WEIGHTS[i.severity] for i in rep.issues)
    max_pen = 60 + 30 * max(len(repos), 1)
    rep.score = max(0, round(100 - 100 * penalty / max_pen))
    say("Analiz tamamlandı.", 100)
    return rep


# ---- şablonlar ----

def readme_template(repo):
    name = repo["name"]
    desc = repo.get("description") or "Proje açıklaması buraya."
    lang = repo.get("language") or ""
    return f"""# {name}

{desc}

## Özellikler

- ...

## Kurulum

```bash
git clone {repo.get('clone_url', '')}
cd {name}
```

## Kullanım

...

## Teknolojiler

{('- ' + lang) if lang else '- ...'}

## Lisans

Bu proje lisans dosyasında belirtilen koşullar altında dağıtılmaktadır.
"""


def profile_readme_template(user):
    login = user["login"]
    name = user.get("name") or login
    bio = user.get("bio") or "Yazılım geliştirmeyi seven biriyim."
    return f"""# Merhaba, ben {name} 👋

{bio}

## 🔭 Şu an üzerinde çalıştıklarım

- ...

## 🛠️ Kullandığım teknolojiler

- ...

## 📫 Bana ulaşın

- GitHub: [@{login}](https://github.com/{login})

![{login}'s GitHub stats](https://github-readme-stats.vercel.app/api?username={login}&show_icons=true)
"""


def mit_license(holder):
    year = datetime.now().year
    return f"""MIT License

Copyright (c) {year} {holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def suggest_topics(repo):
    """Repo adı ve dilinden basit etiket önerisi üretir."""
    out = []
    if repo.get("language"):
        out.append(repo["language"].lower().replace("+", "p").replace("#", "sharp").replace(" ", "-"))
    for part in repo["name"].lower().replace("_", "-").split("-"):
        if len(part) > 2 and part.isalnum() and part not in out:
            out.append(part)
    return out[:6]


def export_markdown(rep):
    u = rep.user
    lines = [f"# GitHub Profil Analizi: {u.get('login')}", "",
             f"**Puan:** {rep.score}/100  ",
             f"**İncelenen repo:** {len(rep.repos)}  ",
             f"**Bulunan sorun:** {len(rep.issues)}  ",
             f"**Tarih:** {datetime.now():%Y-%m-%d %H:%M}", ""]
    for target, issues in rep.by_target().items():
        lines.append(f"## {target}")
        for i in issues:
            lines.append(f"- **[{i.severity}] {i.title}** — {i.detail}")
        lines.append("")
    return "\n".join(lines)
