"""Her perde icin, hedef kontrasti tutan koyulastirma katsayisini bulur."""
import sys
sys.path.insert(0, 'tools')
import numpy as np
from PIL import Image
from frames_from_photos import ACTS, cover, grade

def rel(c):
    c = c/255.0
    return np.where(c <= 0.04045, c/12.92, ((c+0.055)/1.055)**2.4)

def body_contrast(a):
    """En kotu %72 beyaz govde kontrasti (20 yatay band)."""
    h = a.shape[0]
    lin = 0.2126*rel(a[...,0]) + 0.7152*rel(a[...,1]) + 0.0722*rel(a[...,2])
    worst = 99
    for k in range(20):
        m = lin[int(k*h/20):int((k+1)*h/20)].mean()
        c = (0.72 + 0.28*m + 0.05)/(m + 0.05)
        worst = min(worst, c)
    return worst

TARGET = float(sys.argv[1]) if len(sys.argv) > 1 else 5.6
W, H = 480, 270

for name, path in [("bozkir","photos/bozkir.jpg"),("osmanli","photos/osmanli.jpg"),
                   ("cumhuriyet","photos/cumhuriyet.jpg")]:
    img = Image.open(path).convert("RGB")
    act = ACTS[name]
    best = None
    for darken in np.arange(1.0, 2.61, 0.05):
        # pan/zoom ucunda da tutmali: uc konumun en kotusunu al
        worst = 99
        for z, px, py in ((1.06,-0.10,-0.04),(1.16,0.10,0.04),(1.11,0.0,0.0)):
            f = grade(np.asarray(cover(img, W, H, z, px, py), dtype=np.uint8), act, darken) * 255.0
            worst = min(worst, body_contrast(f))
        if worst >= TARGET:
            best = (round(float(darken),2), round(worst,2))
            break
    if best:
        print(f'{name:12s} darken={best[0]}  kontrast={best[1]}')
    else:
        print(f'{name:12s} TARGET ULASILAMADI (en iyi {round(worst,2)})')
