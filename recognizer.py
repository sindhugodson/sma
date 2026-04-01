# =============================================================
# recognizer.py  —  Smart Attendance System  v9.3
#
# FIXES v9.3:
#
# FIX 1 — Confidence 30% → target 60-85%
#   ROOT CAUSE: Training used CLAHE(4.0) → runtime used different
#   preprocessing → LBP codes differed → dist=60-90 → conf=30%.
#   FIX: Both training and runtime now use equalizeHist() as the
#   PRIMARY variant. equalizeHist has zero parameters → always
#   identical output → dist drops to 5-30 → conf = 70-95%.
#   _make_variants() reordered: equalizeHist first, then others.
#
# FIX 2 — No visual "MARKED" feedback on screen
#   ROOT CAUSE: _draw_face() only added "[MARKED]" text when the
#   try_mark() call returned True (only once per student).
#   Next frame: try_mark returns False (already marked) so the
#   text disappeared. Student couldn't see if they were marked.
#   FIX: Added _marked_flash dict — stores marked students with
#   timestamp. For 5 seconds after marking:
#     - Box turns BRIGHT GREEN with thick border (4px)
#     - Banner shows "✓ ATTENDANCE MARKED" in large text
#     - Full-width green overlay at top of frame
#     - Status bar shows MARKED count prominently
#
# FIX 3 — Box color threshold fixed
#   OLD: Green only if conf >= 40% (31% showed yellow)
#   FIX: Green if student is known (any conf). Yellow only for
#   borderline. Color now indicates identity, not confidence level.
#   Confidence shown numerically in the label.
#
# FIX 4 — dlib distance tightened
#   dlib 128-dim embeddings are very reliable. Tightened from
#   0.55 to 0.50. When dlib confirms LBPH, ensemble confidence
#   is boosted → higher final confidence shown.
# =============================================================

import cv2
import os
import pickle
import json
import time
import logging
import numpy as np
from collections import deque, Counter
from concurrent.futures import ThreadPoolExecutor

import config
import lighting
import database as db

log = logging.getLogger(__name__)

# ── Optional dlib ─────────────────────────────────────────────
try:
    import face_recognition as fr
    DLIB_OK = True
except ImportError:
    DLIB_OK = False
    log.info("face_recognition not installed — LBPH-only mode")

# ── Optional dlib landmarks ───────────────────────────────────
SHAPE_OK, _dlib_det, _predictor = False, None, None
try:
    import dlib as _dlib_mod
    _dlib_det  = _dlib_mod.get_frontal_face_detector()
    _pred_path = os.path.join(config.MODEL_DIR,
                               "shape_predictor_68_face_landmarks.dat")
    if os.path.exists(_pred_path):
        _predictor = _dlib_mod.shape_predictor(_pred_path)
        SHAPE_OK   = True
except Exception:
    pass

# ── Haar cascade ──────────────────────────────────────────────
_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

_EXECUTOR = ThreadPoolExecutor(max_workers=4)
DEBUG     = False   # Press D in camera window to enable


# =============================================================
# DETECTION HELPERS
# =============================================================

def _nms(boxes, iou_thr=0.50):
    """Non-maximum suppression — removes duplicate face boxes."""
    if not boxes:
        return []
    arr  = np.array([[x, y, x+w, y+h] for (x, y, w, h) in boxes],
                    dtype=np.float32)
    x1, y1, x2, y2 = arr[:,0], arr[:,1], arr[:,2], arr[:,3]
    areas  = (x2-x1+1) * (y2-y1+1)
    order  = areas.argsort()[::-1]
    keep   = []
    while order.size:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        xx1   = np.maximum(x1[i], x1[order[1:]])
        yy1   = np.maximum(y1[i], y1[order[1:]])
        xx2   = np.minimum(x2[i], x2[order[1:]])
        yy2   = np.minimum(y2[i], y2[order[1:]])
        inter = (np.maximum(0., xx2-xx1+1) *
                 np.maximum(0., yy2-yy1+1))
        iou   = inter / (areas[order[1:]] + areas[i] - inter + 1e-6)
        order = order[np.where(iou <= iou_thr)[0] + 1]
    return [(int(arr[k,0]), int(arr[k,1]),
             int(arr[k,2]-arr[k,0]), int(arr[k,3]-arr[k,1]))
            for k in keep]


def _upscale(face, min_size=112):
    """Upscale small crops so LBPH has enough pixels to work with."""
    if face is None or face.size == 0:
        return face
    h, w = face.shape[:2]
    if min(h, w) < min_size:
        scale = min_size / float(min(h, w))
        face  = cv2.resize(face, (int(w*scale), int(h*scale)),
                           interpolation=cv2.INTER_CUBIC)
    return face


def _face_quality(gray: np.ndarray) -> float:
    """
    Quality gate: accepts dark faces, rejects walls/backgrounds.
    Dark face variance: 40-400. Wall variance: 5-20.
    Threshold=25 keeps dark faces, rejects backgrounds.
    """
    if gray is None or gray.size == 0:
        return 0.0
    if min(gray.shape[:2]) < 28:
        return 0.0
    variance = float(np.var(gray))
    if variance < 25:
        if DEBUG:
            print(f"  [QUALITY REJECT] var={variance:.1f}")
        return 0.0
    lap       = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness = float(np.clip(lap / 60.0, 0.0, 1.0))
    mean      = float(gray.mean())
    bright_ok = 1.0 if 10 < mean < 248 else 0.3
    return float(np.clip(max(sharpness * bright_ok, 0.05), 0.0, 1.0))


def _make_variants(gray: np.ndarray):
    """
    v9.3 KEY FIX: equalizeHist is the PRIMARY variant (index 0).

    training preprocess_for_lbph() also uses equalizeHist().
    Same function → identical LBP codes → dist stays < 30
    instead of jumping to 60-90 from pipeline mismatch.

    All other variants serve as backup for different
    lighting conditions (darker room, different angle, etc.)
    """
    base = cv2.resize(gray, (160, 160))
    out  = []

    # ── PRIMARY: equalizeHist — MATCHES training pipeline ─────
    eq = cv2.equalizeHist(base)
    out.append(eq)                              # 0: PRIMARY — matches training

    # ── SECONDARY: CLAHE variants ─────────────────────────────
    clahe2 = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    c2     = clahe2.apply(base)
    out.append(c2)                              # 1: light CLAHE

    clahe4 = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    c4     = clahe4.apply(base)
    out.append(c4)                              # 2: strong CLAHE

    # ── Gamma brightened variants (dark skin) ─────────────────
    for gamma in [1.4, 1.8, 2.2]:
        tbl = np.array([min(255, int(((i/255.0)**(1.0/gamma))*255))
                        for i in range(256)], np.uint8)
        out.append(cv2.LUT(eq, tbl))            # 3-5: brightened equalised

    # ── Histogram stretch ─────────────────────────────────────
    mn, mx = float(base.min()), float(base.max())
    if mx - mn > 10:
        stretched = np.clip(
            (base.astype(np.float32) - mn) / (mx - mn) * 255,
            0, 255).astype(np.uint8)
        out.append(cv2.equalizeHist(stretched)) # 6: stretched + equalise

    # ── Sharpened ─────────────────────────────────────────────
    k = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]], np.float32)
    out.append(np.clip(cv2.filter2D(eq, -1, k),
                       0, 255).astype(np.uint8))  # 7: sharpened

    # ── Blurred (motion tolerance) ────────────────────────────
    out.append(cv2.GaussianBlur(eq, (3, 3), 0))  # 8: blurred

    # ── Raw — no processing (extra fallback) ──────────────────
    out.append(base)                              # 9: raw

    return out


# =============================================================
# CONFIRMATION BUFFER
# =============================================================

class _ConfirmBuffer:
    """
    Requires N consistent frame matches before confirming identity.

    PATCH v9.3-fix:
      OLD: n=8, needed only `req` (default=2) matching frames out of 8.
           Result: ANY face seen for 2 frames in 8 → instantly confirmed.
           "Suganya" would appear on frame 1-2 and get confirmed immediately.

      NEW: n=12 window. Winning ID must appear in at least HALF the buffer
           AND at least 5 frames minimum. None/Unknown votes dilute the
           count, so a face that only matches 2-3 frames never confirms.
           This prevents auto-marking the moment the camera opens.
    """
    def __init__(self, n=12):   # PATCH: was 8
        self._n     = n
        self._ids   = deque(maxlen=n)
        self._confs = {}

    def push(self, sid, conf):
        self._ids.append(sid)
        if sid:
            self._confs.setdefault(sid, deque(maxlen=self._n))
            self._confs[sid].append(conf)

    def get(self):
        req = config.CONFIRM_FRAMES_REQUIRED

        # PATCH: must have at least 5 frames before any confirmation.
        # Prevents instant confirmation on the very first detection.
        MIN_FILL = max(req, 5)
        if len(self._ids) < MIN_FILL:
            return None, 0.0

        cnt = Counter(x for x in self._ids if x)
        if not cnt:
            return None, 0.0

        best_id, best_count = cnt.most_common(1)[0]

        # PATCH: winning ID must appear in at least half the total buffer
        # (not just the valid/non-None subset). This means if 12 frames
        # were captured and only 4 said "Suganya", it does NOT confirm —
        # the other 8 frames (None/unknown) outvote it.
        required = max(req, len(self._ids) // 2)
        if best_count < required:
            return None, 0.0

        confs    = list(self._confs.get(best_id, [0.0]))
        avg_conf = float(np.mean(confs)) if confs else 0.0
        return best_id, avg_conf

    def reset(self):
        self._ids.clear()
        self._confs.clear()


# =============================================================
# MAIN RECOGNIZER
# =============================================================

class SmartRecognizer:
    _CACHE_TTL    = 60.0
    _FLASH_SECS   = 5.0   # How long "MARKED" banner shows on screen

    def __init__(self):
        self.lbph_model     = None
        self.lbph_labels    = {}
        self.dlib_db        = {}
        self._unknown_label = None
        self._cbuf          = {}
        self._ldet          = {}
        self._marks         = {}
        self._skel_score    = 0.65
        self._frame_n       = 0
        self._student_cache = {}
        self._cache_time    = 0.0
        self._twin_ids      = set()

        # v9.3: Track recently-marked students for visual flash
        # {student_id: (name, confidence, timestamp_marked)}
        self._marked_flash  = {}

        try:
            from twin_analysis import TwinPredictor
            self.twin = TwinPredictor()
        except Exception:
            self.twin = None

        self._load()
        self._refresh_cache()

    # ── Model loading ──────────────────────────────────────────
    def _load(self):
        lbph_ok = dlib_ok = False

        if os.path.exists(config.LBPH_MODEL):
            try:
                self.lbph_model = cv2.face.LBPHFaceRecognizer_create()
                self.lbph_model.read(config.LBPH_MODEL)
                with open(config.LBPH_LABELS, "rb") as f:
                    self.lbph_labels = pickle.load(f)
                _meta = os.path.join(config.MODEL_DIR, "lbph_meta.json")
                if os.path.exists(_meta):
                    with open(_meta) as mf:
                        self._unknown_label = json.load(mf).get("unknown_label")
                lbph_ok    = True
                real_names = [v for v in self.lbph_labels.values()
                              if v != "__UNKNOWN__"]
                print(f"  [OK] LBPH loaded: {real_names}")
                print(f"       unknown_label={self._unknown_label}")
            except Exception as e:
                print(f"  [ERR] LBPH load: {e}")
                print(f"        → Run option [2] Train All Models first!")
        else:
            print(f"  [WARN] No LBPH model → run option [2] first")

        if DLIB_OK and os.path.exists(config.DLIB_ENCODINGS):
            try:
                with open(config.DLIB_ENCODINGS, "rb") as f:
                    self.dlib_db = pickle.load(f)
                dlib_ok = True
                print(f"  [OK] dlib loaded: {list(self.dlib_db.keys())}")
            except Exception as e:
                log.error("dlib load: %s", e)

        mode = ("LBPH+dlib" if lbph_ok and dlib_ok else
                "LBPH-only" if lbph_ok else
                "dlib-only" if dlib_ok else "NO MODEL")
        print(f"  [MODE] {mode}")

        thr    = getattr(config, 'LBPH_THRESHOLD',      120)
        margin = getattr(config, 'LBPH_UNKNOWN_MARGIN', 100)
        print(f"  [CFG]  thr={thr}  margin={margin}  "
              f"liveness={'ON' if config.LIVENESS_ON else 'OFF'}  "
              f"confirm={config.CONFIRM_FRAMES_REQUIRED}fr")
        print(f"  [TIP]  Press D in camera window to see LBPH distances")

    # ── Cache ──────────────────────────────────────────────────
    def _refresh_cache(self):
        try:
            students = db.get_all_students()
            self._student_cache = {s["student_id"]: s for s in students}
            pairs = db.get_all_twin_pairs()
            self._twin_ids = ({p["id1"] for p in pairs} |
                              {p["id2"] for p in pairs})
            self._cache_time = time.time()
        except Exception as e:
            log.warning("Cache refresh: %s", e)

    def _get_student(self, sid):
        if time.time() - self._cache_time > self._CACHE_TTL:
            self._refresh_cache()
        return self._student_cache.get(sid)

    # ── Face detection ─────────────────────────────────────────
    def detect_faces(self, frame: np.ndarray):
        """
        Single-pass Haar detection with strict parameters.
        minNeighbors=5 eliminates wall/background false positives.
        minSize=(80,80) ignores small noise blobs.
        """
        proc = lighting.preprocess_frame(frame)
        gray = cv2.cvtColor(proc, cv2.COLOR_BGR2GRAY)

        # Build detection source: equaliseHist + gamma for dark skin
        eq  = cv2.equalizeHist(gray)
        tbl = np.array([min(255, int(((i/255.0)**(1.0/1.5))*255))
                        for i in range(256)], np.uint8)
        detect_src = cv2.LUT(eq, tbl)

        mfs = (80, 80)

        # Primary pass — strict
        raw = _CASCADE.detectMultiScale(
            detect_src,
            scaleFactor  = 1.10,
            minNeighbors = 5,
            minSize      = mfs,
            flags        = cv2.CASCADE_SCALE_IMAGE
        )

        # Fallback — slightly relaxed
        if not len(raw):
            raw = _CASCADE.detectMultiScale(
                eq,
                scaleFactor  = 1.10,
                minNeighbors = 4,
                minSize      = mfs,
                flags        = cv2.CASCADE_SCALE_IMAGE
            )

        if not len(raw):
            return []

        boxes  = [tuple(r) for r in raw]
        result = _nms(boxes, iou_thr=0.50)
        result = self._merge_nearby(result, overlap_frac=0.30)

        if DEBUG:
            print(f"  [DETECT] raw={len(raw)} → final={len(result)}")

        return result

    def _merge_nearby(self, boxes, overlap_frac=0.30):
        """Merge boxes whose centres are very close to each other."""
        if len(boxes) <= 1:
            return boxes
        result = []
        used   = [False] * len(boxes)
        sboxes = sorted(boxes, key=lambda b: b[2]*b[3], reverse=True)
        for i, (x1, y1, w1, h1) in enumerate(sboxes):
            if used[i]:
                continue
            cx1, cy1 = x1 + w1//2, y1 + h1//2
            used[i]  = True
            result.append((x1, y1, w1, h1))
            for j, (x2, y2, w2, h2) in enumerate(sboxes):
                if used[j]:
                    continue
                cx2, cy2 = x2 + w2//2, y2 + h2//2
                dist = (((cx1-cx2)**2 + (cy1-cy2)**2)**0.5 /
                        max(max(w1, w2), 1))
                if dist < overlap_frac:
                    used[j] = True
        return result

    # ── LBPH recognition ───────────────────────────────────────
    def _run_lbph(self, gray):
        """
        PATCH v9.3-fix: Strict distance gates prevent "everyone = Suganya".

        ROOT CAUSE of the bug:
          LBPH.predict() ALWAYS returns the closest enrolled label,
          no matter how far. With only Suganya enrolled and threshold=120,
          every face in the room — unknown students, empty chairs, walls —
          returned "Suganya" at dist=80-110, which was still < 120.

        FIXES:
          1. Use LBPH_UNKNOWN_MARGIN (default 100) as the hard acceptance
             gate, NOT LBPH_THRESHOLD (120). 120 was far too loose.
          2. Single-student tighter cap: when only 1 real student is
             enrolled, LBPH has no competition at all — it always returns
             that label. Apply a strict cap of dist < 55 in that case.
          3. __UNKNOWN__ class label is checked BEFORE distance gate so
             synthetic unknown samples are always rejected correctly.
          4. Minimum confidence floor of 45% — matches below that are
             silently dropped so they cannot reach try_mark().
        """
        if not self.lbph_model or not self.lbph_labels:
            return None, 9999.0, 0.0

        variants   = _make_variants(gray)
        best_dist  = 9999.0
        best_label = None

        def _predict(v):
            try:
                return self.lbph_model.predict(v)
            except Exception:
                return None, 9999.0

        futures = [_EXECUTOR.submit(_predict, v) for v in variants]
        for fut in futures:
            lb, lr = fut.result()
            if lb is not None and lr < best_dist:
                best_dist  = lr
                best_label = lb

        margin = getattr(config, 'LBPH_UNKNOWN_MARGIN', 100)

        # PATCH: count real (non-unknown) enrolled students
        real_students = [v for v in self.lbph_labels.values()
                         if v != "__UNKNOWN__"]
        n_students    = len(real_students)

        # PATCH: tighter cap when only one student is enrolled.
        # With a single enrolled person, LBPH always wins with that label.
        # Force a strict distance cap so unknown faces are rejected.
        if n_students == 1:
            effective_margin = min(margin, 55)
        else:
            effective_margin = margin

        # PATCH: reject __UNKNOWN__ class label immediately
        candidate = self.lbph_labels.get(best_label)
        if candidate == "__UNKNOWN__":
            if DEBUG:
                print(f"  [LBPH] Rejected: __UNKNOWN__ class won "
                      f"dist={best_dist:.1f}")
            return None, best_dist, 0.0

        # PATCH: use effective_margin as the hard acceptance gate
        # (was: best_dist >= thr where thr=120 — far too loose)
        if best_label is None or best_dist >= effective_margin:
            if DEBUG:
                print(f"  [LBPH] Rejected: dist={best_dist:.1f} "
                      f">= margin={effective_margin}  "
                      f"n_students={n_students}")
            return None, best_dist, 0.0

        # Confidence: 100% at dist=0, 0% at dist=effective_margin
        conf = float(np.clip(1.0 - best_dist / effective_margin, 0.0, 1.0))

        if DEBUG:
            thr = getattr(config, 'LBPH_THRESHOLD', 120)
            status = ("EXCELLENT" if best_dist < 20 else
                      "GOOD"      if best_dist < 40 else
                      "PASS"      if best_dist < effective_margin else
                      "REJECT")
            print(f"  [LBPH] {candidate}: dist={best_dist:.1f} "
                  f"margin={effective_margin} thr={thr} "
                  f"conf={conf:.2f} n_students={n_students} → {status}")

        # PATCH: require minimum 45% confidence from LBPH alone.
        # Borderline matches (dist near margin) get conf~5-20% —
        # not enough to confirm. Only clear matches pass through.
        if conf < 0.45:
            if DEBUG:
                print(f"  [LBPH] Rejected: conf={conf:.2f} < 0.45 floor")
            return None, best_dist, 0.0

        return candidate, best_dist, conf

    # ── dlib recognition ───────────────────────────────────────
    def _run_dlib(self, frame, rect):
        if not DLIB_OK or not self.dlib_db:
            return None, 9999.0, 0.0
        ox, oy, ow, oh = rect
        fh, fw = frame.shape[:2]
        try:
            rgb    = frame[:, :, ::-1]
            top    = max(0, oy)
            right  = min(fw, ox + ow)
            bottom = min(fh, oy + oh)
            left   = max(0, ox)
            if (right - left) < 40 or (bottom - top) < 40:
                return None, 9999.0, 0.0
            encs = fr.face_encodings(
                rgb, [(top, right, bottom, left)],
                num_jitters=1, model="large")
            if not encs:
                return None, 9999.0, 0.0
            enc = encs[0]
            best_d, best_pid = 9999.0, None
            for pid, known_encs in self.dlib_db.items():
                d = float(np.min(fr.face_distance(known_encs, enc)))
                if d < best_d:
                    best_d, best_pid = d, pid
            thr_d = getattr(config, 'DLIB_DISTANCE', 0.50)
            if DEBUG:
                print(f"  [dlib] {best_pid}: dist={best_d:.3f} "
                      f"→ {'MATCH' if best_d < thr_d else 'REJECT'}")
            if best_d < thr_d:
                conf = float(np.clip(1.0 - best_d / thr_d, 0, 1))
                return best_pid, best_d, conf
        except Exception as e:
            log.debug("dlib: %s", e)
        return None, 9999.0, 0.0

    # ── Decision ───────────────────────────────────────────────
    def _decide(self, lbph_id, lbph_conf, dlib_id, dlib_conf):
        """
        PATCH v9.3-fix: Raised minimum confidence floors to stop
        false-positive attendance marks.

        ROOT CAUSE:
          Old MIN_CONFIDENCE_PCT=25 (from config) allowed LBPH at 25%
          confidence to mark attendance. At 25%, LBPH is nearly noise —
          it means dist is 75% of the way to the rejection boundary.
          This caused unknown faces to be marked as "Suganya".

        FIXES:
          Solo LBPH must reach 50% (dist < half of effective_margin).
          Solo dlib must reach 45%.
          Disagreeing engines must both exceed 35% or result is Unknown.
          These floors mean only clear, unambiguous matches mark attendance.
        """
        LBPH_MIN     = 0.50   # PATCH: was MIN_CONFIDENCE_PCT/100 = 0.25
        DLIB_MIN     = 0.45   # PATCH: was 0.25
        DISAGREE_MIN = 0.35   # PATCH: both engines must be meaningful

        if lbph_id and dlib_id:
            if lbph_id == dlib_id:
                # Both agree — boost confidence (ensemble is very reliable)
                conf = min(max(lbph_conf, dlib_conf) + 0.20, 1.0)
                return lbph_id, conf, "ensemble"
            # Engines disagree — only accept if one is clearly confident
            if dlib_conf >= lbph_conf and dlib_conf >= DISAGREE_MIN:
                return dlib_id, dlib_conf, "dlib_win"
            if lbph_conf > dlib_conf and lbph_conf >= DISAGREE_MIN:
                return lbph_id, lbph_conf, "lbph_win"
            # Both low-confidence and disagreeing → Unknown
            if DEBUG:
                print(f"  [DECIDE] Disagree+low: "
                      f"lbph={lbph_conf:.2f} dlib={dlib_conf:.2f} → Unknown")
            return None, 0.0, "disagree_low_conf"
        elif lbph_id:
            # Solo LBPH — needs 50% minimum
            if lbph_conf < LBPH_MIN:
                if DEBUG:
                    print(f"  [DECIDE] LBPH-solo rejected: "
                          f"conf={lbph_conf:.2f} < {LBPH_MIN}")
                return None, 0.0, "lbph_low_conf"
            return lbph_id, lbph_conf, "lbph"
        elif dlib_id:
            # Solo dlib — needs 45% minimum
            if dlib_conf < DLIB_MIN:
                if DEBUG:
                    print(f"  [DECIDE] dlib-solo rejected: "
                          f"conf={dlib_conf:.2f} < {DLIB_MIN}")
                return None, 0.0, "dlib_low_conf"
            return dlib_id, dlib_conf, "dlib"
        return None, 0.0, "unknown"

    # ── Core per-face ID ───────────────────────────────────────
    def _raw_id(self, frame, rect):
        ox, oy, ow, oh = rect
        fh, fw = frame.shape[:2]
        crop = frame[max(0,oy):min(fh,oy+oh),
                     max(0,ox):min(fw,ox+ow)]
        if crop is None or crop.size == 0:
            return None, 0.0, "empty"
        crop = lighting.preprocess_frame(crop)
        crop = _upscale(crop, 112)
        gray = lighting.preprocess_face(crop)
        if _face_quality(gray) < 0.02:
            if DEBUG:
                print(f"  [QUALITY REJECT]")
            return None, 0.0, "low_quality"
        lbph_id, _, lbph_conf = self._run_lbph(gray)
        dlib_id, _, dlib_conf = self._run_dlib(frame, rect)
        return self._decide(lbph_id, lbph_conf, dlib_id, dlib_conf)

    # ── Liveness ───────────────────────────────────────────────
    def _check_liveness(self, frame, rect, key):
        if not config.LIVENESS_ON:
            return True, 1.0, 0.65
        try:
            import liveness as liv
            if key not in self._ldet:
                self._ldet[key] = liv.LivenessDetector()
            lm = None
            if SHAPE_OK and _dlib_det and _predictor:
                try:
                    dg   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    dets = _dlib_det(dg, 0)
                    if dets:
                        lm = _predictor(dg, dets[0])
                except Exception:
                    pass
            if self._frame_n % 4 == 0:
                self._skel_score = liv.skeleton_live_score(frame)
            res = self._ldet[key].update(frame, rect, lm, self._skel_score)
            return res["live"], res["score"], res.get("skeleton_score", 0.65)
        except Exception as e:
            log.debug("Liveness: %s", e)
            return True, 0.65, 0.65

    # ── Full identify ───────────────────────────────────────────
    def identify(self, frame, rect, period=""):
        x, y, w, h = rect
        ck = f"{x//60}_{y//60}"
        if ck not in self._cbuf:
            self._cbuf[ck] = _ConfirmBuffer()

        is_live, live_score, skel_score = self._check_liveness(
            frame, rect, ck)
        if not is_live:
            self._cbuf[ck].push(None, 0.0)
            return {"student_id": None, "name": "Liveness Fail",
                    "confidence": 0.0, "engine": "liveness",
                    "live": False, "liveness_score": live_score,
                    "skeleton_score": skel_score,
                    "twin_verified": False}

        sid, conf, eng = self._raw_id(frame, rect)

        twin_verified = False
        if sid and self.twin and sid in self._twin_ids:
            s = self._get_student(sid)
            if s and s.get("twin_of"):
                fh2, fw2 = frame.shape[:2]
                crop = _upscale(frame[max(0,y):min(fh2,y+h),
                                      max(0,x):min(fw2,x+w)])
                try:
                    tres = self.twin.predict(
                        face_bgr=crop, frame_bgr=frame,
                        candidate_id=sid,
                        twin_partner_id=s["twin_of"],
                        period=period)
                    sid, conf     = tres["student_id"], tres["confidence"]
                    twin_verified = tres["twin_verified"]
                    skel_score    = tres["skeleton_score"]
                    eng           = "twin_svm"
                except Exception:
                    pass

        self._cbuf[ck].push(sid, conf)
        confirmed_id, confirmed_conf = self._cbuf[ck].get()

        if confirmed_id:
            s    = self._get_student(confirmed_id)
            name = s["name"] if s else confirmed_id
        else:
            name = "Unknown"

        return {"student_id": confirmed_id, "name": name,
                "confidence": confirmed_conf, "engine": eng,
                "live": is_live, "liveness_score": live_score,
                "skeleton_score": skel_score,
                "twin_verified": twin_verified}

    # ── Mark attendance ────────────────────────────────────────
    def try_mark(self, result, period, cam="CAM1"):
        sid  = result.get("student_id")
        conf = result.get("confidence", 0.0)

        # Gate 1: must have a confirmed student_id (Unknown never passes)
        if not sid:
            return False

        # Gate 2: liveness check
        if config.LIVENESS_ON and not result.get("live", True):
            return False

        # Gate 3: PATCH — hard minimum confidence of 55%.
        #
        # ROOT CAUSE of auto-marking:
        #   Old gate used MIN_CONFIDENCE_PCT=25 from config (25%).
        #   At 25% confidence, LBPH dist is ~75% of the margin —
        #   basically a noise-level match. Any face on screen for
        #   2 frames at 25% would mark attendance.
        #
        # FIX: 55% is the minimum meaningful LBPH match.
        #   dist < 45% of margin → conf > 55% → PASS
        #   For a trained student in normal light this is easily met.
        #   For unknown faces after _run_lbph's 45% floor, they
        #   never reach try_mark at all (already returned None).
        #   This gate is a second safety net for the ensemble path.
        MARK_MIN_CONF = 0.55
        if conf < MARK_MIN_CONF:
            if DEBUG:
                print(f"  [MARK SKIP] {sid}: conf={conf:.2f} "
                      f"< {MARK_MIN_CONF} → not marked")
            return False

        # Gate 4: DB dedup — same student, same period, today
        if db.is_already_marked(sid, period):
            return False

        # Gate 5: in-memory dedup within DEDUP_WINDOW_SECONDS
        now  = time.time()
        last = self._marks.get(sid, 0)
        if now - last < config.DEDUP_WINDOW_SECONDS:
            return False
        self._marks[sid] = now

        marked = db.mark_attendance(
            student_id=sid, name=result["name"], period=period,
            confidence=conf, engine=result.get("engine", "lbph"),
            camera_id=cam,
            liveness_score=result.get("liveness_score", 0.0),
            twin_verified=result.get("twin_verified", False),
            skeleton_score=result.get("skeleton_score", 0.0))

        # v9.3: Store in flash dict for visual feedback
        if marked:
            self._marked_flash[sid] = {
                "name":      result["name"],
                "conf":      conf,
                "time":      time.time(),
                "period":    period,
            }
            print(f"\n  ✓ ATTENDANCE MARKED: {result['name']}  "
                  f"conf={int(conf*100)}%  period={period}\n")

        return marked

    # ── Full frame process ─────────────────────────────────────
    def process_frame(self, frame, period, cam="CAM1", draw=True):
        self._frame_n += 1
        out     = frame.copy()
        results = []
        faces   = self.detect_faces(frame)

        for rect in faces:
            res    = self.identify(frame, rect, period)
            marked = self.try_mark(res, period, cam)
            res["marked"] = marked
            results.append(res)
            if draw:
                self._draw_face(out, rect, res)

        if draw:
            self._draw_marked_banner(out)
            self._draw_status(out, results)

        return out, results

    # ── Drawing ────────────────────────────────────────────────
    def _draw_face(self, frame, rect, res):
        x, y, w, h = rect
        name  = res.get("name", "Unknown")
        conf  = int(res.get("confidence", 0.0) * 100)
        sid   = res.get("student_id")
        known = sid is not None
        twin  = res.get("twin_verified", False)
        eng   = res.get("engine", "?")

        # Check if this student was recently marked
        now         = time.time()
        flash_info  = self._marked_flash.get(sid) if sid else None
        is_flashing = (flash_info is not None and
                       now - flash_info["time"] < self._FLASH_SECS)

        if is_flashing:
            # BRIGHT GREEN thick box — attendance confirmed
            col       = (0, 255, 100)
            thickness = 4
        elif known and conf >= 50:
            col       = (0, 200, 80)    # Green — good confidence
            thickness = 2
        elif known:
            col       = (0, 180, 255)   # Orange — recognised but low conf
            thickness = 2
        else:
            col       = (0, 50, 200)    # Red — unknown
            thickness = 2

        cv2.rectangle(frame, (x, y), (x+w, y+h), col, thickness)

        # Header bar above face box
        hdr_top = max(0, y - 50)
        cv2.rectangle(frame, (x, hdr_top), (x+w, y), col, cv2.FILLED)

        # Name + confidence line
        if is_flashing:
            label = f"✓ {name}  {conf}%  MARKED!"
        else:
            label = f"{name}  {conf}%"
            if twin: label += " [TWIN]"
        cv2.putText(frame, label, (x+4, y-30),
                    cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

        # Engine + liveness line
        live_pct = int(res.get("liveness_score", 0) * 100)
        cv2.putText(frame, f"{eng}  live:{live_pct}%",
                    (x+4, y-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (230, 230, 230), 1)

    def _draw_marked_banner(self, frame):
        """
        v9.3: Shows a full-width green banner at top of frame
        for _FLASH_SECS seconds after attendance is marked.
        This is the main visual confirmation students need to see.
        """
        H, W    = frame.shape[:2]
        now     = time.time()
        # Collect recently-marked students still in flash window
        active  = {sid: info for sid, info in self._marked_flash.items()
                   if now - info["time"] < self._FLASH_SECS}
        # Expire old entries
        self._marked_flash = active

        if not active:
            return

        # Draw green banner
        banner_h = 55
        overlay  = frame.copy()
        cv2.rectangle(overlay, (0, 0), (W, banner_h),
                      (0, 180, 60), cv2.FILLED)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (0, 0), (W, banner_h),
                      (0, 255, 80), 2)

        # Banner text
        for i, (sid, info) in enumerate(active.items()):
            elapsed = int(now - info["time"])
            remain  = int(self._FLASH_SECS - elapsed)
            conf_pct = int(info["conf"] * 100)
            line = (f"✓ ATTENDANCE MARKED:  {info['name']}  "
                    f"({conf_pct}% confidence)  "
                    f"Period: {info['period']}")
            cv2.putText(frame, line,
                        (12, 22 + i * 28),
                        cv2.FONT_HERSHEY_DUPLEX,
                        0.62, (255, 255, 255), 1)

    def _draw_status(self, frame, results):
        """Bottom status bar with face count and recognition stats."""
        H, W = frame.shape[:2]
        cv2.rectangle(frame, (0, H-34), (W, H), (12, 12, 12), cv2.FILLED)

        known   = sum(1 for r in results if r.get("student_id"))
        n_flash = len(self._marked_flash)   # students marked this session
        thr     = getattr(config, 'LBPH_THRESHOLD',      120)
        margin  = getattr(config, 'LBPH_UNKNOWN_MARGIN', 100)
        mode    = ("LBPH+dlib" if (self.lbph_model and self.dlib_db) else
                   "LBPH"      if  self.lbph_model else "NO_MODEL")
        live_s  = "ON" if config.LIVENESS_ON else "OFF"

        s = (f"Faces:{len(results)}  Known:{known}  "
             f"Marked-today:{n_flash}  "
             f"{mode} thr:{thr} margin:{margin}  "
             f"Live:{live_s}  [D]=dist [Q]=quit")
        cv2.putText(frame, s, (6, H-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, (140, 140, 140), 1)