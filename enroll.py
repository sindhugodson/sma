
# =============================================================
# enroll.py  —  Smart Attendance System  v8.2
#
# FIXES for "camera not responding" / MSMF error:
#  1. Uses cv2.CAP_DSHOW backend on Windows (avoids RGB24 error)
#  2. Falls back through MSMF -> AUTO if DSHOW fails
#  3. Camera opens at 640x480 (safe) not 1280x720 (broken)
#  4. Read-timeout recovery: skips bad frames, never freezes
#  5. Removed Unicode chars that crash Windows consoles
#  6. cap.set() called AFTER open to avoid format lock
# =============================================================
import cv2
import os
import time
import logging
import numpy as np
import config
import database as db
import lighting

log = logging.getLogger(__name__)


# =============================================================
# Camera helpers
# =============================================================
def _open_camera(index: int):
    """
    Open camera trying DSHOW first (Windows fix), then fallback.
    Returns cap object or None.
    DSHOW backend avoids the MSMF 'unsupported media type' RGB24 error.
    """
    import platform
    if platform.system() == "Windows":
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_ANY, cv2.CAP_V4L2]

    for backend in backends:
        try:
            cap = cv2.VideoCapture(index + (backend if backend != cv2.CAP_ANY else 0))
            # For explicit backend use addApiPreference pattern
            if backend != cv2.CAP_ANY:
                cap.release()
                cap = cv2.VideoCapture(index, backend)

            if not cap.isOpened():
                cap.release()
                continue

            # Safe resolution: 640x480 always works
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS,          30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE,   2)

            # Flush stale frames
            for _ in range(8):
                cap.grab()
                time.sleep(0.02)

            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                log.info("Camera opened backend=%s %dx%d", backend, w, h)
                print(f"  Camera backend: {backend}  resolution: {w}x{h}")
                return cap
            cap.release()
        except Exception as e:
            log.debug("Backend %s failed: %s", backend, e)

    return None


def _read_frame(cap, timeout_s: float = 2.0):
    """
    Read a frame with timeout. Returns (True, frame) or (False, None).
    Prevents the window from freezing if camera stalls.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ret, frame = cap.read()
        if ret and frame is not None and frame.size > 0:
            return True, frame
        time.sleep(0.02)
    return False, None


# =============================================================
# Quality check
# =============================================================
def _quality_ok(gray_face: np.ndarray) -> tuple:
    """Returns (ok: bool, reason: str)."""
    if gray_face is None or gray_face.size == 0:
        return False, "no face"
    h, w = gray_face.shape[:2]
    if min(h, w) < 35:
        return False, "too small"
    blur = float(cv2.Laplacian(gray_face, cv2.CV_64F).var())
    if blur < 12:   # v9.1: slightly more tolerant
        return False, f"blurry {blur:.0f}"
    mean_br = float(np.mean(gray_face))
    if mean_br < 8:   # v9.1: dark faces can be as low as 10-15
        return False, f"dark {mean_br:.0f}"
    if mean_br > 248:
        return False, f"overexposed {mean_br:.0f}"
    return True, "ok"


# =============================================================
# UI overlay
# =============================================================
def _draw_ui(frame, pose_label, hint, count, target, face_rect,
             brightness, blur, recording):
    H, W = frame.shape[:2]
    out  = frame.copy()

    # Header
    cv2.rectangle(out, (0, 0), (W, 65), (25, 25, 25), -1)
    cv2.putText(out, pose_label, (10, 26),
                cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 210, 255), 1)
    cv2.putText(out, hint, (10, 54),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46, (190, 190, 190), 1)

    # Progress bar
    if target > 0:
        pct   = min(count / float(target), 1.0)
        bar_w = W - 20
        cv2.rectangle(out, (10, H-30), (10+bar_w, H-8), (50,50,50), -1)
        cv2.rectangle(out, (10, H-30), (10+int(bar_w*pct), H-8),
                      (0, 200, 80), -1)
        cv2.putText(out, f"Saved {count}/{target}", (14, H-34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220,220,220), 1)

    # Face rect
    if face_rect is not None:
        x, y, w, h = face_rect
        col = ((0,200,80) if blur > 60 else
               (0,165,255) if blur > 25 else (0,0,210))
        cv2.rectangle(out, (x, y), (x+w, y+h), col, 2)
        cv2.putText(out, f"blur={blur:.0f} br={brightness:.0f}",
                    (x, y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.40,
                    (255,255,255), 1)

    # Status line
    if recording:
        status = f"Recording ({count}/{target}) — ESC=stop"
        col_s  = (0, 255, 120)
    else:
        status = "SPACE = start recording   ESC = cancel"
        col_s  = (180, 180, 180)

    if brightness < 55:
        light_msg = "! Too dark — move to better light"
        light_col = (0, 60, 255)
    elif brightness < 85:
        light_msg = "Lighting: OK (brighter = better)"
        light_col = (0, 165, 255)
    else:
        light_msg = "Lighting: Good"
        light_col = (0, 200, 80)

    cv2.putText(out, light_msg, (10, H-36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, light_col, 1)
    cv2.putText(out, status, (10, H-56),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, col_s, 1)

    return out


# =============================================================
# Collect one pose
# =============================================================
CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def collect_pose(cap, pose_label, hint, student_dir, color_dir,
                 prefix, target=40):
    win = "Enrolment"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 720, 540)

    recording  = False
    count      = 0
    attempts   = 0
    max_att    = target * 12
    consecutive_fail = 0

    print(f"  Window open — press SPACE in the window to start, ESC to skip.")

    while True:
        # Read frame — non-blocking grab pattern to prevent freeze
        ret = cap.grab()
        if ret:
            ret, frame = cap.retrieve()
        else:
            frame = None

        if not ret or frame is None or frame.size == 0:
            consecutive_fail += 1
            if consecutive_fail > 30:
                print("  Camera stopped sending frames. Check USB connection.")
                break
            # Show placeholder
            blank = np.zeros((480, 640, 3), np.uint8)
            cv2.putText(blank, "Waiting for camera...",
                        (120, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 140, 255), 2)
            cv2.imshow(win, blank)
            key = cv2.waitKey(100) & 0xFF
            if key == 27:
                break
            continue

        consecutive_fail = 0

        # Preprocess for detection
        proc  = lighting.preprocess_frame(frame)
        gray  = cv2.cvtColor(proc, cv2.COLOR_BGR2GRAY)
        eq    = cv2.equalizeHist(gray)

        # v9.1: Multi-pass detection for dark skin
        _clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        cg     = _clahe.apply(gray)
        _t     = np.array([min(255, int(((i/255.0)**0.5)*255)) for i in range(256)], np.uint8)
        bright = cv2.LUT(cg, _t)
        faces  = []
        for _src, _sc, _nb in [(cg, 1.05, 2), (bright, 1.05, 2), (eq, 1.08, 3)]:
            _det = CASCADE.detectMultiScale(_src, scaleFactor=_sc,
                                             minNeighbors=_nb, minSize=(40, 40))
            if len(_det):
                faces = [tuple(r) for r in _det]
                break
        if not len(faces):
            faces = []

        face_rect  = None
        brightness = float(np.mean(gray))
        blur_val   = 0.0
        fh, fw     = frame.shape[:2]

        if len(faces):
            x, y, w, h = max(faces, key=lambda r: r[2]*r[3])
            face_rect   = (x, y, w, h)
            fg = gray[max(0,y):min(fh,y+h), max(0,x):min(fw,x+w)]
            if fg.size > 0:
                blur_val = float(cv2.Laplacian(fg, cv2.CV_64F).var())

            if recording:
                attempts += 1
                fc = proc[max(0,y):min(fh,y+h), max(0,x):min(fw,x+w)]
                good, _ = _quality_ok(fg)
                if good and fc.size > 0:
                    fname = f"{prefix}_p{count:04d}.jpg"
                    g_r   = cv2.resize(fg, (160, 160))
                    c_r   = cv2.resize(fc, (160, 160))
                    cv2.imwrite(os.path.join(student_dir, fname), g_r)
                    cv2.imwrite(os.path.join(color_dir,   fname), c_r)
                    count += 1
                    if count >= target:
                        break
                if attempts >= max_att:
                    print(f"  Max attempts reached. Saved {count}/{target}.")
                    break

        # Draw UI and display
        display = _draw_ui(frame, pose_label, hint, count, target,
                           face_rect, brightness, blur_val, recording)
        cv2.imshow(win, display)

        # CRITICAL: waitKey must be called to pump Windows events
        # Use 1ms so it never blocks but always processes events
        key = cv2.waitKey(1) & 0xFF

        if key == 27:               # ESC = skip this pose
            print("  Pose skipped.")
            break
        if key == 32 and not recording:  # SPACE = start
            recording = True
            print(f"  Recording... (target: {target} images)")

    cv2.destroyWindow(win)
    # Pump any remaining events
    for _ in range(5):
        cv2.waitKey(1)

    print(f"  Pose done: {count}/{target} images saved.")
    return count

    cv2.destroyWindow(win)
    print(f"    Done: {count}/{target} images saved.")
    return count


# =============================================================
# POSES
# =============================================================
POSES = [
    ("1/5  LOOK STRAIGHT",   "Face camera directly, chin level"),
    ("2/5  TURN HEAD LEFT",  "Slowly turn head left ~20 degrees"),
    ("3/5  TURN HEAD RIGHT", "Slowly turn head right ~20 degrees"),
    ("4/5  TILT HEAD UP",    "Tilt chin slightly upward"),
    ("5/5  TILT HEAD DOWN",  "Lower chin slightly toward chest"),
]


# =============================================================
# Main entry point
# =============================================================
def enroll_student():
    print("\n" + "=" * 55)
    print("  Student Enrolment  v9.1")
    print("=" * 55)
    print("  LIGHTING TIP: Face a window or lamp — not your back to it.")
    print("  For dark skin: extra light on face greatly helps accuracy.\n")

    name    = input("  Student Name   : ").strip()
    roll    = input("  Roll Number    : ").strip().lower()
    section = input("  Section (A/B)  : ").strip().upper() or "A"
    mobile  = input("  Mobile         : ").strip()
    twin_of = input("  Twin of (ID or blank): ").strip() or None

    if not name or not roll:
        print("  ERROR: Name and Roll Number are required.")
        return

    sid = f"STU_{roll.upper()}"
    print(f"\n  Student ID: {sid}")

    # Directories
    gray_dir  = os.path.join(config.DATASET_DIR,     sid)
    color_dir = os.path.join(config.KNOWN_FACES_DIR, sid)
    os.makedirs(gray_dir,  exist_ok=True)
    os.makedirs(color_dir, exist_ok=True)

    # DB
    ok = db.add_student(
        student_id=sid, name=name, roll_number=roll,
        mobile=mobile, section=section, twin_of=twin_of)
    if not ok:
        print("  INFO: Student already in DB — re-enrolling images.")

    # Open camera
    print("\n  Opening camera...")
    cap = _open_camera(config.CAMERA_INDEX)
    if cap is None:
        print("  ERROR: Could not open camera with any backend.")
        print("  Solutions:")
        print("    1. Close any app using the camera (Teams, Zoom, etc.)")
        print("    2. Set CAMERA_INDEX=1 in .env if you have two cameras")
        print("    3. Restart your PC and try again")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  Camera ready: {w}x{h}")
    print(f"  INSTRUCTIONS: A window will open for each pose.")
    print(f"  Press SPACE to start recording, ESC to skip a pose.\n")

    total = 0
    for i, (pose_name, hint) in enumerate(POSES):
        print(f"\n  === Pose {i+1}/5: {pose_name} ===")
        print(f"  {hint}")
        saved = collect_pose(
            cap       = cap,
            pose_label= f"{pose_name}",
            hint      = hint,
            student_dir= gray_dir,
            color_dir  = color_dir,
            prefix     = sid,
            target     = 40,
        )
        total += saved

    cap.release()
    cv2.destroyAllWindows()

    print(f"\n  Enrolment COMPLETE: {total} images for {name}")
    print(f"  Student ID: {sid}")
    if total < 100:
        print(f"  WARNING: Only {total} images collected (target=200).")
        print(f"  Consider re-enrolling for better accuracy.")
    print(f"  -> Run option [2] to train models.\n")