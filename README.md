# GitHub Profil Analiz

GitHub profilini ve repolarını tarayıp eksikleri bulan, istersen tek tıkla düzelten Windows programı.

## İndir

En güncel `GitHubProfilAnaliz.exe` dosyasını [Releases](https://github.com/MustafaCanDere/github-profil-analiz/releases/latest) sayfasından indirebilirsin.

## Kullanım

1. `GitHubProfilAnaliz.exe` dosyasını çift tıklayarak aç (kurulum gerekmez).
2. GitHub kullanıcı adını yaz, **Analiz Et**'e bas.
3. Sorunlar profil ve repo bazında, önem derecesiyle listelenir; üstte 100 üzerinden puan görünür.
4. Düzeltme yapmak için kendi hesabına ait bir token gir (aşağıda), tekrar analiz et, bir soruyu seç ve **Seçileni Düzelt**'e bas (ya da çift tıkla).
5. **Raporu Kaydet** ile sonucu Markdown dosyası olarak saklayabilirsin.

## Token

Token yalnızca düzeltme yapmak ve API limitini (saatte 60 → 5000) artırmak için gerekir. Programdaki "Token nasıl alınır?" bağlantısı, `repo` ve `user` izinleri seçili şekilde GitHub token sayfasını açar. Token hiçbir yere kaydedilmez, yalnızca GitHub API'ye gönderilir.

## Kontroller

| Profil | Repo |
|---|---|
| Görünen ad, biyografi, konum, web sitesi, X/Twitter | Açıklama (description) |
| Profil README reposu (`kullanici/kullanici`) | Konu etiketleri (topics) |
| Herkese açık repo ve takipçi sayısı | Lisans |
| | README |
| | Boş repo, 1 yıldan uzun güncellenmemiş repo |
| | GitHub Pages bağlantısı, dil |

## Otomatik düzeltmeler (token ile)

Profil alanlarını doldurma, profil README reposu oluşturma, repo açıklaması ve etiket ekleme, MIT lisansı ekleme, şablondan README oluşturma (göndermeden önce düzenlenebilir), eski repoyu arşivleme, Pages adresini website olarak ekleme. Her işlem öncesinde onay ister.

## 🤖 AI ile otomatik düzeltme

AI olarak **Claude** veya **Gemini** seçip API anahtarını gir ve **AI ile Tümünü Düzelt**'e bas. Program her reponun kodunu ve dosyalarını okur, AI da eksik olan açıklamayı, etiketleri ve README'yi, profil için de biyografiyi ve profil README'sini yazar (Türkçe veya İngilizce). Eksik lisanslar için MIT lisansı eklenir.

Öneriler önce bir önizleme penceresinde gösterilir: metinleri düzenleyebilir, istemediklerinin işaretini kaldırabilirsin. **Seçilenleri GitHub'a Uygula**'ya basana kadar hiçbir şey değişmez.

| | Claude | Gemini |
|---|---|---|
| Anahtar | [platform.claude.com](https://platform.claude.com/settings/keys) | [aistudio.google.com](https://aistudio.google.com/apikey) |
| Model | `claude-opus-5-5` | `gemini-3.8-flash` (listeden değiştirilebilir) |
| Ortam değişkeni | `ANTHROPIC_API_KEY` | `GEMINI_API_KEY` |

Anahtarlar hiçbir yere kaydedilmez. Ortam değişkeni tanımlıysa kutu otomatik dolar.

## Kaynaktan derleme

Analiz kısmı yalnızca Python standart kütüphanesini kullanır; Claude seçeneği için `pip install -r requirements.txt` gerekir; Gemini ek paket istemez. Windows'ta `build.bat` çalıştır ya da kodu bir GitHub reposuna yükle: `.github/workflows/build.yml` exe'yi otomatik derler. Konsolda rapor için: `python main.py --cli KULLANICI [TOKEN]`.
