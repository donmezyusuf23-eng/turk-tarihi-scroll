"""
Videodan scroll sitesi icin kare dizisi cikarir.

ScrollCraft'in frames-from-video.mjs betigi ffmpeg'e dayaniyor ve bu makinedeki
ffmpeg 2013 surumu (mjpeg encoder + scale=-2 bozuk). Kare cikarma isini OpenCV
ile yapiyoruz: hem guvenilir, hem de dikey/yatay videoyu otomatik ele aliyor.

Kural: kareler frame_0000.jpg'den baslar, bosluksuz ve 4 haneli olmali —
build-site.mjs bosluk gorurse build'i reddediyor.

Cikti iki set:
  --out          yatay (1920x1080) — masaustu
  --mobile-out   dikey (900x1600)  — telefon

Kaynak video yataysa "cover" ile kirpiliyor; dikeyse yine cover uygulanir, yani
en-boy oranini bozmadan merkezden kirpar.
"""

import argparse
import os
import sys

import cv2
import numpy as np


def cover_frame(frame, out_w, out_h):
    """En-boy oranini bozmadan, hedef cerceveyi tamamen dolduracak sekilde kirp."""
    src_h, src_w = frame.shape[:2]
    scale = max(out_w / src_w, out_h / src_h)
    new_w, new_h = int(round(src_w * scale)), int(round(src_h * scale))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized = cv2.resize(frame, (new_w, new_h), interpolation=interp)
    x0 = (new_w - out_w) // 2
    y0 = (new_h - out_h) // 2
    return resized[y0:y0 + out_h, x0:x0 + out_w]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=180)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--mobile-out", default=None)
    ap.add_argument("--mobile-width", type=int, default=900)
    ap.add_argument("--mobile-height", type=int, default=1600)
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--mobile-quality", type=int, default=80)
    ap.add_argument("--start", type=float, default=0.0, help="baslangic saniyesi")
    ap.add_argument("--end", type=float, default=None, help="bitis saniyesi")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        sys.exit(f"video bulunamadi: {args.input}")

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        sys.exit(f"video acilamadi: {args.input}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total / fps

    start_f = int(args.start * fps)
    end_f = int((args.end if args.end is not None else duration) * fps)
    end_f = max(start_f + 2, min(end_f, total - 1))

    print(f"kaynak : {src_w}x{src_h}  {fps:.2f}fps  {total} kare  {duration:.2f}s")
    print(f"aralik : {start_f}..{end_f} ({end_f - start_f} kare) -> {args.count} cikis karesi")

    # Kare indekslerini esit aralikla sec (basit atlama degil: lineer ornekleme)
    indices = np.linspace(start_f, end_f, args.count).round().astype(int)

    os.makedirs(args.out, exist_ok=True)
    if args.mobile_out:
        os.makedirs(args.mobile_out, exist_ok=True)

    written = 0
    for i, src_idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(src_idx))
        ok, frame = cap.read()
        if not ok or frame is None:
            print(f"  uyari: kare {src_idx} okunamadi, atlaniyor")
            continue

        name = f"frame_{written:04d}.jpg"
        desk = cover_frame(frame, args.width, args.height)
        cv2.imwrite(os.path.join(args.out, name), desk,
                    [cv2.IMWRITE_JPEG_QUALITY, args.quality])
        if args.mobile_out:
            mob = cover_frame(frame, args.mobile_width, args.mobile_height)
            cv2.imwrite(os.path.join(args.mobile_out, name), mob,
                        [cv2.IMWRITE_JPEG_QUALITY, args.mobile_quality])
        written += 1
        if written % 30 == 0:
            print(f"  {written}/{args.count}", flush=True)

    cap.release()

    if written == 0:
        sys.exit("hic kare yazilamadi")

    # Bosluk kontrolu: build-site.mjs bunu kendisi de yapiyor ama erken uyaralim
    missing = [i for i in range(written)
               if not os.path.isfile(os.path.join(args.out, f"frame_{i:04d}.jpg"))]
    if missing:
        sys.exit(f"bosluk var, eksik: {missing[:5]}")

    print(f"bitti  : {written} kare -> {args.out}"
          + (f"  + {args.mobile_out}" if args.mobile_out else ""))


if __name__ == "__main__":
    main()
