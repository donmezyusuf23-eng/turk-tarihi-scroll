"""
Turk tarihi scroll sitesi icin arka plan karelerini cizer.

Uc perde, tek bir isik hikayesi:
  I.  BOZKIR      safak oncesi mavi, alcak gunes, bozkir silueti, atli okcu
  II. OSMANLI     yanan ufuk, kubbe ve minare siluetleri, kararan gece
  III.CUMHURiYET  gece -> safak, bozkir geri doner, tek yildiz

Kontrast kurali: yazi karelerin UZERINDE durur ve verify.mjs gercek pikseli olcer.
Bu yuzden gokyuzu tepesi 8-bit luma ~75'in altinda tutulur; parlak isik sadece
ufukta ince bir bant ve kucuk bir gunes diski olarak kalir.
"""

import argparse
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---------------------------------------------------------------- renk yardimci


def hexc(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- paleti

# Her perde icin gokyuzu duraklari (tepeden ufka). Ufuk cizgisi "horizon_y"
# ile verilir; duraklar bu aralikta yayilir.
ACTS = {
    # perde I: safak oncesi bozkir, celik mavi, alcak soluk isik
    "bozkir": {
        "sky": ["#0F151C", "#182230", "#24323F", "#2C3945", "#33424E"],
        "glow": "#8FA6B2",
        "ground": ["#0D1117", "#080A0E"],
        "sun": {"color": "#E8DFC8", "y": 1.12, "radius": 0.075, "glow": 0.50},
    },
    # perde II: yanan alacakaranlik
    "osmanli": {
        "sky": ["#040506", "#140808", "#2E0B08", "#44140D", "#5A2216"],
        "glow": "#F0A04B",
        "ground": ["#060405", "#040304"],
        "sun": {"color": "#F6B25E", "y": 1.14, "radius": 0.085, "glow": 0.62},
    },
    # perde III: gece kirilan safak
    "cumhuriyet": {
        "sky": ["#03040A", "#060913", "#0C1322", "#121B2C", "#1F2C3C"],
        "glow": "#F2D28B",
        "ground": ["#070A0F", "#030509"],
        "sun": {"color": "#F2D28B", "y": 1.16, "radius": 0.080, "glow": 0.55},
    },
}


def mix_palette(a, b, t):
    """Iki perdenin gokyuzu duraklarini karistir."""
    out = {}
    out["sky"] = [tuple(lerp(hexc(x), hexc(y), t)) for x, y in zip(a["sky"], b["sky"])]
    out["ground"] = [tuple(lerp(hexc(x), hexc(y), t)) for x, y in zip(a["ground"], b["ground"])]
    out["glow"] = tuple(lerp(hexc(a["glow"]), hexc(b["glow"]), t))
    sa, sb = a["sun"], b["sun"]
    out["sun"] = {
        "color": tuple(lerp(hexc(sa["color"]), hexc(sb["color"]), t)),
        "y": lerp(sa["y"], sb["y"], t),
        "radius": lerp(sa["radius"], sb["radius"], t),
        "glow": lerp(sa["glow"], sb["glow"], t),
    }
    return out


# ---------------------------------------------------------------- gokyuzu


def sky_gradient(w, h, pal, horizon_y, glow_strength, glow_y):
    """Dikey gokyuzu gradyani + ufukta isik bandi. float32 (h, w, 3)."""
    stops = pal["sky"]
    n = len(stops)
    # dikey oran 0..1 gokyuzu icinde
    # Duraklar tepeden ufka yayilir; ufkun alti en alt renkte sabit kalir (zemin
    # sonra ustune yazar, ama tasan bir parlaklik kalmamali).
    ys = np.clip(np.arange(h, dtype=np.float32) / max(1.0, float(horizon_y)),
                 0.0, 1.0)[:, None]
    ys = np.repeat(ys, w, axis=1)

    img = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        vals = np.array([s[c] for s in stops], dtype=np.float32)
        pos = np.linspace(0.0, 1.0, n, dtype=np.float32)
        img[:, :, c] = np.interp(ys, pos, vals)

    # ufuk isigi: ince, yumusak bant (mutlak kare oraniyla olculur)
    if glow_strength > 0.001:
        y_abs = (np.arange(h, dtype=np.float32) / max(1.0, h))[:, None]
        band = np.exp(-((y_abs - glow_y) ** 2) / (2 * 0.030 ** 2)) * glow_strength
        gl = hexc(pal["glow"]) if isinstance(pal["glow"], str) else np.array(pal["glow"])
        img += band[:, :, None] * gl[None, None, :] * 0.34

    # yatay isik dagilimi: gunesin oldugu taraf biraz daha sicak
    return img


def radial_glow(w, h, cx, cy, radius_px, color, strength, falloff=2.0):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max(1.0, radius_px)
    g = np.clip(1.0 - d, 0, 1) ** falloff
    return (g[:, :, None] * np.array(color, dtype=np.float32)[None, None, :]) * strength


# ---------------------------------------------------------------- siluetler


def ridge_line(w, seed, base_y, amp, roughness, phase=0.0, detail=5):
    """Deterministik, yumusak bir siradağ cizgisi dondurur (x basina y)."""
    rng = np.random.default_rng(seed)
    xs = np.arange(w, dtype=np.float32)
    u = xs / max(1.0, w - 1)
    y = np.zeros_like(xs)
    wsum = 0.0
    for k in range(1, detail + 1):
        freq = k * (0.6 + roughness * 0.9)
        a = 1.0 / (k ** 1.25)
        y += a * amp * np.sin(u * math.pi * 2 * freq + phase + rng.uniform(0, 6.28))
        wsum += a
    y /= wsum
    return base_y - y


def draw_silhouette(w, h, polys, color, blur=0.0, ss=2):
    """Kati poligonlardan alfa maskesi uret, blurla, renkle dondur."""
    m = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)
    for poly in polys:
        pts = [(x * ss, y * ss) for x, y in poly]
        if len(pts) >= 3:
            d.polygon(pts, fill=255)
    if ss != 1:
        m = m.resize((w, h), Image.LANCZOS)
    if blur > 0:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    a = np.asarray(m, dtype=np.float32)[:, :, None] / 255.0
    return a * np.array(color, dtype=np.float32)[None, None, :], a


def over(img, layer):
    """Silueti uzerine yaz: koyu maske arkayi acik hale getirmez, ortalar."""
    if isinstance(layer, tuple):
        premul, a = layer
        return img * (1 - a) + premul
    return img + layer


def ellipse_poly(cx, cy, rx, ry, steps=26, rot=0.0):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        x = math.cos(t) * rx
        y = math.sin(t) * ry
        xr = x * math.cos(rot) - y * math.sin(rot)
        yr = x * math.sin(rot) + y * math.cos(rot)
        pts.append((cx + xr, cy + yr))
    return pts


def archer_polys(w, h, cx, base_y, scale):
    """Kucuk, mesafede bir atli okcu silueti. scale = figur yuksekligi (px)."""
    s = scale
    P = []

    def pt(dx, dy):
        return (cx + dx * s, base_y + dy * s)

    # govde
    P.append([pt(-0.52, -0.46), pt(-0.30, -0.62), pt(0.18, -0.60),
              pt(0.42, -0.50), pt(0.38, -0.30), pt(-0.05, -0.22),
              pt(-0.46, -0.26)])
    # boyun + bas
    P.append([pt(0.34, -0.52), pt(0.50, -0.94), pt(0.66, -0.88),
              pt(0.60, -0.66), pt(0.44, -0.46)])
    P.append(ellipse_poly(*pt(0.66, -0.97), 0.085 * s, 0.055 * s, 18, 0.35))
    # bacaklar
    for bx, ang in ((-0.34, 0.10), (-0.10, 0.2), (0.22, 0.16), (0.38, 0.1)):
        P.append([pt(bx, -0.28), pt(bx + 0.055, -0.28),
                  pt(bx + 0.055 + ang * 0.28, 0.0), pt(bx + ang * 0.28, 0.0)])
    # kuyruk
    P.append([pt(-0.50, -0.46), pt(-0.72, -0.20), pt(-0.64, -0.40)])
    # binici govdesi
    P.append([pt(-0.06, -0.60), pt(-0.02, -0.90), pt(0.14, -0.92),
              pt(0.18, -0.62)])
    # binici basi
    P.append(ellipse_poly(*pt(0.07, -0.99), 0.065 * s, 0.072 * s, 16))
    # yay: egri bir yay, ince poligon
    bow = []
    for i in range(7):
        t = i / 6.0
        bx = 0.20 + 0.10 * math.sin(t * math.pi)
        by = -1.02 + t * 0.55
        bow.append(pt(bx, by))
    for i in range(7):
        t = 1.0 - i / 6.0
        bx = 0.20 + 0.10 * math.sin(t * math.pi)
        by = -1.02 + t * 0.55
        bow.append(pt(bx - 0.035, by))
    P.append(bow)
    return P


def dome_cluster_polys(w, h, base_y, span_l, span_r, color_scale=1.0):
    """Kubbe + minare silueti kumesi. base_y = oturdugu taban."""
    P = []
    rng = np.random.default_rng(7)

    # ana yapi blogu
    def block(cx, top, half_w, dome_r, dome_h):
        P.append([(cx - half_w, base_y), (cx - half_w, top),
                  (cx + half_w, top), (cx + half_w, base_y)])
        # kubbe: yarim elips
        pts = []
        for i in range(1, 24):
            t = math.pi * i / 24
            pts.append((cx - dome_r * math.cos(t), top - dome_h * math.sin(t)))
        pts.append((cx + dome_r, top))
        pts.append((cx - dome_r, top))
        P.append(pts)
        # alem (tepede ince cizgi)
        P.append([(cx - half_w * 0.03, top - dome_h), (cx + half_w * 0.03, top - dome_h),
                  (cx + half_w * 0.03, top - dome_h - dome_h * 0.28),
                  (cx - half_w * 0.03, top - dome_h - dome_h * 0.28)])

    def minaret(cx, top, half_w):
        P.append([(cx - half_w, base_y), (cx - half_w, top),
                  (cx + half_w, top), (cx + half_w, base_y)])
        # konik kurek
        P.append([(cx - half_w * 1.7, top), (cx + half_w * 1.7, top),
                  (cx, top - half_w * 5.2)])
        # alem
        P.append([(cx - half_w * 0.16, top - half_w * 5.2), (cx + half_w * 0.16, top - half_w * 5.2),
                  (cx + half_w * 0.16, top - half_w * 7.4), (cx - half_w * 0.16, top - half_w * 7.4)])

    U = w  # birim = genislik
    mid = (span_l + span_r) / 2
    width = span_r - span_l
    H = h

    # arkadaki alcalmis yapilar
    block(mid + width * 0.30, base_y - H * 0.030, width * 0.085, width * 0.095, H * 0.055)
    minaret(mid - width * 0.02, base_y - H * 0.150, U * 0.0035)
    minaret(mid + width * 0.075, base_y - H * 0.140, U * 0.0032)

    # ana cami
    block(mid + width * 0.13, base_y - H * 0.058, width * 0.080, width * 0.088, H * 0.070)
    # yarim kubbeler
    block(mid + width * 0.02, base_y - H * 0.030, width * 0.055, width * 0.060, H * 0.030)
    block(mid + width * 0.24, base_y - H * 0.030, width * 0.055, width * 0.060, H * 0.030)

    # on plandaki alcak siluetler
    block(mid - width * 0.18, base_y - H * 0.018, width * 0.075, width * 0.080, H * 0.026)
    minaret(mid - width * 0.30, base_y - H * 0.105, U * 0.0028)
    minaret(mid - width * 0.10, base_y - H * 0.095, U * 0.0026)
    return P


def star_poly(cx, cy, r, inner=0.42, points=5, rot=-math.pi / 2):
    pts = []
    for i in range(points * 2):
        ang = rot + i * math.pi / points
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    return pts


# ---------------------------------------------------------------- kirik sahne


def render(width, height, p, seed=0):
    w, h = width, height
    rng = np.random.default_rng(seed * 7919 + 13)

    # ----- perde agirliklari: p 0..1 boyunca yumusak gecis
    if p < 0.36:
        t = p / 0.36
        pal = mix_palette(ACTS["bozkir"], ACTS["osmanli"], smoothstep((t - 0.72) / 0.28) * 0.55)
        act = "bozkir"
        local = t
    elif p < 0.70:
        t = (p - 0.36) / 0.34
        if t < 0.5:
            pal = mix_palette(ACTS["osmanli"], ACTS["osmanli"], 0)
            local = t
        else:
            pal = mix_palette(ACTS["osmanli"], ACTS["cumhuriyet"], smoothstep((t - 0.5) / 0.5) * 0.85)
            local = t
        act = "osmanli"
    else:
        t = (p - 0.70) / 0.30
        pal = mix_palette(ACTS["cumhuriyet"], ACTS["cumhuriyet"], 0)
        act = "cumhuriyet"
        local = t

    # ----- kamera: yavas zoom + ufkun hafif yukselmesi
    zoom = 1.0 + 0.10 * ease(p)
    horizon_f = 0.755 - 0.020 * ease(p)     # ufuk yuksekligi (resim orani)
    horizon_y = horizon_f * h

    img = np.zeros((h, w, 3), dtype=np.float32)

    # gokyuzu, tum kareye basilir (zemin sonra kapatir)
    glow_strength = 0.0
    if act == "bozkir":
        glow_strength = 0.70 + 0.30 * local
    elif act == "osmanli":
        glow_strength = 1.05 - 0.35 * local
    else:
        glow_strength = 0.35 + 0.90 * smoothstep((local - 0.15) / 0.85)

    img += sky_gradient(w, h, pal, horizon_y, glow_strength, horizon_f)

    # gunes / ay diski + halesi
    sun = pal["sun"]
    sx = w * (0.68 if act != "cumhuriyet" else 0.34)
    sy = h * sun["y"] - h * 0.02 * ease(p)
    sr = h * sun["radius"]
    img += radial_glow(w, h, sx, sy, sr * 2.6, sun["color"], 0.20 * sun["glow"], 2.6)
    # disk
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2)
    disk = np.clip(1.0 - (d - sr) / max(1.0, sr * 0.06), 0, 1)[:, :, None]
    img = img * (1 - disk) + disk * np.array(sun["color"], dtype=np.float32)[None, None, :]

    # yildizlar (gece)
    stars_a = 0.0
    if act == "cumhuriyet":
        stars_a = 1.0 - smoothstep((local - 0.25) / 0.75)
    elif act == "osmanli":
        stars_a = smoothstep((local - 0.72) / 0.28) * 0.7
    if stars_a > 0.01:
        rng2 = np.random.default_rng(99)
        n = 150
        stx = rng2.uniform(0, w, n)
        sty = rng2.uniform(0, horizon_y * 0.92, n)
        sz = rng2.uniform(0.6, 1.9, n)
        br = rng2.uniform(0.25, 1.0, n) ** 2
        star_mask = np.zeros((h, w), dtype=np.float32)
        for i in range(n):
            xi, yi = int(stx[i]), int(sty[i])
            if 0 <= yi < h and 0 <= xi < w:
                star_mask[yi, xi] = max(star_mask[yi, xi], br[i])
        star_mask = np.asarray(
            Image.fromarray((star_mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)),
            dtype=np.float32,
        ) / 255.0
        img += star_mask[:, :, None] * stars_a * 0.85

    # ----- zemin (ufkun alti)
    ground_top = np.array(pal["ground"][0], dtype=np.float32)
    ground_bot = np.array(pal["ground"][1], dtype=np.float32)
    gy = np.clip((np.arange(h, dtype=np.float32) - horizon_y) / max(1.0, h - horizon_y), 0, 1)[:, None, None]
    ground = ground_top[None, None, :] * (1 - gy) + ground_bot[None, None, :] * gy
    ground_layer = np.repeat(ground, w, axis=1)
    below = (np.arange(h, dtype=np.float32) >= horizon_y)[:, None, None]
    img = img * (1 - below) + ground_layer * below

    # ----- perdeye ozgu siluetler
    if act == "bozkir":
        # uzak siralar (paralaks)
        for i, (dy, amp, col, blur) in enumerate([
            (0.030, 0.026, "#1B2530", 1.8),
            (0.016, 0.017, "#141C26", 1.2),
            (0.006, 0.010, "#0E141B", 0.8),
        ]):
            line = ridge_line(w, 11 + i, horizon_y - (0.028 - dy) * h, amp * h, 0.5,
                              phase=p * 3.0 * (i + 1))
            poly = [(x, line[x]) for x in range(0, w, 3)] + [(w - 1, h), (0, h)]
            img = over(img, draw_silhouette(w, h, [poly], hexc(col), blur=blur, ss=2))

        # bozkir duzlugu: ufuktan asagi dogru koyulayan duz alan
        plain = np.clip((np.arange(h, dtype=np.float32) - (horizon_y + 0.02 * h)) / (0.5 * h), 0, 1)
        plain = (plain ** 0.7)[:, None, None] * np.array(hexc("#151A21") - hexc("#0A0D11"), dtype=np.float32)
        img += plain

        # atli okcu: ufukta, kucuk
        ascale = h * 0.085 * zoom
        acx = w * (0.34 + 0.02 * ease(p))
        acy = horizon_y - h * 0.008
        polys = archer_polys(w, h, acx, acy, ascale)
        img = over(img, draw_silhouette(w, h, polys, hexc("#0B0E12"), blur=1.1, ss=2))

        # on plan ot: kenarlarda daha koyu, yazi alanini korur
        for cx, s2 in ((-w * 0.05, h * 0.20), (w * 1.06, h * 0.24)):
            grass = []
            base = horizon_y + h * 0.10
            for k in range(24):
                gx = cx + (k - 12) * w * 0.012 * (s2 / (h * 0.2))
                top = base - s2 * rng.uniform(0.4, 1.0)
                grass.append([(gx - w * 0.006, base + h * 0.3), (gx, top), (gx + w * 0.006, base + h * 0.3)])
            img = over(img, draw_silhouette(w, h, grass, hexc("#05070A"), blur=2.2, ss=2))

    elif act == "osmanli":
        col = hexc("#040406")
        # uzak siluet, henuz ufukta
        base_y = horizon_y + h * 0.002
        polys = dome_cluster_polys(w, h, base_y, w * 0.16, w * 0.92)
        img = over(img, draw_silhouette(w, h, polys, col, blur=1.0, ss=2))

        # suya yansima bandi
        refl = np.zeros((h, w), dtype=np.float32)
        y0 = int(horizon_y + h * 0.02)
        y1 = min(h, int(horizon_y + h * 0.40))
        if y1 > y0:
            refl[y0:y1, :] = 1.0
            fall = np.clip(1 - (np.arange(y0, y1, dtype=np.float32) - y0) / max(1, y1 - y0), 0, 1) ** 1.6
            refl[y0:y1, :] *= fall[:, None]
            # dalga dokusu
            wob = 0.75 + 0.25 * np.sin(np.arange(w, dtype=np.float32)[None, :] * 0.045
                                       + np.arange(y0, y1, dtype=np.float32)[:, None] * 0.6)
            refl[y0:y1, :] *= wob
        refl = np.asarray(Image.fromarray((refl.clip(0, 1) * 255).astype(np.uint8))
                          .filter(ImageFilter.GaussianBlur(2.5)), dtype=np.float32) / 255.0
        img += refl[:, :, None] * hexc("#7A2215")[None, None, :] * 0.35

        # on plan: kenar karanligi
        img *= 1.0 - 0.25 * refl[:, :, None]

    else:  # cumhuriyet
        # ayni bozkir sirti geri doner, simdi safakta
        for i, (dy, amp, col, blur) in enumerate([
            (0.028, 0.024, "#0A0F18", 1.6),
            (0.014, 0.016, "#070B12", 1.1),
            (0.005, 0.009, "#05080D", 0.7),
        ]):
            line = ridge_line(w, 31 + i, horizon_y - (0.026 - dy) * h, amp * h, 0.5,
                              phase=1.2 + p * 2.0)
            poly = [(x, line[x]) for x in range(0, w, 3)] + [(w - 1, h), (0, h)]
            img = over(img, draw_silhouette(w, h, [poly], hexc(col), blur=blur, ss=2))

        # tek yildiz: tepede, kucuk
        st_a = 0.25 + 0.75 * smoothstep(local / 0.6)
        star_c = (w * 0.70, h * 0.20)
        img += radial_glow(w, h, star_c[0], star_c[1], h * 0.20, hexc("#F2D28B"), 0.10 * st_a, 3.0)
        star_layer, star_alpha = draw_silhouette(w, h, [star_poly(star_c[0], star_c[1], h * 0.020)],
                                                hexc("#F2D28B"), blur=0.8, ss=3)
        img = img * (1 - star_alpha) + star_layer * (0.55 + 0.45 * st_a)

        # on plan duzluk
        plain = np.clip((np.arange(h, dtype=np.float32) - (horizon_y + 0.03 * h)) / (0.45 * h), 0, 1)
        img *= 1.0 - (plain[:, None, None] ** 0.8) * 0.35

    # ----- atmosferik pus: ufukta yumusak sicak bant
    haze_y = (np.arange(h, dtype=np.float32) / h)[:, None]
    haze = np.exp(-((haze_y - horizon_f) ** 2) / (2 * 0.055 ** 2)) * 0.16
    img += haze[:, :, None] * (np.array(pal["glow"], dtype=np.float32)[None, None, :] * 0.5)

    # ----- vinyet: koseleri karartir, yaziyi korur
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2) / (w / 2)
    ny = (yy - h / 2) / (h / 2)
    v = np.clip(1.0 - 0.34 * (nx ** 2 * 0.55 + ny ** 2 * 0.85), 0.0, 1.0)
    img *= v[:, :, None]

    # ----- film grain (kareye ozgu, hafif)
    grain = rng.normal(0, 3.6, (h // 2, w // 2, 1)).astype(np.float32)
    grain = np.asarray(
        Image.fromarray(((grain[:, :, 0] + 12)).clip(0, 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
        dtype=np.float32,
    )[:, :, None]
    img += (grain - 12)

    out = np.clip(img, 0, 255).astype(np.uint8)
    im = Image.fromarray(out, "RGB")

    # zoom: merkezden olcek (kucuk oldugu icin kirpma yeterli)
    if zoom > 1.0001:
        cw, ch = int(w / zoom), int(h / zoom)
        ox = (w - cw) // 2
        oy = int((h - ch) * 0.55)
        im = im.crop((ox, oy, ox + cw, oy + ch)).resize((w, h), Image.LANCZOS)

    return im


# ---------------------------------------------------------------- ana


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=180)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--mobile-width", type=int, default=900)
    ap.add_argument("--mobile-height", type=int, default=1600)
    ap.add_argument("--quality", type=int, default=82)
    ap.add_argument("--only", type=int, default=None, help="tek kare ciz (test icin)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    n = args.count
    targets = [(args.width, args.height)] if args.only is None else [(args.width, args.height)]

    for i in range(n):
        if args.only is not None and i != args.only:
            continue
        p = i / max(1, n - 1)
        im = render(args.width, args.height, p, seed=i)
        im.save(os.path.join(args.out, f"frame_{i:04d}.jpg"), quality=args.quality,
                subsampling=2, optimize=True)
        if i % 20 == 0:
            print(f"  {i}/{n}", flush=True)
    print(f"done: {n} frames -> {args.out}")


if __name__ == "__main__":
    main()
