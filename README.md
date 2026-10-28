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

## Kaynaktan derleme

Yalnızca Python standart kütüphanesi kullanılır. Windows'ta `build.bat` çalıştır ya da kodu bir GitHub reposuna yükle: `.github/workflows/build.yml` exe'yi otomatik derler. Konsolda rapor için: `python main.py --cli KULLANICI [TOKEN]`.
