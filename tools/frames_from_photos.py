"""
Fotograftan scroll sitesi kareleri: Ken Burns (yakinlasma + kayma) + isik hikayesi.

Neden bu betik var
------------------
Ham fotograflar beyaz yaziyi tasimiyor: bozkir gunduz cekilmis (luma ~103, beyaz
kontrast 2.1:1), Suleymaniye alacakaranlik (155, 1:1). verify.mjs yazinin arkasindaki
GERCEK pikseli olcuyor, yani kareyi oldugu gibi kullanmak imkansiz.

Yaklasim: fotografi koru, uzerine perde sicakliginde bir "isik hikayesi" giydir.
  - ton harmanlama  : kareyi perdenin paletine cek (cok uslu degil, %55)
  - luma sikistirma : parlak yerleri tepeden bas (boya gibi, dokuyu oldurmeden)
  - gradient + vinyet: yazinin oturdugu bolgeyi koyulastir
  - film grain
Boylece fotografin dokusu ve kompozisyonu kalir, kontrast 4.5:1'in uzerine cikar.

Kareler arasi gecis
-------------------
Her perde bir fotografla temsil edilir. Iki perde arasinda frameler capraz
gecisle karisir; bu yuzden scroll boyunca sahne degisimi video gibi akar.
Ken Burns her perde icin ayri ayri hesaplanir: panorama genislesir ya da
detaya yakinlasir — hep ayni yonde, hep yavas.
"""

import argparse
import math
import os

import numpy as np
from PIL import Image

# ------------------------------------------------------------------ palet

# Her perdenin isik hikayesi. stops: tepeden ufka dogru tonlar (0-1-0..1 renk).
ACTS = {
    "bozkir": {
        "tint": (0.72, 0.80, 0.95),      # serin, celik maviye cek
        "shadow": (7, 12, 19),
        "highlight": (124, 142, 162),
        "lift": 0.055,
        "contrast": 0.58,
        "vignette": 0.34,
        "grad_top": 0.42,
        "grad_bot": 0.22,
        "grain": 3.2,
        "darken": 1.20,
    },
    "osmanli": {
        "tint": (1.06, 0.90, 0.80),      # sicak, yanan kehribar
        "shadow": (8, 5, 5),
        "highlight": (150, 88, 50),
        "lift": 0.040,
        "contrast": 0.64,
        "vignette": 0.40,
        "grad_top": 0.46,
        "grad_bot": 0.26,
        "grain": 3.6,
        "darken": 1.40,
    },
    "cumhuriyet": {
        "tint": (0.84, 0.90, 1.02),      # gece mavisi, safak kenari
        "shadow": (5, 7, 12),
        "highlight": (132, 132, 148),
        "lift": 0.045,
        "contrast": 0.60,
        "vignette": 0.36,
        "grad_top": 0.44,
        "grad_bot": 0.20,
        "grain": 3.0,
        "darken": 1.00,
    },
}


def smoothstep(t):
    t = np.clip(np.asarray(t, dtype=np.float32), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix_act(a, b, t):
    """Iki perdenin isik ayarlarini karistir."""
    out = {}
    for k in ("tint", "shadow", "highlight"):
        out[k] = tuple(a[k][i] + (b[k][i] - a[k][i]) * t for i in range(3))
    for k in ("lift", "contrast", "vignette", "grad_top", "grad_bot", "grain", "darken"):
        out[k] = a[k] + (b[k] - a[k]) * t
    return out


# ------------------------------------------------------------------ goruntu


def cover(img, w, h, zoom=1.0, pan_x=0.0, pan_y=0.0):
    """Ken Burns: merkeze gore zoom, sonra pan. En-boy orani korunur."""
    iw, ih = img.size
    scale = max(w / iw, h / ih) * zoom
    nw, nh = int(round(iw * scale)), int(round(ih * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)

    # pan -1..1 arasi, kalan bosluk uzerinden
    max_dx = max(0, nw - w)
    max_dy = max(0, nh - h)
    x0 = int(max_dx * (0.5 + pan_x * 0.5))
    y0 = int(max_dy * (0.5 + pan_y * 0.5))
    x0 = max(0, min(nw - w, x0))
    y0 = max(0, min(nh - h, y0))
    return resized.crop((x0, y0, x0 + w, y0 + h))


def grade(arr, act, darken=1.0):
    """Fotografi perdenin isigina boya ve yazinin bolgesini koyulastir."""
    a = arr.astype(np.float32) / 255.0
    h, w, _ = a.shape

    # 1) tint: kanal bazli carpan
    a = a * np.array(act["tint"], dtype=np.float32)[None, None, :]

    # 2) luma sikistirma: parlak yerleri highlight'a dogru bas
    lo = np.array(act["shadow"], dtype=np.float32) / 255.0
    hi = np.array(act["highlight"], dtype=np.float32) / 255.0
    a = np.clip(a, 0.0, 1.0)
    # yumusak S egrisi: golgeyi lo'ya, isigi hi'ya oturt
    a = lo[None, None, :] + a * (hi - lo)[None, None, :]

    # 3) kontrast: orta noktaya dogru sikistir (isik/ton kaybi olmadan)
    c = act["contrast"]
    a = 0.5 + (a - 0.5) * c + act["lift"]

    # 4) dikey gradient: tepe koyu (baslik bolgesi), alt daha az
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    top = act["grad_top"] * (1.0 - smoothstep(y / 0.62))  # (h,1,1)
    bot = act["grad_bot"] * smoothstep((y - 0.62) / 0.38)
    a = a * (1.0 - top) * (1.0 - bot)

    # 4b) hedef kontrasta kilitlenmis koyulastirma (gamma)
    if darken != 1.0:
        a = np.power(np.clip(a, 0.0, 1.0), darken)

    # 5) vinyet
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2) / (w / 2)
    ny = (yy - h / 2) / (h / 2)
    v = np.clip(1.0 - act["vignette"] * (nx ** 2 * 0.55 + ny ** 2 * 0.85), 0.0, 1.0)
    a = a * v[:, :, None]

    return a


def add_grain(a, rng, amount):
    if amount <= 0:
        return a
    h, w, _ = a.shape
    g = rng.normal(0, amount / 255.0, (h, w, 1)).astype(np.float32)
    return a + g


# ------------------------------------------------------------------ ana


def build(photos, out_dir, count, width, height, quality, seed=0):
    """photos: [(act_adi, Image), ...] sirali perde listesi."""
    n_acts = len(photos)
    if n_acts == 0:
        raise SystemExit("en az bir fotograf gerekli")
    if n_acts == 1:
        raise SystemExit("gecis icin en az iki fotograf gerekli")

    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)

    # Her perde scroll boyunca esit pay alir; aralarinda ortusen gecis penceresi.
    # perde i merkezi: i / (n-1)
    span = 1.0 / max(1, n_acts - 1)
    blend = span * 0.30          # gecis penceresi: payin %30'u

    for i in range(count):
        p = i / max(1, count - 1)

        # hangi perdeye daha yakin
        k = min(n_acts - 1, int(round(p / span)))
        local = (p - k * span) / span
        local = max(-1.0, min(1.0, local))

        # Ken Burns: perde basindan sonuna yavas yakinlasma + yatay kayma
        kb = (k + max(0.0, local)) if k < n_acts - 1 else k + (0.5 + 0.5 * local)
        prog = min(1.0, max(0.0, (local + 1.0) / 2.0))

        def kb_params(idx, pr):
            zoom = 1.06 + 0.10 * pr
            # alternatif yon: cift perdeler saga, tek perdeler sola kayar
            direction = 1.0 if idx % 2 == 0 else -1.0
            pan_x = direction * (-0.10 + 0.20 * pr)
            pan_y = -0.04 + 0.08 * pr
            return zoom, pan_x, pan_y

        z_k, px_k, py_k = kb_params(k, prog)
        frame_k = grade(np.asarray(
            cover(photos[k][1], width, height, z_k, px_k, py_k), dtype=np.uint8
        ), ACTS[photos[k][0]], ACTS[photos[k][0]]["darken"])

        # gecis penceresindeysek komsu perdeyle karis
        act = ACTS[photos[k][0]]
        frame = frame_k
        if 0 < k < n_acts - 1:
            pass
        # soldaki komsuya yakin mi
        if k > 0 and abs(p - k * span) < blend:
            t = smoothstep(0.5 + (p - k * span) / (2 * blend))
            z_p, px_p, py_p = kb_params(k - 1, 1.0)
            frame_p = grade(np.asarray(
                cover(photos[k - 1][1], width, height, z_p, px_p, py_p), dtype=np.uint8
            ), ACTS[photos[k - 1][0]], ACTS[photos[k - 1][0]]["darken"])
            frame = frame_p * (1 - t) + frame * t
            act = mix_act(ACTS[photos[k - 1][0]], act, t)
        # sagdaki komsuya yakin mi
        elif k < n_acts - 1 and abs((k + 1) * span - p) < blend:
            t = smoothstep(0.5 - ((k + 1) * span - p) / (2 * blend))
            z_n, px_n, py_n = kb_params(k + 1, 0.0)
            frame_n = grade(np.asarray(
                cover(photos[k + 1][1], width, height, z_n, px_n, py_n), dtype=np.uint8
            ), ACTS[photos[k + 1][0]], ACTS[photos[k + 1][0]]["darken"])
            frame = frame * (1 - t) + frame_n * t
            act = mix_act(act, ACTS[photos[k + 1][0]], t)

        frame = add_grain(frame, rng, act["grain"])
        out = np.clip(frame * 255.0, 0, 255).astype(np.uint8)
        Image.fromarray(out, "RGB").save(
            os.path.join(out_dir, f"frame_{i:04d}.jpg"),
            quality=quality, subsampling=2, optimize=True,
        )
        if i % 20 == 0:
            print(f"  {i}/{count}", flush=True)

    print(f"bitti: {count} kare -> {out_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", required=True,
                    help="virgulle ayrilmis: perde_adi=path (or. bozkir=steppe.jpg)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=180)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--quality", type=int, default=84)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    photos = []
    for spec in args.photos.split(","):
        name, _, path = spec.partition("=")
        name, path = name.strip(), path.strip()
        if name not in ACTS:
            raise SystemExit(f"bilinmeyen perde '{name}' (secenekler: {', '.join(ACTS)})")
        if not os.path.isfile(path):
            raise SystemExit(f"fotograf yok: {path}")
        photos.append((name, Image.open(path).convert("RGB")))
        print(f"  perde {name:12s} <- {path}  {Image.open(path).size}")

    build(photos, args.out, args.count, args.width, args.height, args.quality, args.seed)


if __name__ == "__main__":
    main()
