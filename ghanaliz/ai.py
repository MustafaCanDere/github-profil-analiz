"""Claude veya Gemini ile eksik açıklama, etiket, README ve biyografi üretimi."""

import json
import re
import ssl
import urllib.error
import urllib.request

MODEL = "claude-opus-5-5"
GEMINI_MODELS = ("gemini-3.8-flash", "gemini-flash-latest", "gemini-4-argon")
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Bağlama eklenecek dosyalar: önce bunlar, sonra kaynak dosyalar
KEY_FILES = ("package.json", "requirements.txt", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod",
             "pom.xml", "build.gradle", "composer.json", "Gemfile", "CMakeLists.txt", "Makefile",
             "Dockerfile", "index.html", "main.py", "app.py")
SOURCE_EXT = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".cs", ".cpp", ".c", ".h", ".go",
              ".rs", ".php", ".rb", ".swift", ".dart", ".lua", ".html", ".css", ".sh", ".bat", ".ps1")
SKIP_DIRS = ("node_modules/", "vendor/", "dist/", "build/", ".git/", "venv/", ".venv/", "__pycache__/")
MAX_CONTEXT_CHARS = 40000

REPO_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "topics": {"type": "array", "items": {"type": "string"}},
        "readme": {"type": "string"},
    },
    "required": ["description", "topics", "readme"],
    "additionalProperties": False,
}

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "bio": {"type": "string"},
        "profile_readme": {"type": "string"},
    },
    "required": ["bio", "profile_readme"],
    "additionalProperties": False,
}

SYSTEM = (
    "Sen GitHub profillerini düzenleyen bir yardımcısın. Sana bir reponun dosya listesi ve "
    "dosya içerikleri verilecek. Yalnızca gördüğün koda dayan; kodda olmayan özellik, "
    "kurulum adımı veya teknoloji uydurma. Emin olmadığın kısımları kısa ve genel tut."
)


class AIError(Exception):
    pass


class Assistant:
    """Ortak istem mantığı; alt sınıflar _ask ile modele bağlanır."""

    def __init__(self, lang="Türkçe"):
        self.lang = lang

    def _ask(self, prompt, schema):
        raise NotImplementedError


    # ---- bağlam toplama ----
    @staticmethod
    def repo_context(gh, owner, repo):
        paths = gh.get_tree(owner, repo["name"], repo.get("default_branch") or "main")
        paths = [p for p in paths if not any(d in p for d in SKIP_DIRS)]
        parts = [f"Repo adı: {repo['name']}",
                 f"Ana dil: {repo.get('language') or 'bilinmiyor'}",
                 f"Mevcut açıklama: {repo.get('description') or '(yok)'}",
                 f"Mevcut etiketler: {', '.join(repo.get('topics') or []) or '(yok)'}",
                 "", "Dosya listesi:", "\n".join(paths[:300])]
        size = sum(len(p) for p in parts)
        lower = {p.lower(): p for p in paths}
        chosen = [lower[k] for k in (f.lower() for f in KEY_FILES) if k in lower]
        chosen += [p for p in paths if p not in chosen and p.lower().startswith("readme")]
        chosen += sorted((p for p in paths if p.endswith(SOURCE_EXT) and p not in chosen),
                         key=lambda p: (p.count("/"), len(p)))
        for path in chosen[:25]:
            if size > MAX_CONTEXT_CHARS:
                break
            text = gh.get_text(owner, repo["name"], path)
            if text:
                block = f"\n--- {path} ---\n{text}"
                parts.append(block)
                size += len(block)
        return "\n".join(parts)

    # ---- üretim ----
    def repo_fixes(self, gh, owner, repo):
        ctx = self.repo_context(gh, owner, repo)
        prompt = (
            f"{ctx}\n\n"
            "Bu repo için şunları üret:\n"
            f"- description: {self.lang} dilinde, en fazla 120 karakterlik tek cümlelik açıklama.\n"
            "- topics: 3-8 adet GitHub konu etiketi (küçük harf, yalnızca a-z, 0-9 ve tire).\n"
            f"- readme: {self.lang} dilinde Markdown README.md. Başlık, kısa tanıtım, özellikler, "
            "kurulum/çalıştırma ve kullanılan teknolojiler bölümleri olsun. Kurulum komutlarını "
            f"yalnızca dosyalardan çıkarabiliyorsan yaz. Klonlama adresi: {repo.get('clone_url', '')}"
        )
        out = self._ask(prompt, REPO_SCHEMA)
        out["topics"] = clean_topics(out.get("topics", []))
        out["description"] = out.get("description", "").strip()[:350]
        return out

    def profile_fixes(self, user, repos):
        lines = [f"- {r['name']} ({r.get('language') or '?'}, {r.get('stargazers_count', 0)}★): "
                 f"{r.get('description') or 'açıklama yok'}" for r in repos[:40]]
        prompt = (
            f"GitHub kullanıcısı: {user['login']}\n"
            f"Görünen ad: {user.get('name') or '(yok)'}\n"
            f"Mevcut bio: {user.get('bio') or '(yok)'}\n"
            f"Konum: {user.get('location') or '(yok)'}\n"
            f"Repoları:\n" + "\n".join(lines) + "\n\n"
            "Bu bilgilere göre şunları üret:\n"
            f"- bio: {self.lang} dilinde, en fazla 150 karakter, repolara bakarak ilgi alanlarını anlatan biyografi.\n"
            f"- profile_readme: {self.lang} dilinde profil README.md (Markdown). Kısa tanıtım, öne çıkan "
            "projeler (repo bağlantılarıyla), kullandığı teknolojiler ve iletişim bölümü. Kullanıcının "
            "repolarında görünmeyen bilgileri uydurma."
        )
        out = self._ask(prompt, PROFILE_SCHEMA)
        out["bio"] = out.get("bio", "").strip()[:160]
        return out


def clean_topics(topics):
    out = [re.sub(r"[^a-z0-9-]", "-", t.strip().lower()).strip("-")[:50] for t in topics]
    return [t for t in dict.fromkeys(out) if t][:20]


class ClaudeAssistant(Assistant):
    def __init__(self, api_key, lang="Türkçe"):
        super().__init__(lang)
        import anthropic  # yalnızca Claude seçilince yükle
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key.strip() or None)

    def _ask(self, prompt, schema):
        anthropic = self.anthropic
        try:
            resp = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM,
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError:
            raise AIError("Claude API anahtarı geçersiz.") from None
        except anthropic.PermissionDeniedError:
            raise AIError("Bu API anahtarının Claude kullanma izni yok.") from None
        except anthropic.RateLimitError:
            raise AIError("Claude API istek limiti doldu, biraz sonra tekrar dene.") from None
        except anthropic.APIStatusError as e:
            raise AIError(f"Claude API hatası ({e.status_code}): {e.message}") from None
        except anthropic.APIConnectionError:
            raise AIError("Claude API'ye bağlanılamadı. İnternet bağlantını kontrol et.") from None
        if resp.stop_reason == "refusal":
            raise AIError("Claude bu isteği yanıtlamayı reddetti.")
        if resp.stop_reason == "max_tokens":
            raise AIError("Yanıt yarıda kesildi.")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise AIError("Claude geçersiz bir yanıt döndürdü.") from None


class GeminiAssistant(Assistant):
    def __init__(self, api_key, lang="Türkçe", model=GEMINI_MODELS[0]):
        super().__init__(lang)
        self.key = api_key.strip()
        self.model = model.strip() or GEMINI_MODELS[0]
        self.url = GEMINI_API.format(model=self.model)
        self.ctx = ssl.create_default_context()

    def _post(self, body):
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-goog-api-key", self.key)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read()).get("error", {})
            except Exception:
                err = {}
            msg = err.get("message", e.reason)
            if e.code in (400, 401, 403) and "API key" in str(msg):
                raise AIError("Gemini API anahtarı geçersiz.") from None
            if e.code == 429:
                raise AIError("Gemini API istek limiti doldu, biraz sonra tekrar dene.") from None
            if e.code == 404:
                raise AIError(f"Gemini modeli bulunamadı: {self.model}") from None
            raise AIError(f"Gemini API hatası ({e.code}): {msg}") from None
        except urllib.error.URLError as e:
            raise AIError(f"Gemini API'ye bağlanılamadı: {e.reason}") from None

    def _ask(self, prompt, schema):
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema},
        }
        try:
            data = self._post(body)
        except AIError as e:
            if "schema" not in str(e).lower():
                raise
            # Şemayı desteklemeyen modeller için: şemayı isteme yazıp yalnızca JSON iste
            del body["generationConfig"]["responseJsonSchema"]
            body["contents"][0]["parts"][0]["text"] += "\n\nYalnızca şu JSON şemasına uyan bir nesne döndür:\n" + json.dumps(schema)
            data = self._post(body)
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise AIError(f"Gemini yanıt vermedi{f' ({reason})' if reason else ''}.")
        if cands[0].get("finishReason") == "MAX_TOKENS":
            raise AIError("Yanıt yarıda kesildi.")
        text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []) if not p.get("thought"))
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            out = json.loads(text)
        except json.JSONDecodeError:
            raise AIError("Gemini geçersiz bir yanıt döndürdü.") from None
        missing = [k for k in schema["required"] if k not in out]
        if missing:
            raise AIError(f"Gemini yanıtında eksik alan: {', '.join(missing)}")
        return out
