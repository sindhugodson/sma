
    
    
    # =============================================================
# train.py  —  Smart Attendance System  v9.3
#
# KEY FIX v9.3 — Why confidence was 30% after training:
#
# PROBLEM:
#   Training used one preprocessing pipeline (strong CLAHE 4.0).
#   Runtime used a different pipeline (gamma + stretch + CLAHE).
#   LBPH produces different LBP codes for different pipelines.
#   Self-test showed dist=0.0 (perfect) because it tested on the
#   SAME preprocessing. But live camera used different steps →
#   dist jumped to 60-90 → confidence = 1 - 70/100 = 30%.
#
# FIX:
#   Training now uses EXACTLY the same function as runtime:
#   cv2.equalizeHist() — simple, stable, no parameters.
#   Runtime recognizer also uses equalizeHist as its primary
#   variant. Same input → same LBP codes → dist stays low.
#
#   Why equalizeHist over CLAHE?
#   equalizeHist has zero parameters → always identical output
#   for identical input. CLAHE has clipLimit/tileGridSize that
#   can vary. Consistent preprocessing = low training distance.
#
# AUGMENTATION v9.3:
#   More brightness variants for dark skin training.
#   LBPH radius=1 for fine-grained texture (better for dark skin
#   which has subtler texture than lighter skin).
# =============================================================

import cv2
import os
import pickle
import numpy as np
import logging
import json
from datetime import datetime

import config

log = logging.getLogger(__name__)

try:
    import face_recognition as fr
    DLIB_OK = True
except ImportError:
    DLIB_OK = False

UNKNOWN_CLASS_ID = "__UNKNOWN__"


def preprocess_for_lbph(gray: np.ndarray, size: int = 160) -> np.ndarray:
    """
    v9.3 CRITICAL FIX: Use equalizeHist ONLY.

    This MUST match exactly what _make_variants() in recognizer.py
    puts in its primary slots. equalizeHist is parameter-free →
    always produces identical output → self-test dist stays low
    AND runtime dist also stays low (same preprocessing).

    Previous versions used CLAHE (clipLimit=2.0 or 4.0) which
    varies by implementation and caused train/runtime mismatch.
    """
    resized = cv2.resize(gray, (size, size))
    return cv2.equalizeHist(resized)


def augment(gray: np.ndarray):
    """
    v9.3 augmentation — covers all realistic lighting conditions.
    Extra brightness variants are critical for dark skin since
    classroom lighting varies significantly throughout the day.
    """
    h, w = gray.shape
    out  = []

    # Horizontal flip
    out.append(cv2.flip(gray, 1))

    # Brightness scale variants — dark skin key
    for alpha, beta in [
        (2.2,  70),   # very bright
        (1.8,  50),   # bright
        (1.5,  30),   # medium bright
        (1.3,  15),   # slightly bright
        (1.1,   5),   # subtle
        (0.85, -10),  # slightly dark
        (0.70, -20),  # dark
        (0.55, -30),  # very dark
        (0.40, -40),  # extremely dark (as seen by cheap webcam)
    ]:
        out.append(cv2.convertScaleAbs(gray, alpha=alpha, beta=beta))

    # Gamma brightening variants
    for gamma in [1.3, 1.6, 2.0, 2.4, 2.8]:
        tbl = np.array([min(255, int(((i/255.0)**(1.0/gamma))*255))
                        for i in range(256)], np.uint8)
        out.append(cv2.LUT(gray, tbl))

    # Rotations
    for angle in [-15, -10, -5, 5, 10, 15]:
        M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
        out.append(cv2.warpAffine(gray, M, (w, h),
                                   borderMode=cv2.BORDER_REPLICATE))

    # Blur variants (motion blur simulation)
    out.append(cv2.GaussianBlur(gray, (5, 5), 1.5))
    out.append(cv2.GaussianBlur(gray, (3, 3), 0.8))

    # Noise
    noise = np.random.normal(0, 10, gray.shape).astype(np.int16)
    out.append(np.clip(gray.astype(np.int16) + noise, 0, 255).astype(np.uint8))

    # Sharpen
    k = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]], np.float32)
    out.append(np.clip(cv2.filter2D(gray, -1, k), 0, 255).astype(np.uint8))

    # Center zoom (simulates closer camera)
    pad = int(h * 0.08)
    if pad > 2:
        out.append(cv2.resize(gray[pad:h-pad, pad:w-pad], (w, h)))

    # Salt & pepper noise
    noisy = gray.copy()
    n = int(0.005 * gray.size)
    coords = [np.random.randint(0, i, n) for i in gray.shape]
    noisy[coords[0], coords[1]] = 255
    coords = [np.random.randint(0, i, n) for i in gray.shape]
    noisy[coords[0], coords[1]] = 0
    out.append(noisy)

    # Histogram equalize (same as primary training pipeline)
    out.append(cv2.equalizeHist(gray))

    # CLAHE (secondary)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    out.append(clahe.apply(gray))

    return out


def _get_negative_samples(n=400):
    """
    Synthetic unknown-face samples for negative class training.
    Prevents unknown people from being labelled as enrolled students.
    """
    samples = []
    rng = np.random.RandomState(42)

    for i in range(n):
        base_val = rng.randint(25, 210)
        img = np.full((160, 160), base_val, dtype=np.uint8)
        cx, cy = 80, 80
        for yy in range(0, 160, 2):
            for xx in range(0, 160, 2):
                dx = (xx - cx) / 56.0
                dy = (yy - cy) / 72.0
                if dx*dx + dy*dy < 1.0:
                    v = np.clip(base_val + rng.randint(-40, 40), 10, 245)
                    img[yy:min(160, yy+2), xx:min(160, xx+2)] = v
        noise = rng.normal(0, 18, img.shape).astype(np.int16)
        img   = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img   = cv2.equalizeHist(img)   # same preprocessing as training
        samples.append(img)

    # Background/wall samples
    for i in range(80):
        img = rng.randint(50, 210, (160, 160), dtype=np.uint8)
        img = cv2.GaussianBlur(img.astype(np.uint8), (5, 5), 0)
        img = cv2.equalizeHist(img)
        samples.append(img)

    print(f"  Generated {len(samples)} negative class samples")
    return samples


def train_lbph():
    print("\n─── LBPH Training v9.3 ───")
    persons = sorted([
        d for d in os.listdir(config.DATASET_DIR)
        if os.path.isdir(os.path.join(config.DATASET_DIR, d))
    ])
    if not persons:
        print("  ERROR: No enrolled students found in data/dataset/")
        print("  Run option [1] Enrol New Student first.")
        return {}

    print(f"  Students: {persons}")
    faces, labels, label_map, cid = [], [], {}, 0

    for pid in persons:
        ppath = os.path.join(config.DATASET_DIR, pid)
        imgs  = [f for f in os.listdir(ppath)
                 if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if not imgs:
            print(f"  WARN: No images for {pid} — skipping")
            continue

        label_map[cid] = pid
        raw = aug = 0

        for fname in imgs:
            img = cv2.imread(os.path.join(ppath, fname), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            p = preprocess_for_lbph(img)   # equalizeHist — matches runtime
            faces.append(p)
            labels.append(cid)
            raw += 1

            if config.AUGMENT:
                for a in augment(p):
                    faces.append(a)
                    labels.append(cid)
                    aug += 1

        print(f"  {pid}: {raw} raw + {aug} augmented = {raw+aug} total")
        cid += 1

    if not faces:
        print("  ERROR: No images loaded — check data/dataset/ directory")
        return {}

    # Negative class
    unknown_label          = cid
    label_map[unknown_label] = UNKNOWN_CLASS_ID
    neg_samples            = _get_negative_samples(400)
    for ns in neg_samples:
        faces.append(ns)
        labels.append(unknown_label)
    print(f"  Unknown class: {len(neg_samples)} samples (label={unknown_label})")

    total = len(faces)
    print(f"\n  Training LBPH on {total} total samples…")

    # LBPH parameters:
    # radius=1: fine-grained texture (better for dark skin subtle patterns)
    # neighbors=8: standard
    # grid_x/y=8: good spatial resolution
    rec = cv2.face.LBPHFaceRecognizer_create(
        radius=1, neighbors=8, grid_x=8, grid_y=8)
    rec.train(faces, np.array(labels))

    os.makedirs(config.MODEL_DIR, exist_ok=True)
    rec.save(config.LBPH_MODEL)
    with open(config.LBPH_LABELS, "wb") as f:
        pickle.dump(label_map, f)
    with open(os.path.join(config.MODEL_DIR, "lbph_meta.json"), "w") as f:
        json.dump({"unknown_label": unknown_label}, f)

    real_count = len([v for v in label_map.values() if v != UNKNOWN_CLASS_ID])
    print(f"  Model saved — {real_count} student(s)")
    print(f"  Threshold: {config.LBPH_THRESHOLD}  Margin: {config.LBPH_UNKNOWN_MARGIN}")

    # Self-test
    print("\n  Self-test (expected: dist < 50 for good lighting):")
    for cid_t, pid_t in label_map.items():
        if pid_t == UNKNOWN_CLASS_ID:
            continue
        ppath = os.path.join(config.DATASET_DIR, pid_t)
        imgs  = [f for f in os.listdir(ppath)
                 if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if imgs:
            img = cv2.imread(os.path.join(ppath, imgs[0]),
                              cv2.IMREAD_GRAYSCALE)
            if img is not None:
                p      = preprocess_for_lbph(img)
                lb, lr = rec.predict(p)
                pred   = label_map.get(lb, "?")
                margin = config.LBPH_UNKNOWN_MARGIN
                if pred == UNKNOWN_CLASS_ID:
                    status = "FAIL — __UNKNOWN__ won (re-enrol in better light)"
                elif lr < 20:
                    status = "EXCELLENT (expected conf ~80%+ at runtime)"
                elif lr < 40:
                    status = "GOOD (expected conf ~60-80% at runtime)"
                elif lr < margin * 0.6:
                    status = "OK (expected conf ~40-60% at runtime)"
                elif lr < margin:
                    status = "PASS (expected conf ~30% — re-enrol for better)"
                else:
                    status = f"WARN dist={lr:.0f} > margin={margin} (will show Unknown)"
                print(f"    {pid_t}: pred={pred}  dist={lr:.1f}  → {status}")

    return label_map


def train_dlib():
    print("\n─── dlib Encoding Training ───")
    if not DLIB_OK:
        print("  Skipped — face_recognition not installed")
        return
    if not os.path.isdir(config.KNOWN_FACES_DIR):
        print("  known_faces/ not found — skipped")
        return

    persons = sorted([
        d for d in os.listdir(config.KNOWN_FACES_DIR)
        if os.path.isdir(os.path.join(config.KNOWN_FACES_DIR, d))
    ])
    if not persons:
        print("  No students in known_faces/ — skipped")
        return

    db_enc = {}
    for pid in persons:
        ppath = os.path.join(config.KNOWN_FACES_DIR, pid)
        imgs  = [f for f in os.listdir(ppath)
                 if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if not imgs:
            continue

        encs = []
        for fname in imgs[:100]:
            try:
                img = fr.load_image_file(os.path.join(ppath, fname))
                # Brighten dark images before encoding
                mean = np.mean(img)
                if mean < 80:
                    boost = int((80 - mean) * 0.8)
                    img   = np.clip(img.astype(np.int32) + boost,
                                    0, 255).astype(np.uint8)
                locs = fr.face_locations(img, model="hog")
                if not locs:
                    locs = fr.face_locations(
                        img, model="hog",
                        number_of_times_to_upsample=2)
                if locs:
                    enc = fr.face_encodings(
                        img, locs[:1],
                        num_jitters=2, model="large")
                    if enc:
                        encs.append(enc[0])
            except Exception:
                pass

        if encs:
            db_enc[pid] = encs
            print(f"  {pid}: {len(encs)} encodings")
        else:
            print(f"  WARN: 0 encodings for {pid} (check known_faces/{pid}/)")

    if db_enc:
        with open(config.DLIB_ENCODINGS, "wb") as f:
            pickle.dump(db_enc, f)
        print(f"  Saved {len(db_enc)} student(s)")


def train_all():
    print("\n" + "="*62)
    print(f"  Smart Attendance v9.3 — Training")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*62)

    lm = train_lbph()
    train_dlib()

    try:
        from twin_analysis import train_twin_model
        train_twin_model()
    except Exception as e:
        log.debug("Twin train: %s", e)

    print("\n" + "="*62)
    real = len([v for v in lm.values() if v != UNKNOWN_CLASS_ID])
    print(f"  Training COMPLETE — {real} student(s)")
    print(f"\n  ACCURACY TIPS:")
    print(f"  • If conf < 60%: Re-enrol with more images (200+)")
    print(f"    and better lighting on face")
    print(f"  • Press D in camera window to see exact LBPH distances")
    print(f"  • dist < 40 = conf > 60% = green box")
    print(f"  • dist < 20 = conf > 80% = bright green box")
    print("="*62 + "\n")
    return lm


if __name__ == "__main__":
    train_all()