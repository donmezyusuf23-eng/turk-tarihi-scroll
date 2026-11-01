# Bozkırdan Cumhuriyete

Türk tarihini beş kavram üzerinden anlatan, scroll ile sürülen sinematik tek sayfa site.

Scroll ettikçe tam ekran fotoğraflar yavaşça yakınlaşıp kayar (Ken Burns etkisi), arka
planın ışığı bozkırın çelik mavisinden Osmanlı'nın kehribarına, oradan Cumhuriyet'in şafak
mavisine geçer. Metinler bu karelerin üzerinde sabitlenir.

**Perdeler:** Göç → Töre → Yerleşme → Kubbe → Kalem → Değişim → Egemenlik → 1923

---

## Nasıl çalışır

Site tek bir statik klasördür: `index.html` + `frames/`. Çerçeve yok, derleyici yok,
çalışma zamanı bağımlılığı yok. Herhangi bir statik sunucu olduğu gibi servis eder.

Kare üretimi iki katmanlıdır:

| Katman | Dosya | Ne yapar |
| --- | --- | --- |
| İçerik | `scrollcraft.json` | Bölümler, metinler, tipografi, palet, scroll temposu |
| Görüntü | `tools/frames_from_photos.py` | Fotoğraftan 180 kare: Ken Burns + ışık derecelendirmesi |
| Kalibrasyon | `tools/calibrate.py` | Karelerin beyaz yazıyı taşıdığını ölçerek garanti eder |

`dist/` ve `frames/` üretilebilir çıktılardır; depoda tutulmaz.

---

## Kurulum

Gereksinimler: **Python 3.10+** (`numpy`, `Pillow`), **Node.js 18+**.

```bash
pip install numpy pillow

# 1. Kareleri üret (desktop + mobil)
python tools/frames_from_photos.py \
  --photos "bozkir=photos/bozkir.jpg,osmanli=photos/osmanli.jpg,cumhuriyet=photos/cumhuriyet.jpg" \
  --out frames --count 180 --width 1920 --height 1080

python tools/frames_from_photos.py \
  --photos "bozkir=photos/bozkir.jpg,osmanli=photos/osmanli.jpg,cumhuriyet=photos/cumhuriyet.jpg" \
  --out frames-mobile --count 180 --width 900 --height 1600 --quality 80

# 2. Siteyi derle
node tools/build.mjs
```

Ardından `SITEYI_AC.bat` dosyasına çift tıkla, ya da:

```bash
node tools/serve.mjs --dir dist --port 4321
```

`dist/index.html` dosyasını **doğrudan çift tıklayarak açma** — tarayıcı `file://` kipinde
karelerin yüklenmesini engeller ve arka plan siyah kalır. HTTP üzerinden açılmalı.

---

## Doğrulama

Bu tür sayfaların karakteristik hatası sessizdir: eksik bir kare siyah tuval çizer,
hiçbir hata fırlatmaz, konsola bir şey yazmaz. "Derleme 0 döndü" sitenin çalıştığının
kanıtı değildir. Bu yüzden ölçüm yapılır:

```bash
python tools/calibrate.py 7.0     # perde başına koyulaştırma katsayısı
node tools/verify.mjs --dir dist --samples 30
```

`verify` siteyi başsız tarayıcıda açar, kaydırır ve okuyucunun **gerçekten gördüğü**
pikselleri ölçer:

- tuval gerçekten çiziyor mu (404 karenin ürettiği siyah dikdörtgen değil)
- arka plan kaydırmayla ilerliyor mu (tek karede donmuş bir scrub, ekstra adımlı bir
  durağan görüntüdür)
- **her metin satırı, arkasındaki piksellere karşı 4.5:1 kontrastı geçiyor mu**
- hiçbir istek 404 dönmüyor mu, sayfa yana kaymıyor mu

## Neden kalibrasyon gerekli

Ham fotoğraflar beyaz yazıyı taşımıyor. Ölçüm:

| Fotoğraf | Ortalama parlaklık | En kötü beyaz kontrast |
| --- | --- | --- |
| Bozkır (Kazakistan, gündüz) | 90.7 | **2.42:1** |
| Süleymaniye (alacakaranlık) | 155.4 | **1.00:1** |
| Boğaz (gün batımı) | 39.4 | 4.45:1 |

Gereken 4.5:1. Bu yüzden her perdeye ton harmanlama, luma sıkıştırma, dikey gradyan ve
vinyet giydirilir. `calibrate.py` bu derecelendirmenin üstüne hedef kontrastı tutan
gama katsayısını **ölçerek** bulur; sezgisel ayar yetmez (elle 3.48:1'de kalıyordu,
kalibrasyon 5.31:1'e çıkardı).

Fotoğrafı değiştirirsen `calibrate.py` çalıştır ve çıkan `darken` değerlerini
`tools/frames_from_photos.py` içindeki `ACTS` sözlüğüne yaz.

---

## Proje yapısı

```
scrollcraft.json          Site içeriği: bölümler, metinler, tipografi, palet
photos/                   Kaynak fotoğraflar (bkz. PHOTO_CREDITS.md)
tools/
  frames_from_photos.py   Fotoğraf → kare (Ken Burns, ışık hikâyesi, geçişler)
  frames_from_video.py    Video → kare (OpenCV; ffmpeg gerektirmez)
  calibrate.py            Kontrast ölçümüyle koyulaştırma katsayısı
  render_frames.py        Tamamen prosedürel arka plan (fotoğrafsız alternatif)
  build.mjs, serve.mjs, verify.mjs   ScrollCraft motorundan
SITEYI_AC.bat             Windows başlatıcı: sunucuyu açar, tarayıcıyı başlatır
```

---

## Teknik notlar

**Neden OpenCV, neden ffmpeg değil?** Bu makinede ffmpeg 2013 sürümüydü; `scale=-2`
ve mjpeg kodlayıcı çalışmıyordu. `frames_from_video.py` kare çıkarmayı OpenCV ile yapar,
dikey videoyu doğru kırpar ve ffmpeg'e hiç ihtiyaç duymaz.

**Ken Burns nasıl bağlanıyor?** Her perde scroll boyunca eşit pay alır. Perde içinde
zoom `1.06 → 1.16` arası doğrusal, pan yönü perde indeksine göre değişir (çift perdeler
sağa, tek perdeler sola). Perde sınırlarında payın %30'u kadar çapraz geçiş penceresi
vardır; kareler önce derecelendirilip sonra karıştırılır, böylece geçiş sırasında da
kontrast korunur.

**Neden 180 kare?** 13.500px scroll yolu için yaklaşık 75px'te bir kare. Daha azı
scrub'ı basamaklı gösterir, daha fazlası sayfa ağırlığını artırırır.

---

## Lisans

Kod MIT — bkz. [LICENSE](LICENSE).

Fotoğraflar CC lisanslıdır ve **atıf gerektirir** — bkz. [PHOTO_CREDITS.md](PHOTO_CREDITS.md).
Siteyi yayınlarsan atıfları sayfaya da eklemelisin.

ScrollCraft motoru MIT lisanslıdır — bkz. [CREDITS.md](CREDITS.md).
