# # =============================================================
# # api.py  —  Smart Attendance System  v9.6
# #
# # INTEGRATION CHANGES v9.6 (frontend bridge):
# #   - All existing v9.5 endpoints kept 100% intact
# #   - Added /api/* bridge routes consumed by the EduTrack
# #     frontend (index.html / app.js):
# #
# #     POST /api/login          → wraps /auth/login, returns role
# #     GET  /api/students        → get_all_students()
# #     POST /api/students        → add_student()
# #     DELETE /api/students/{id} → delete_student_data()
# #     GET  /api/attendance/today→ get_today_attendance()
# #     GET  /api/attendance/summary → get_attendance_summary()
# #     POST /api/attendance/override → teacher_override()
# #     GET  /api/session/status  → session status + marked list
# #     POST /api/session/start   → start face recognition thread
# #     POST /api/session/stop    → stop face recognition thread
# #     POST /api/train           → kick off LBPH+dlib training
# #     GET  /api/timetable       → period list
# #     GET  /api/settings        → config thresholds
# #     POST /api/settings        → update config thresholds
# #     GET  /api/analytics/summary → kpi summary object
# #     GET  /api/export/csv      → CSV download
# #     GET  /video_feed          → MJPEG stream (unchanged)
# #     GET  /app                 → serves frontend/index.html
# #
# # DATABASE: SQLite via database.py — single source of truth.
# # =============================================================

# import os
# import sys
# import time
# import hmac
# import hashlib
# import base64
# import json
# import logging
# import threading
# import platform
# import signal
# from datetime import datetime

# try:
#     from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
#     from fastapi.middleware.cors import CORSMiddleware
#     from fastapi.responses import (FileResponse, HTMLResponse,
#                                    StreamingResponse, JSONResponse)
#     from fastapi.staticfiles import StaticFiles
#     from pydantic import BaseModel
#     import uvicorn
#     FASTAPI_OK = True
# except ImportError:
#     FASTAPI_OK = False

# JWT_OK = False
# try:
#     import jwt as _jwt
#     _jwt.encode({"t": 1}, "k", algorithm="HS256")
#     JWT_OK = True
# except Exception:
#     pass

# import config
# import database as db          # SQLite — single source of truth
# import attendance_session as _sess

# log = logging.getLogger(__name__)
# PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


# # =============================================================
# # TOKEN HELPERS  (unchanged from v9.5)
# # =============================================================
# def _make_token(payload: dict) -> str:
#     data_b = base64.urlsafe_b64encode(
#         json.dumps(payload, separators=(",", ":")).encode()).decode()
#     sig = hmac.new(config.API_SECRET_KEY.encode(),
#                    data_b.encode(), hashlib.sha256).hexdigest()
#     return f"{data_b}.{sig}"


# def _verify_token(token: str) -> dict:
#     try:
#         data_b, sig = token.split(".")
#         expected = hmac.new(config.API_SECRET_KEY.encode(),
#                             data_b.encode(), hashlib.sha256).hexdigest()
#         if not hmac.compare_digest(sig, expected):
#             raise ValueError("invalid signature")
#         data = json.loads(base64.urlsafe_b64decode(data_b).decode())
#         if data.get("exp", 0) < time.time():
#             raise ValueError("token expired")
#         return data
#     except Exception as e:
#         raise HTTPException(status_code=401,
#                             detail=f"Invalid token: {e}")


# def create_access_token(username: str, role: str) -> str:
#     payload = {
#         "sub":  username,
#         "role": role,
#         "exp":  time.time() + config.API_TOKEN_EXPIRY_HOURS * 3600,
#         "iat":  time.time(),
#     }
#     if JWT_OK:
#         try:
#             return _jwt.encode(payload, config.API_SECRET_KEY,
#                                algorithm="HS256")
#         except Exception:
#             pass
#     return _make_token(payload)


# def decode_token(token: str) -> dict:
#     if JWT_OK:
#         try:
#             return _jwt.decode(token, config.API_SECRET_KEY,
#                                algorithms=["HS256"])
#         except Exception:
#             pass
#     return _verify_token(token)


# def _uname(user: dict) -> str:
#     return user.get("sub") or user.get("username") or "system"


# # =============================================================
# # PYDANTIC MODELS
# # =============================================================
# class LoginReq(BaseModel):
#     username: str
#     password: str


# class StartSessionReq(BaseModel):
#     period: str


# class OverrideReq(BaseModel):
#     student_id: str
#     period:     str
#     action:     str
#     note:       str = ""


# class AddStudentReq(BaseModel):
#     name:        str
#     roll_number: str
#     section:     str = "A"
#     mobile:      str = ""
#     twin_of:     str = None


# # Frontend-specific models
# class FrontendLoginReq(BaseModel):
#     email:    str = ""
#     password: str
#     role:     str = "admin"
#     fac_id:   str = ""


# class FrontendOverrideReq(BaseModel):
#     student_id:  str
#     period:      str
#     action:      str        # mark_present | mark_absent | mark_late | mark_od
#     reason:      str = ""
#     modifier_id: str = ""
#     category:    str = ""


# # =============================================================
# # TRAINING BACKGROUND TASK
# # =============================================================
# _train_state = {"running": False, "done": False, "error": "", "log": []}

# def _run_training_bg():
#     global _train_state
#     _train_state["running"] = True
#     _train_state["done"]    = False
#     _train_state["error"]   = ""
#     _train_state["log"]     = []
#     try:
#         import io, contextlib
#         buf = io.StringIO()
#         with contextlib.redirect_stdout(buf):
#             from train import train_all
#             train_all()
#         _train_state["log"] = buf.getvalue().split("\n")
#         _train_state["done"] = True
#     except Exception as e:
#         _train_state["error"] = str(e)
#         _train_state["done"]  = True
#     finally:
#         _train_state["running"] = False


# # =============================================================
# # APP FACTORY
# # =============================================================
# def create_app():
#     if not FASTAPI_OK:
#         raise ImportError(
#             "FastAPI not installed. Run: pip install fastapi uvicorn")

#     app = FastAPI(title="Smart Attendance API v9.6", version="9.6")

#     app.add_middleware(
#         CORSMiddleware,
#         allow_origins=["*"],
#         allow_credentials=True,
#         allow_methods=["*"],
#         allow_headers=["*"],
#     )

#     # ── Auth dependencies ─────────────────────────────────────
#     def get_current_user(request: Request) -> dict:
#         auth = request.headers.get("Authorization", "")
#         if not auth.startswith("Bearer "):
#             raise HTTPException(status_code=401,
#                                 detail="No token provided")
#         return decode_token(auth[7:])

#     def teacher_required(
#             user: dict = Depends(get_current_user)) -> dict:
#         if user.get("role") not in ("admin", "teacher", "hod",
#                                     "classincharge", "faculty"):
#             raise HTTPException(status_code=403,
#                                 detail="Teacher access required")
#         return user

#     def admin_required(
#             user: dict = Depends(get_current_user)) -> dict:
#         if user.get("role") not in ("admin", "hod"):
#             raise HTTPException(status_code=403,
#                                 detail="Admin access required")
#         return user

#     # =========================================================
#     # ORIGINAL v9.5 ENDPOINTS (unchanged)
#     # =========================================================

#     @app.get("/health")
#     def health():
#         return {"status": "ok", "version": "9.6"}

#     @app.post("/auth/login")
#     def login(req: LoginReq, request: Request):
#         ip   = request.client.host if request.client else "?"
#         role = None
#         if (req.username == config.ADMIN_USERNAME and
#                 req.password == config.ADMIN_PASSWORD):
#             role = "admin"
#         elif (req.username == config.TEACHER_USERNAME and
#               req.password == config.TEACHER_PASSWORD):
#             role = "teacher"
#         if not role:
#             db.log_audit(req.username, "login_fail", "", "", ip)
#             raise HTTPException(status_code=401,
#                                 detail="Invalid credentials")
#         token = create_access_token(req.username, role)
#         db.log_audit(req.username, "login_ok", "", role, ip)
#         return {"access_token": token, "token_type": "bearer",
#                 "role": role}

#     @app.get("/students")
#     def list_students(_: dict = Depends(get_current_user)):
#         return db.get_all_students()

#     @app.post("/students")
#     def add_student(req: AddStudentReq, request: Request,
#                     user: dict = Depends(teacher_required)):
#         sid = f"STU_{req.roll_number.upper()}"
#         ok  = db.add_student(
#             student_id=sid, name=req.name,
#             roll_number=req.roll_number.lower(),
#             section=req.section, mobile=req.mobile,
#             twin_of=req.twin_of)
#         db.log_audit(_uname(user), "add_student", sid, req.name,
#                      request.client.host if request.client else "?")
#         if not ok:
#             raise HTTPException(status_code=409,
#                                 detail="Student already exists")
#         return {"student_id": sid, "status": "created"}

#     @app.delete("/students/{student_id}")
#     def delete_student(student_id: str, request: Request,
#                        user: dict = Depends(admin_required)):
#         db.delete_student_data(student_id)
#         db.log_audit(_uname(user), "delete_student", student_id,
#                      "", request.client.host if request.client else "?")
#         return {"status": "deactivated"}

#     @app.get("/attendance/today")
#     def today(period: str = None,
#               _: dict = Depends(get_current_user)):
#         return db.get_today_attendance(period)

#     @app.get("/attendance/summary")
#     def summary(days: int = 30,
#                 _: dict = Depends(get_current_user)):
#         return db.get_attendance_summary(days)

#     @app.post("/attendance/override")
#     def override(req: OverrideReq, request: Request,
#                  user: dict = Depends(teacher_required)):
#         db.teacher_override(req.student_id, req.period,
#                             req.action, req.note)
#         db.log_audit(_uname(user), "override",
#                      req.student_id, req.action,
#                      request.client.host if request.client else "?")
#         return {"status": "done"}

#     @app.get("/attendance/yesterday")
#     def yesterday(period: str = None,
#                   _: dict = Depends(get_current_user)):
#         from datetime import timedelta
#         d = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
#         return db.get_attendance_by_date(d, period)

#     @app.get("/attendance/date/{date_str}")
#     def by_date(date_str: str, period: str = None,
#                 _: dict = Depends(get_current_user)):
#         return db.get_attendance_by_date(date_str, period)

#     @app.get("/analytics/engine")
#     def engine_stats(days: int = 7,
#                      _: dict = Depends(get_current_user)):
#         return db.get_engine_stats(days)

#     @app.get("/analytics/period")
#     def period_stats(_: dict = Depends(get_current_user)):
#         return db.get_period_stats()

#     @app.get("/analytics/twins")
#     def twin_log(days: int = 7,
#                  _: dict = Depends(get_current_user)):
#         return db.get_twin_analysis_log(days)

#     @app.get("/timetable")
#     def timetable(_: dict = Depends(get_current_user)):
#         return db.get_timetable()

#     @app.get("/settings")
#     def get_settings(_: dict = Depends(get_current_user)):
#         return {
#             "LBPH_THRESHOLD":          config.LBPH_THRESHOLD,
#             "DLIB_DISTANCE":           config.DLIB_DISTANCE,
#             "MIN_CONFIDENCE_PCT":      config.MIN_CONFIDENCE_PCT,
#             "CONFIRM_FRAMES_REQUIRED": config.CONFIRM_FRAMES_REQUIRED,
#             "LIVENESS_THRESHOLD":      config.LIVENESS_THRESHOLD,
#             "LIVENESS_ON":             config.LIVENESS_ON,
#             "CAMERA_INDEX":            config.CAMERA_INDEX,
#         }

#     @app.post("/settings")
#     def save_settings(data: dict,
#                       user: dict = Depends(admin_required)):
#         for key, cast in {
#             "LBPH_THRESHOLD": float,
#             "DLIB_DISTANCE": float,
#             "MIN_CONFIDENCE_PCT": float,
#             "CONFIRM_FRAMES_REQUIRED": int,
#             "LIVENESS_THRESHOLD": float,
#             "LIVENESS_ON": bool,
#             "CAMERA_INDEX": int,
#         }.items():
#             if key in data:
#                 setattr(config, key, cast(data[key]))
#         return {"status": "ok"}

#     @app.get("/export/csv")
#     def export_csv(_: dict = Depends(get_current_user)):
#         import csv, io
#         today_str = datetime.now().strftime("%Y-%m-%d")
#         rows      = db.get_today_attendance()
#         out       = io.StringIO()
#         w = csv.DictWriter(out, fieldnames=[
#             "name", "roll_number", "period", "date",
#             "time", "confidence", "engine"])
#         w.writeheader()
#         for r in rows:
#             w.writerow({k: r.get(k, "") for k in w.fieldnames})
#         out.seek(0)
#         return StreamingResponse(
#             iter([out.read()]),
#             media_type="text/csv",
#             headers={"Content-Disposition":
#                      f"attachment; filename=attendance_{today_str}.csv"})

#     @app.post("/session/start")
#     def session_start(req: StartSessionReq,
#                       user: dict = Depends(teacher_required)):
#         state = _sess._SESSION_STATE
#         t = state.get("thread")
#         if t and not t.is_alive():
#             state["running"] = False
#             state["thread"]  = None
#         if state["running"]:
#             raise HTTPException(
#                 status_code=409,
#                 detail="Session already running. Stop it first.")
#         period = req.period.strip()
#         if not period:
#             raise HTTPException(status_code=400,
#                                 detail="Period name is required")
#         result = _sess.start_session(period)
#         if not result["ok"]:
#             raise HTTPException(status_code=500,
#                                 detail=result.get("error", "Start failed"))
#         db.log_audit(_uname(user), "session_start", period)
#         return {
#             "status": "started",
#             "period": period,
#             "stream": f"http://localhost:{config.API_PORT}/video_feed",
#         }

#     @app.post("/session/stop")
#     def session_stop(user: dict = Depends(teacher_required)):
#         _sess.stop_session()
#         db.log_audit(_uname(user), "session_stop",
#                      _sess._SESSION_STATE.get("period", ""))
#         return {"status": "stopped"}

#     @app.get("/session/status")
#     def session_status(_: dict = Depends(get_current_user)):
#         state  = _sess.get_status()
#         period = state.get("period")
#         marked_rows: list = []
#         if period:
#             try:
#                 marked_rows = db.get_today_attendance(period) or []
#             except Exception:
#                 pass
#         already_marked = [
#             {
#                 "student_id": r.get("student_id", ""),
#                 "name":       r.get("name", ""),
#                 "time":       str(r.get("time", ""))[:8],
#                 "confidence": int(float(r.get("confidence", 0)) * 100),
#                 "engine":     r.get("engine", ""),
#             }
#             for r in marked_rows
#         ]
#         total_students = 0
#         try:
#             total_students = len(db.get_all_students())
#         except Exception:
#             pass
#         return {
#             "running":        state.get("running", False),
#             "period":         period,
#             "started_at":     state.get("started_at"),
#             "marked_count":   len(marked_rows),
#             "total_students": total_students,
#             "absent_count":   max(0, total_students - len(marked_rows)),
#             "already_marked": already_marked,
#             "error":          state.get("error") or "",
#         }

#     @app.get("/video_feed")
#     def video_feed():
#         return StreamingResponse(
#             _sess.generate_frames(),
#             media_type="multipart/x-mixed-replace; boundary=frame",
#             headers={
#                 "Cache-Control": "no-cache, no-store, must-revalidate",
#                 "Pragma":        "no-cache",
#                 "Expires":       "0",
#             }
#         )

#     # =========================================================
#     # /api/* BRIDGE ENDPOINTS  (new in v9.6 — for EduTrack frontend)
#     # =========================================================

#     # ── Login ─────────────────────────────────────────────────
#     @app.post("/api/login")
#     def api_login(req: FrontendLoginReq, request: Request):
#         """
#         Accepts the EduTrack frontend login payload.
#         Admin/HOD/ClassIncharge log in with email + password.
#         Faculty log in with fac_id + password (checked against
#         students table where student_id starts with 'FAC').
#         Returns JWT token + role for the frontend to store.
#         """
#         ip = request.client.host if request.client else "?"
#         role = None
#         username = ""

#         # Faculty portal login (fac_id provided)
#         if req.fac_id:
#             fac = db.get_student(req.fac_id)
#             if fac and req.password == "fac@2025":   # dev default
#                 token = create_access_token(req.fac_id, "faculty")
#                 db.log_audit(req.fac_id, "login_ok", "", "faculty", ip)
#                 return {
#                     "access_token": token, "token_type": "bearer",
#                     "role": "faculty",
#                     "fac_id": req.fac_id,
#                     "name": fac.get("name", req.fac_id),
#                 }
#             db.log_audit(req.fac_id, "login_fail", "", "faculty", ip)
#             raise HTTPException(status_code=401,
#                                 detail="Invalid Faculty ID or password")

#         # Admin portal login
#         email = req.email.strip().lower()
#         if (email == config.ADMIN_USERNAME.lower() or
#                 email == f"{config.ADMIN_USERNAME.lower()}@college.edu"):
#             if req.password == config.ADMIN_PASSWORD:
#                 role = req.role if req.role in ("admin","hod","classincharge") else "admin"
#                 username = config.ADMIN_USERNAME
#         elif (email == config.TEACHER_USERNAME.lower() or
#                 email == f"{config.TEACHER_USERNAME.lower()}@college.edu"):
#             if req.password == config.TEACHER_PASSWORD:
#                 role = "teacher"
#                 username = config.TEACHER_USERNAME

#         # Also accept password-only for demo (any email + correct password)
#         if not role:
#             if req.password == config.ADMIN_PASSWORD:
#                 role = req.role if req.role in ("admin","hod","classincharge") else "admin"
#                 username = req.email or config.ADMIN_USERNAME
#             elif req.password == config.TEACHER_PASSWORD:
#                 role = "teacher"
#                 username = req.email or config.TEACHER_USERNAME

#         if not role:
#             db.log_audit(req.email, "login_fail", "", "", ip)
#             raise HTTPException(status_code=401,
#                                 detail="Invalid credentials")

#         token = create_access_token(username, role)
#         db.log_audit(username, "login_ok", "", role, ip)
#         return {
#             "access_token": token, "token_type": "bearer",
#             "role": role, "username": username,
#         }

#     # ── Students ──────────────────────────────────────────────
#     @app.get("/api/students")
#     def api_list_students(_: dict = Depends(get_current_user)):
#         rows = db.get_all_students()
#         # Convert Row objects to plain dicts
#         return [dict(r) for r in rows]

#     @app.post("/api/students")
#     def api_add_student(req: AddStudentReq, request: Request,
#                         user: dict = Depends(teacher_required)):
#         sid = f"STU_{req.roll_number.upper()}"
#         ok  = db.add_student(
#             student_id=sid, name=req.name,
#             roll_number=req.roll_number.lower(),
#             section=req.section, mobile=req.mobile,
#             twin_of=req.twin_of)
#         db.log_audit(_uname(user), "add_student", sid, req.name,
#                      request.client.host if request.client else "?")
#         if not ok:
#             raise HTTPException(status_code=409,
#                                 detail="Student already exists")
#         return {"student_id": sid, "status": "created",
#                 "message": f"Student {req.name} added. Run training to enrol face."}

#     @app.delete("/api/students/{student_id}")
#     def api_delete_student(student_id: str, request: Request,
#                            user: dict = Depends(admin_required)):
#         db.delete_student_data(student_id)
#         db.log_audit(_uname(user), "delete_student", student_id,
#                      "", request.client.host if request.client else "?")
#         return {"status": "deactivated", "student_id": student_id}

#     # ── Attendance ────────────────────────────────────────────
#     @app.get("/api/attendance/today")
#     def api_today(period: str = None,
#                   _: dict = Depends(get_current_user)):
#         rows = db.get_today_attendance(period)
#         return [dict(r) for r in rows]

#     @app.get("/api/attendance/summary")
#     def api_summary(days: int = 30,
#                     _: dict = Depends(get_current_user)):
#         rows = db.get_attendance_summary(days)
#         return [dict(r) for r in rows]

#     @app.get("/api/attendance/date/{date_str}")
#     def api_by_date(date_str: str, period: str = None,
#                     _: dict = Depends(get_current_user)):
#         rows = db.get_attendance_by_date(date_str, period)
#         return [dict(r) for r in rows]

#     @app.post("/api/attendance/override")
#     def api_override(req: FrontendOverrideReq, request: Request,
#                      user: dict = Depends(teacher_required)):
#         """
#         Frontend override — supports richer payload from EduTrack UI.
#         Internally maps to the same db.teacher_override() call.
#         """
#         note = req.reason
#         if req.category and req.category != "—":
#             note = f"[{req.category}] {note}".strip()
#         if req.modifier_id:
#             note = f"{note} (by {req.modifier_id})".strip()

#         db.teacher_override(req.student_id, req.period,
#                             req.action, note)
#         db.log_audit(
#             _uname(user), "override",
#             req.student_id,
#             f"{req.action} — {note}",
#             request.client.host if request.client else "?")
#         return {"status": "done", "message": "Override saved to database"}

#     # ── Session ───────────────────────────────────────────────
#     @app.post("/api/session/start")
#     def api_session_start(req: StartSessionReq,
#                           user: dict = Depends(teacher_required)):
#         state = _sess._SESSION_STATE
#         t = state.get("thread")
#         if t and not t.is_alive():
#             state["running"] = False
#             state["thread"]  = None
#         if state["running"]:
#             raise HTTPException(
#                 status_code=409,
#                 detail="Session already running. Stop it first.")
#         period = req.period.strip()
#         if not period:
#             raise HTTPException(status_code=400,
#                                 detail="Period name is required")
#         result = _sess.start_session(period)
#         if not result["ok"]:
#             raise HTTPException(status_code=500,
#                                 detail=result.get("error", "Start failed"))
#         db.log_audit(_uname(user), "api_session_start", period)
#         port = config.API_PORT
#         return {
#             "status":  "started",
#             "period":  period,
#             "stream":  f"/video_feed",
#             "message": f"Camera session started for {period}",
#         }

#     @app.post("/api/session/stop")
#     def api_session_stop(user: dict = Depends(teacher_required)):
#         _sess.stop_session()
#         db.log_audit(_uname(user), "api_session_stop",
#                      _sess._SESSION_STATE.get("period", ""))
#         return {"status": "stopped", "message": "Session stopped"}

#     @app.get("/api/session/status")
#     def api_session_status(_: dict = Depends(get_current_user)):
#         state  = _sess.get_status()
#         period = state.get("period")
#         marked_rows: list = []
#         if period:
#             try:
#                 marked_rows = db.get_today_attendance(period) or []
#             except Exception:
#                 pass
#         already_marked = [
#             {
#                 "student_id": r.get("student_id", ""),
#                 "name":       r.get("name", ""),
#                 "time":       str(r.get("time", ""))[:8],
#                 "confidence": int(float(r.get("confidence", 0)) * 100),
#                 "engine":     r.get("engine", ""),
#             }
#             for r in marked_rows
#         ]
#         total_students = 0
#         try:
#             total_students = len(db.get_all_students())
#         except Exception:
#             pass
#         return {
#             "running":        state.get("running", False),
#             "period":         period,
#             "started_at":     state.get("started_at"),
#             "marked_count":   len(marked_rows),
#             "total_students": total_students,
#             "absent_count":   max(0, total_students - len(marked_rows)),
#             "already_marked": already_marked,
#             "error":          state.get("error") or "",
#         }

#     # ── Training ──────────────────────────────────────────────
#     @app.post("/api/train")
#     def api_train(background_tasks: BackgroundTasks,
#                   user: dict = Depends(admin_required)):
#         """
#         Kicks off LBPH + dlib training in a background thread.
#         Returns immediately; poll /api/train/status to check progress.
#         """
#         if _train_state["running"]:
#             return {"status": "already_running",
#                     "message": "Training is already in progress"}
#         background_tasks.add_task(_run_training_bg)
#         return {"status": "started",
#                 "message": "Training started in background. Poll /api/train/status"}

#     @app.get("/api/train/status")
#     def api_train_status(_: dict = Depends(get_current_user)):
#         return {
#             "running": _train_state["running"],
#             "done":    _train_state["done"],
#             "error":   _train_state["error"],
#             "log":     _train_state["log"][-20:],   # last 20 lines
#         }

#     # ── Analytics ─────────────────────────────────────────────
#     @app.get("/api/analytics/summary")
#     def api_analytics_summary(_: dict = Depends(get_current_user)):
#         """
#         Returns a single object with all KPI numbers the
#         EduTrack dashboard needs: total students, today present,
#         avg attendance, engine stats, etc.
#         """
#         students     = db.get_all_students()
#         today_rows   = db.get_today_attendance()
#         summary_rows = db.get_attendance_summary(30)
#         engine_rows  = db.get_engine_stats(7)
#         period_rows  = db.get_period_stats()

#         total_students = len(students)
#         present_today  = len(today_rows)
#         absent_today   = max(0, total_students - present_today)
#         pct_today      = round(present_today / total_students * 100, 1) if total_students else 0

#         # Avg from summary
#         pcts = []
#         for r in summary_rows:
#             pc = r.get("present_count", 0)
#             td = r.get("total_days", 1) or 1
#             pcts.append(pc / td * 100)
#         avg_att = round(sum(pcts) / len(pcts), 1) if pcts else 0

#         # Critical students (<65%)
#         critical = [r for r in summary_rows
#                     if (r.get("present_count", 0) / (r.get("total_days", 1) or 1)) < 0.65]

#         return {
#             "total_students":  total_students,
#             "present_today":   present_today,
#             "absent_today":    absent_today,
#             "pct_today":       pct_today,
#             "avg_attendance":  avg_att,
#             "critical_count":  len(critical),
#             "critical_students": [dict(r) for r in critical],
#             "engine_stats":    [dict(r) for r in engine_rows],
#             "period_stats":    [dict(r) for r in period_rows],
#         }

#     @app.get("/api/analytics/engine")
#     def api_engine_stats(days: int = 7,
#                          _: dict = Depends(get_current_user)):
#         return [dict(r) for r in db.get_engine_stats(days)]

#     @app.get("/api/analytics/period")
#     def api_period_stats(_: dict = Depends(get_current_user)):
#         return [dict(r) for r in db.get_period_stats()]

#     @app.get("/api/analytics/twins")
#     def api_twin_log(days: int = 7,
#                      _: dict = Depends(get_current_user)):
#         return [dict(r) for r in db.get_twin_analysis_log(days)]

#     # ── Timetable ─────────────────────────────────────────────
#     @app.get("/api/timetable")
#     def api_timetable(_: dict = Depends(get_current_user)):
#         rows = db.get_timetable()
#         return [dict(r) for r in rows]

#     # ── Settings ──────────────────────────────────────────────
#     @app.get("/api/settings")
#     def api_get_settings(_: dict = Depends(get_current_user)):
#         return {
#             "LBPH_THRESHOLD":          config.LBPH_THRESHOLD,
#             "DLIB_DISTANCE":           config.DLIB_DISTANCE,
#             "MIN_CONFIDENCE_PCT":      config.MIN_CONFIDENCE_PCT,
#             "CONFIRM_FRAMES_REQUIRED": config.CONFIRM_FRAMES_REQUIRED,
#             "LIVENESS_THRESHOLD":      config.LIVENESS_THRESHOLD,
#             "LIVENESS_ON":             config.LIVENESS_ON,
#             "CAMERA_INDEX":            config.CAMERA_INDEX,
#         }

#     @app.post("/api/settings")
#     def api_save_settings(data: dict,
#                           user: dict = Depends(admin_required)):
#         for key, cast in {
#             "LBPH_THRESHOLD": float,
#             "DLIB_DISTANCE": float,
#             "MIN_CONFIDENCE_PCT": float,
#             "CONFIRM_FRAMES_REQUIRED": int,
#             "LIVENESS_THRESHOLD": float,
#             "LIVENESS_ON": bool,
#             "CAMERA_INDEX": int,
#         }.items():
#             if key in data:
#                 setattr(config, key, cast(data[key]))
#         return {"status": "ok", "message": "Settings updated"}

#     # ── Export ────────────────────────────────────────────────
#     @app.get("/api/export/csv")
#     def api_export_csv(period: str = None,
#                        _: dict = Depends(get_current_user)):
#         import csv, io
#         today_str = datetime.now().strftime("%Y-%m-%d")
#         rows      = db.get_today_attendance(period)
#         out       = io.StringIO()
#         w = csv.DictWriter(out, fieldnames=[
#             "name", "student_id", "period", "date",
#             "time", "confidence", "engine"])
#         w.writeheader()
#         for r in rows:
#             w.writerow({k: r.get(k, "") for k in w.fieldnames})
#         out.seek(0)
#         return StreamingResponse(
#             iter([out.read()]),
#             media_type="text/csv",
#             headers={"Content-Disposition":
#                      f"attachment; filename=attendance_{today_str}.csv"})

#     # ── Frontend static files ─────────────────────────────────
#     frontend_dir = os.path.join(config.BASE_DIR, "frontend")
#     if os.path.isdir(frontend_dir):
#         # Serve frontend/style.css and frontend/app.js at /style.css, /app.js
#         @app.get("/style.css")
#         def serve_css():
#             p = os.path.join(frontend_dir, "style.css")
#             return FileResponse(p, media_type="text/css") if os.path.exists(p) else HTMLResponse("", 404)

#         @app.get("/app.js")
#         def serve_js():
#             p = os.path.join(frontend_dir, "app.js")
#             return FileResponse(p, media_type="application/javascript") if os.path.exists(p) else HTMLResponse("", 404)

#         @app.get("/app", response_class=HTMLResponse)
#         @app.get("/", response_class=HTMLResponse)
#         def frontend():
#             idx = os.path.join(frontend_dir, "index.html")
#             if os.path.exists(idx):
#                 return FileResponse(idx)
#             return HTMLResponse(
#                 "<h2>Frontend not found</h2>"
#                 f"<p>Expected: {idx}</p>"
#                 "<p>Place index.html, style.css, app.js inside the "
#                 "<code>frontend/</code> folder.</p>")

#     return app


# # =============================================================
# # ENTRY POINT  (called from main.py option 4)
# # =============================================================
# def run_api():
#     if not FASTAPI_OK:
#         print("  ERROR: pip install fastapi uvicorn")
#         return

#     app = create_app()

#     import socket
#     port = config.API_PORT
#     for p in [port, port+1, port+2, 8080, 8888, 9000]:
#         try:
#             with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#                 s.bind(("", p))
#             port = p
#             break
#         except OSError:
#             continue
#     else:
#         print("  ERROR: No free port. Kill old server and retry.")
#         return

#     if port != config.API_PORT:
#         print(f"  [INFO] Port {config.API_PORT} busy — using {port}")

#     print(f"\n  ┌──────────────────────────────────────────────────────┐")
#     print(f"  │  EduTrack Pro  ·  Smart Attendance System  v9.6      │")
#     print(f"  │                                                        │")
#     print(f"  │  Dashboard  : http://localhost:{port}/app             │")
#     print(f"  │  API Docs   : http://localhost:{port}/docs            │")
#     print(f"  │  Video Feed : http://localhost:{port}/video_feed      │")
#     print(f"  │                                                        │")
#     print(f"  │  Admin login  : admin / admin123                      │")
#     print(f"  │  Teacher login: teacher / teacher123                  │")
#     print(f"  │  Press Ctrl+C to stop                                 │")
#     print(f"  └──────────────────────────────────────────────────────┘\n")

#     try:
#         uvicorn.run(app, host=config.API_HOST, port=port,
#                     log_level="warning")
#     except OSError as e:
#         print(f"\n  ERROR: {e}")
#         print(f"  Kill the process using port {port} and retry.")



# =============================================================
# api.py  —  Smart Attendance System  v9.6
#
# INTEGRATION CHANGES v9.6 (frontend bridge):
#   - All existing v9.5 endpoints kept 100% intact
#   - Added /api/* bridge routes consumed by the EduTrack
#     frontend (index.html / app.js):
#
#     POST /api/login          → wraps /auth/login, returns role
#     GET  /api/students        → get_all_students()
#     POST /api/students        → add_student()
#     DELETE /api/students/{id} → delete_student_data()
#     GET  /api/attendance/today→ get_today_attendance()
#     GET  /api/attendance/summary → get_attendance_summary()
#     POST /api/attendance/override → teacher_override()
#     GET  /api/session/status  → session status + marked list
#     POST /api/session/start   → start face recognition thread
#     POST /api/session/stop    → stop face recognition thread
#     POST /api/train           → kick off LBPH+dlib training
#     GET  /api/timetable       → period list
#     GET  /api/settings        → config thresholds
#     POST /api/settings        → update config thresholds
#     GET  /api/analytics/summary → kpi summary object
#     GET  /api/export/csv      → CSV download
#     GET  /video_feed          → MJPEG stream (unchanged)
#     GET  /app                 → serves frontend/index.html
#
# DATABASE: SQLite via database.py — single source of truth.
# =============================================================

import os
import sys
import time
import hmac
import hashlib
import base64
import json
import logging
import threading
import platform
import signal

from datetime import datetime
from pydantic import BaseModel

try:
    from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import (FileResponse, HTMLResponse,
                                   StreamingResponse, JSONResponse)
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False

JWT_OK = False
try:
    import jwt as _jwt
    _jwt.encode({"t": 1}, "k", algorithm="HS256")
    JWT_OK = True
except Exception:
    pass

import config
import database as db          # SQLite — single source of truth
import attendance_session as _sess

log = logging.getLogger(__name__)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


# =============================================================
# TOKEN HELPERS  (unchanged from v9.5)
# =============================================================
def _make_token(payload: dict) -> str:
    data_b = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(config.API_SECRET_KEY.encode(),
                   data_b.encode(), hashlib.sha256).hexdigest()
    return f"{data_b}.{sig}"


def _verify_token(token: str) -> dict:
    try:
        data_b, sig = token.split(".")
        expected = hmac.new(config.API_SECRET_KEY.encode(),
                            data_b.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("invalid signature")
        data = json.loads(base64.urlsafe_b64decode(data_b).decode())
        if data.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return data
    except Exception as e:
        raise HTTPException(status_code=401,
                            detail=f"Invalid token: {e}")


def create_access_token(username: str, role: str) -> str:
    payload = {
        "sub":  username,
        "role": role,
        "exp":  time.time() + config.API_TOKEN_EXPIRY_HOURS * 3600,
        "iat":  time.time(),
    }
    if JWT_OK:
        try:
            return _jwt.encode(payload, config.API_SECRET_KEY,
                               algorithm="HS256")
        except Exception:
            pass
    return _make_token(payload)


def decode_token(token: str) -> dict:
    if JWT_OK:
        try:
            return _jwt.decode(token, config.API_SECRET_KEY,
                               algorithms=["HS256"])
        except Exception:
            pass
    return _verify_token(token)


def _uname(user: dict) -> str:
    return user.get("sub") or user.get("username") or "system"


# =============================================================
# PYDANTIC MODELS
# =============================================================
class LoginReq(BaseModel):
    username: str
    password: str


class StartSessionReq(BaseModel):
    period: str


class OverrideReq(BaseModel):
    student_id: str
    period:     str
    action:     str
    note:       str = ""


class AddStudentReq(BaseModel):
    name:        str
    roll_number: str
    section:     str = "A"
    mobile:      str = ""
    twin_of:     str = None


# Frontend-specific models
class FrontendLoginReq(BaseModel):
    email:    str = ""
    password: str
    role:     str = "admin"
    fac_id:   str = ""


class FrontendOverrideReq(BaseModel):
    student_id:  str
    period:      str
    action:      str        # mark_present | mark_absent | mark_late | mark_od
    reason:      str = ""
    modifier_id: str = ""
    category:    str = ""


# =============================================================
# TRAINING BACKGROUND TASK
# =============================================================
_train_state = {"running": False, "done": False, "error": "", "log": []}

def _run_training_bg():
    global _train_state
    _train_state["running"] = True
    _train_state["done"]    = False
    _train_state["error"]   = ""
    _train_state["log"]     = []
    try:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            from train import train_all
            train_all()
        _train_state["log"] = buf.getvalue().split("\n")
        _train_state["done"] = True
    except Exception as e:
        _train_state["error"] = str(e)
        _train_state["done"]  = True
    finally:
        _train_state["running"] = False


# =============================================================
# APP FACTORY
# =============================================================
def create_app():
    if not FASTAPI_OK:
        raise ImportError(
            "FastAPI not installed. Run: pip install fastapi uvicorn")

    app = FastAPI(title="Smart Attendance API v9.6", version="9.6")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth dependencies ─────────────────────────────────────
    def get_current_user(request: Request) -> dict:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401,
                                detail="No token provided")
        return decode_token(auth[7:])

    def teacher_required(
            user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in ("admin", "teacher", "hod",
                                    "classincharge", "faculty"):
            raise HTTPException(status_code=403,
                                detail="Teacher access required")
        return user

    def admin_required(
            user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in ("admin", "hod"):
            raise HTTPException(status_code=403,
                                detail="Admin access required")
        return user

    # =========================================================
    # ORIGINAL v9.5 ENDPOINTS (unchanged)
    # =========================================================

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "9.6"}

    @app.post("/auth/login")
    def login(req: LoginReq, request: Request):
        ip   = request.client.host if request.client else "?"
        role = None
        if (req.username == config.ADMIN_USERNAME and
                req.password == config.ADMIN_PASSWORD):
            role = "admin"
        elif (req.username == config.TEACHER_USERNAME and
              req.password == config.TEACHER_PASSWORD):
            role = "teacher"
        if not role:
            db.log_audit(req.username, "login_fail", "", "", ip)
            raise HTTPException(status_code=401,
                                detail="Invalid credentials")
        token = create_access_token(req.username, role)
        db.log_audit(req.username, "login_ok", "", role, ip)
        return {"access_token": token, "token_type": "bearer",
                "role": role}

    @app.get("/students")
    def list_students(_: dict = Depends(get_current_user)):
        return db.get_all_students()

    @app.post("/students")
    def add_student(req: AddStudentReq, request: Request,
                    user: dict = Depends(teacher_required)):
        sid = f"STU_{req.roll_number.upper()}"
        ok  = db.add_student(
            student_id=sid, name=req.name,
            roll_number=req.roll_number.lower(),
            section=req.section, mobile=req.mobile,
            twin_of=req.twin_of)
        db.log_audit(_uname(user), "add_student", sid, req.name,
                     request.client.host if request.client else "?")
        if not ok:
            raise HTTPException(status_code=409,
                                detail="Student already exists")
        return {"student_id": sid, "status": "created"}

    @app.delete("/students/{student_id}")
    def delete_student(student_id: str, request: Request,
                       user: dict = Depends(admin_required)):
        db.delete_student_data(student_id)
        db.log_audit(_uname(user), "delete_student", student_id,
                     "", request.client.host if request.client else "?")
        return {"status": "deactivated"}

    @app.get("/attendance/today")
    def today(period: str = None,
              _: dict = Depends(get_current_user)):
        return db.get_today_attendance(period)

    @app.get("/attendance/summary")
    def summary(days: int = 30,
                _: dict = Depends(get_current_user)):
        return db.get_attendance_summary(days)

    @app.post("/attendance/override")
    def override(req: OverrideReq, request: Request,
                 user: dict = Depends(teacher_required)):
        db.teacher_override(req.student_id, req.period,
                            req.action, req.note)
        db.log_audit(_uname(user), "override",
                     req.student_id, req.action,
                     request.client.host if request.client else "?")
        return {"status": "done"}

    @app.get("/attendance/yesterday")
    def yesterday(period: str = None,
                  _: dict = Depends(get_current_user)):
        from datetime import timedelta
        d = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return db.get_attendance_by_date(d, period)

    @app.get("/attendance/date/{date_str}")
    def by_date(date_str: str, period: str = None,
                _: dict = Depends(get_current_user)):
        return db.get_attendance_by_date(date_str, period)

    @app.get("/analytics/engine")
    def engine_stats(days: int = 7,
                     _: dict = Depends(get_current_user)):
        return db.get_engine_stats(days)

    @app.get("/analytics/period")
    def period_stats(_: dict = Depends(get_current_user)):
        return db.get_period_stats()

    @app.get("/analytics/twins")
    def twin_log(days: int = 7,
                 _: dict = Depends(get_current_user)):
        return db.get_twin_analysis_log(days)

    @app.get("/timetable")
    def timetable(_: dict = Depends(get_current_user)):
        return db.get_timetable()

    @app.get("/settings")
    def get_settings(_: dict = Depends(get_current_user)):
        return {
            "LBPH_THRESHOLD":          config.LBPH_THRESHOLD,
            "DLIB_DISTANCE":           config.DLIB_DISTANCE,
            "MIN_CONFIDENCE_PCT":      config.MIN_CONFIDENCE_PCT,
            "CONFIRM_FRAMES_REQUIRED": config.CONFIRM_FRAMES_REQUIRED,
            "LIVENESS_THRESHOLD":      config.LIVENESS_THRESHOLD,
            "LIVENESS_ON":             config.LIVENESS_ON,
            "CAMERA_INDEX":            config.CAMERA_INDEX,
        }

    @app.post("/settings")
    def save_settings(data: dict,
                      user: dict = Depends(admin_required)):
        for key, cast in {
            "LBPH_THRESHOLD": float,
            "DLIB_DISTANCE": float,
            "MIN_CONFIDENCE_PCT": float,
            "CONFIRM_FRAMES_REQUIRED": int,
            "LIVENESS_THRESHOLD": float,
            "LIVENESS_ON": bool,
            "CAMERA_INDEX": int,
        }.items():
            if key in data:
                setattr(config, key, cast(data[key]))
        return {"status": "ok"}

    @app.get("/export/csv")
    def export_csv(_: dict = Depends(get_current_user)):
        import csv, io
        today_str = datetime.now().strftime("%Y-%m-%d")
        rows      = db.get_today_attendance()
        out       = io.StringIO()
        w = csv.DictWriter(out, fieldnames=[
            "name", "roll_number", "period", "date",
            "time", "confidence", "engine"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
        out.seek(0)
        return StreamingResponse(
            iter([out.read()]),
            media_type="text/csv",
            headers={"Content-Disposition":
                     f"attachment; filename=attendance_{today_str}.csv"})

    @app.post("/session/start")
    def session_start(req: StartSessionReq,
                      user: dict = Depends(teacher_required)):
        state = _sess._SESSION_STATE
        t = state.get("thread")
        if t and not t.is_alive():
            state["running"] = False
            state["thread"]  = None
        if state["running"]:
            raise HTTPException(
                status_code=409,
                detail="Session already running. Stop it first.")
        period = req.period.strip()
        if not period:
            raise HTTPException(status_code=400,
                                detail="Period name is required")
        result = _sess.start_session(period)
        if not result["ok"]:
            raise HTTPException(status_code=500,
                                detail=result.get("error", "Start failed"))
        db.log_audit(_uname(user), "session_start", period)
        return {
            "status": "started",
            "period": period,
            "stream": f"http://localhost:{config.API_PORT}/video_feed",
        }

    @app.post("/session/stop")
    def session_stop(user: dict = Depends(teacher_required)):
        _sess.stop_session()
        db.log_audit(_uname(user), "session_stop",
                     _sess._SESSION_STATE.get("period", ""))
        return {"status": "stopped"}

    @app.get("/session/status")
    def session_status(_: dict = Depends(get_current_user)):
        state  = _sess.get_status()
        period = state.get("period")
        marked_rows: list = []
        if period:
            try:
                marked_rows = db.get_today_attendance(period) or []
            except Exception:
                pass
        already_marked = [
            {
                "student_id": r.get("student_id", ""),
                "name":       r.get("name", ""),
                "time":       str(r.get("time", ""))[:8],
                "confidence": int(float(r.get("confidence", 0)) * 100),
                "engine":     r.get("engine", ""),
            }
            for r in marked_rows
        ]
        total_students = 0
        try:
            total_students = len(db.get_all_students())
        except Exception:
            pass
        return {
            "running":        state.get("running", False),
            "period":         period,
            "started_at":     state.get("started_at"),
            "marked_count":   len(marked_rows),
            "total_students": total_students,
            "absent_count":   max(0, total_students - len(marked_rows)),
            "already_marked": already_marked,
            "error":          state.get("error") or "",
        }

    @app.get("/video_feed")
    def video_feed():
        return StreamingResponse(
            _sess.generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma":        "no-cache",
                "Expires":       "0",
            }
        )

    # =========================================================
    # /api/* BRIDGE ENDPOINTS  (new in v9.6 — for EduTrack frontend)
    # =========================================================

    # ── Login ─────────────────────────────────────────────────
    @app.post("/api/login")
    def api_login(req: FrontendLoginReq, request: Request):
        """
        Accepts the EduTrack frontend login payload.
        Admin/HOD/ClassIncharge log in with email + password.
        Faculty log in with fac_id + password (checked against
        students table where student_id starts with 'FAC').
        Returns JWT token + role for the frontend to store.
        """
        ip = request.client.host if request.client else "?"
        role = None
        username = ""

        # Faculty portal login (fac_id provided)
        if req.fac_id:
            fac = db.get_student(req.fac_id)
            if fac and req.password == "fac@2025":   # dev default
                token = create_access_token(req.fac_id, "faculty")
                db.log_audit(req.fac_id, "login_ok", "", "faculty", ip)
                return {
                    "access_token": token, "token_type": "bearer",
                    "role": "faculty",
                    "fac_id": req.fac_id,
                    "name": fac.get("name", req.fac_id),
                }
            db.log_audit(req.fac_id, "login_fail", "", "faculty", ip)
            raise HTTPException(status_code=401,
                                detail="Invalid Faculty ID or password")

        # Admin portal login
        email = req.email.strip().lower()
        if (email == config.ADMIN_USERNAME.lower() or
                email == f"{config.ADMIN_USERNAME.lower()}@college.edu"):
            if req.password == config.ADMIN_PASSWORD:
                role = req.role if req.role in ("admin","hod","classincharge") else "admin"
                username = config.ADMIN_USERNAME
        elif (email == config.TEACHER_USERNAME.lower() or
                email == f"{config.TEACHER_USERNAME.lower()}@college.edu"):
            if req.password == config.TEACHER_PASSWORD:
                role = "teacher"
                username = config.TEACHER_USERNAME

        # Also accept password-only for demo (any email + correct password)
        if not role:
            if req.password == config.ADMIN_PASSWORD:
                role = req.role if req.role in ("admin","hod","classincharge") else "admin"
                username = req.email or config.ADMIN_USERNAME
            elif req.password == config.TEACHER_PASSWORD:
                role = "teacher"
                username = req.email or config.TEACHER_USERNAME

        if not role:
            db.log_audit(req.email, "login_fail", "", "", ip)
            raise HTTPException(status_code=401,
                                detail="Invalid credentials")

        token = create_access_token(username, role)
        db.log_audit(username, "login_ok", "", role, ip)
        return {
            "access_token": token, "token_type": "bearer",
            "role": role, "username": username,
        }

    # ── Students ──────────────────────────────────────────────
    @app.get("/api/students")
    def api_list_students(_: dict = Depends(get_current_user)):
        rows = db.get_all_students()
        # Convert Row objects to plain dicts
        return [dict(r) for r in rows]

    @app.post("/api/students")
    def api_add_student(req: AddStudentReq, request: Request,
                        user: dict = Depends(teacher_required)):
        sid = f"STU_{req.roll_number.upper()}"
        ok  = db.add_student(
            student_id=sid, name=req.name,
            roll_number=req.roll_number.lower(),
            section=req.section, mobile=req.mobile,
            twin_of=req.twin_of)
        db.log_audit(_uname(user), "add_student", sid, req.name,
                     request.client.host if request.client else "?")
        if not ok:
            raise HTTPException(status_code=409,
                                detail="Student already exists")
        return {"student_id": sid, "status": "created",
                "message": f"Student {req.name} added. Run training to enrol face."}

    @app.delete("/api/students/{student_id}")
    def api_delete_student(student_id: str, request: Request,
                           user: dict = Depends(admin_required)):
        db.delete_student_data(student_id)
        db.log_audit(_uname(user), "delete_student", student_id,
                     "", request.client.host if request.client else "?")
        return {"status": "deactivated", "student_id": student_id}

    # ── Attendance ────────────────────────────────────────────
    @app.get("/api/attendance/today")
    def api_today(period: str = None,
                  _: dict = Depends(get_current_user)):
        rows = db.get_today_attendance(period)
        return [dict(r) for r in rows]

    @app.get("/api/attendance/summary")
    def api_summary(days: int = 30,
                    _: dict = Depends(get_current_user)):
        rows = db.get_attendance_summary(days)
        return [dict(r) for r in rows]

    @app.get("/api/attendance/date/{date_str}")
    def api_by_date(date_str: str, period: str = None,
                    _: dict = Depends(get_current_user)):
        rows = db.get_attendance_by_date(date_str, period)
        return [dict(r) for r in rows]

    @app.post("/api/attendance/override")
    def api_override(req: FrontendOverrideReq, request: Request,
                     user: dict = Depends(teacher_required)):
        """
        Frontend override — supports richer payload from EduTrack UI.
        Internally maps to the same db.teacher_override() call.
        """
        note = req.reason
        if req.category and req.category != "—":
            note = f"[{req.category}] {note}".strip()
        if req.modifier_id:
            note = f"{note} (by {req.modifier_id})".strip()

        db.teacher_override(req.student_id, req.period,
                            req.action, note)
        db.log_audit(
            _uname(user), "override",
            req.student_id,
            f"{req.action} — {note}",
            request.client.host if request.client else "?")
        return {"status": "done", "message": "Override saved to database"}

    # ── Session ───────────────────────────────────────────────
    @app.post("/api/session/start")
    def api_session_start(req: StartSessionReq,
                          user: dict = Depends(teacher_required)):
        state = _sess._SESSION_STATE
        t = state.get("thread")
        if t and not t.is_alive():
            state["running"] = False
            state["thread"]  = None
        if state["running"]:
            raise HTTPException(
                status_code=409,
                detail="Session already running. Stop it first.")
        period = req.period.strip()
        if not period:
            raise HTTPException(status_code=400,
                                detail="Period name is required")
        result = _sess.start_session(period)
        if not result["ok"]:
            raise HTTPException(status_code=500,
                                detail=result.get("error", "Start failed"))
        db.log_audit(_uname(user), "api_session_start", period)
        port = config.API_PORT
        return {
            "status":  "started",
            "period":  period,
            "stream":  f"/video_feed",
            "message": f"Camera session started for {period}",
        }

    @app.post("/api/session/stop")
    def api_session_stop(user: dict = Depends(teacher_required)):
        _sess.stop_session()
        db.log_audit(_uname(user), "api_session_stop",
                     _sess._SESSION_STATE.get("period", ""))
        return {"status": "stopped", "message": "Session stopped"}

    @app.get("/api/session/status")
    def api_session_status(_: dict = Depends(get_current_user)):
        state  = _sess.get_status()
        period = state.get("period")
        marked_rows: list = []
        if period:
            try:
                marked_rows = db.get_today_attendance(period) or []
            except Exception:
                pass
        already_marked = [
            {
                "student_id": r.get("student_id", ""),
                "name":       r.get("name", ""),
                "time":       str(r.get("time", ""))[:8],
                "confidence": int(float(r.get("confidence", 0)) * 100),
                "engine":     r.get("engine", ""),
            }
            for r in marked_rows
        ]
        total_students = 0
        try:
            total_students = len(db.get_all_students())
        except Exception:
            pass
        return {
            "running":        state.get("running", False),
            "period":         period,
            "started_at":     state.get("started_at"),
            "marked_count":   len(marked_rows),
            "total_students": total_students,
            "absent_count":   max(0, total_students - len(marked_rows)),
            "already_marked": already_marked,
            "error":          state.get("error") or "",
        }

    # ── Training ──────────────────────────────────────────────
    @app.post("/api/train")
    def api_train(background_tasks: BackgroundTasks,
                  user: dict = Depends(admin_required)):
        """
        Kicks off LBPH + dlib training in a background thread.
        Returns immediately; poll /api/train/status to check progress.
        """
        if _train_state["running"]:
            return {"status": "already_running",
                    "message": "Training is already in progress"}
        background_tasks.add_task(_run_training_bg)
        return {"status": "started",
                "message": "Training started in background. Poll /api/train/status"}

    @app.get("/api/train/status")
    def api_train_status(_: dict = Depends(get_current_user)):
        return {
            "running": _train_state["running"],
            "done":    _train_state["done"],
            "error":   _train_state["error"],
            "log":     _train_state["log"][-20:],   # last 20 lines
        }

    # ── Analytics ─────────────────────────────────────────────
    @app.get("/api/analytics/summary")
    def api_analytics_summary(_: dict = Depends(get_current_user)):
        """
        Returns a single object with all KPI numbers the
        EduTrack dashboard needs: total students, today present,
        avg attendance, engine stats, etc.
        """
        students     = db.get_all_students()
        today_rows   = db.get_today_attendance()
        summary_rows = db.get_attendance_summary(30)
        engine_rows  = db.get_engine_stats(7)
        period_rows  = db.get_period_stats()

        total_students = len(students)
        present_today  = len(today_rows)
        absent_today   = max(0, total_students - present_today)
        pct_today      = round(present_today / total_students * 100, 1) if total_students else 0

        # Avg from summary
        pcts = []
        for r in summary_rows:
            pc = r.get("present_count", 0)
            td = r.get("total_days", 1) or 1
            pcts.append(pc / td * 100)
        avg_att = round(sum(pcts) / len(pcts), 1) if pcts else 0

        # Critical students (<65%)
        critical = [r for r in summary_rows
                    if (r.get("present_count", 0) / (r.get("total_days", 1) or 1)) < 0.65]

        return {
            "total_students":  total_students,
            "present_today":   present_today,
            "absent_today":    absent_today,
            "pct_today":       pct_today,
            "avg_attendance":  avg_att,
            "critical_count":  len(critical),
            "critical_students": [dict(r) for r in critical],
            "engine_stats":    [dict(r) for r in engine_rows],
            "period_stats":    [dict(r) for r in period_rows],
        }

    @app.get("/api/analytics/engine")
    def api_engine_stats(days: int = 7,
                         _: dict = Depends(get_current_user)):
        return [dict(r) for r in db.get_engine_stats(days)]

    @app.get("/api/analytics/period")
    def api_period_stats(_: dict = Depends(get_current_user)):
        return [dict(r) for r in db.get_period_stats()]

    @app.get("/api/analytics/twins")
    def api_twin_log(days: int = 7,
                     _: dict = Depends(get_current_user)):
        return [dict(r) for r in db.get_twin_analysis_log(days)]

    # ── Timetable ─────────────────────────────────────────────
    @app.get("/api/timetable")
    def api_timetable(_: dict = Depends(get_current_user)):
        rows = db.get_timetable()
        return [dict(r) for r in rows]

    # ── Settings ──────────────────────────────────────────────
    @app.get("/api/settings")
    def api_get_settings(_: dict = Depends(get_current_user)):
        return {
            "LBPH_THRESHOLD":          config.LBPH_THRESHOLD,
            "DLIB_DISTANCE":           config.DLIB_DISTANCE,
            "MIN_CONFIDENCE_PCT":      config.MIN_CONFIDENCE_PCT,
            "CONFIRM_FRAMES_REQUIRED": config.CONFIRM_FRAMES_REQUIRED,
            "LIVENESS_THRESHOLD":      config.LIVENESS_THRESHOLD,
            "LIVENESS_ON":             config.LIVENESS_ON,
            "CAMERA_INDEX":            config.CAMERA_INDEX,
        }

    @app.post("/api/settings")
    def api_save_settings(data: dict,
                          user: dict = Depends(admin_required)):
        for key, cast in {
            "LBPH_THRESHOLD": float,
            "DLIB_DISTANCE": float,
            "MIN_CONFIDENCE_PCT": float,
            "CONFIRM_FRAMES_REQUIRED": int,
            "LIVENESS_THRESHOLD": float,
            "LIVENESS_ON": bool,
            "CAMERA_INDEX": int,
        }.items():
            if key in data:
                setattr(config, key, cast(data[key]))
        return {"status": "ok", "message": "Settings updated"}

    # ── Export ────────────────────────────────────────────────
    @app.get("/api/export/csv")
    def api_export_csv(period: str = None,
                       _: dict = Depends(get_current_user)):
        import csv, io
        today_str = datetime.now().strftime("%Y-%m-%d")
        rows      = db.get_today_attendance(period)
        out       = io.StringIO()
        w = csv.DictWriter(out, fieldnames=[
            "name", "student_id", "period", "date",
            "time", "confidence", "engine"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
        out.seek(0)
        return StreamingResponse(
            iter([out.read()]),
            media_type="text/csv",
            headers={"Content-Disposition":
                     f"attachment; filename=attendance_{today_str}.csv"})

    # ── Frontend static files ─────────────────────────────────
    frontend_dir = os.path.join(config.BASE_DIR, "frontend")
    if os.path.isdir(frontend_dir):
        # Serve frontend/style.css and frontend/app.js at /style.css, /app.js
        @app.get("/style.css")
        def serve_css():
            p = os.path.join(frontend_dir, "style.css")
            return FileResponse(p, media_type="text/css") if os.path.exists(p) else HTMLResponse("", 404)

        @app.get("/app.js")
        def serve_js():
            p = os.path.join(frontend_dir, "app.js")
            return FileResponse(p, media_type="application/javascript") if os.path.exists(p) else HTMLResponse("", 404)

        @app.get("/features.js")
        def serve_features_js():
            p = os.path.join(frontend_dir, "features.js")
            return FileResponse(p, media_type="application/javascript") if os.path.exists(p) else HTMLResponse("", 404)

        @app.get("/features.css")
        def serve_features_css():
            p = os.path.join(frontend_dir, "features.css")
            return FileResponse(p, media_type="text/css") if os.path.exists(p) else HTMLResponse("", 404)

        @app.get("/app", response_class=HTMLResponse)
        @app.get("/", response_class=HTMLResponse)
        def frontend():
            idx = os.path.join(frontend_dir, "index.html")
            if os.path.exists(idx):
                return FileResponse(idx)
            return HTMLResponse(
                "<h2>Frontend not found</h2>"
                f"<p>Expected: {idx}</p>"
                "<p>Place index.html, style.css, app.js inside the "
                "<code>frontend/</code> folder.</p>")

    # ── Feature Extensions (departments drill-down + faculty mgmt) ──
    try:
        from api_features import register_feature_routes
        register_feature_routes(app, get_current_user,
                                teacher_required, admin_required)
        log.info("Feature routes registered (departments + faculty).")
    except Exception as _fe:
        log.warning("Feature routes not loaded: %s", _fe)

    return app


# =============================================================
# ENTRY POINT  (called from main.py option 4)
# =============================================================
def run_api():
    if not FASTAPI_OK:
        print("  ERROR: pip install fastapi uvicorn")
        return

    app = create_app()

    import socket
    port = config.API_PORT
    for p in [port, port+1, port+2, 8080, 8888, 9000]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", p))
            port = p
            break
        except OSError:
            continue
    else:
        print("  ERROR: No free port. Kill old server and retry.")
        return

    if port != config.API_PORT:
        print(f"  [INFO] Port {config.API_PORT} busy — using {port}")

    print(f"\n  ┌──────────────────────────────────────────────────────┐")
    print(f"  │  EduTrack Pro  ·  Smart Attendance System  v9.6      │")
    print(f"  │                                                        │")
    print(f"  │  Dashboard  : http://localhost:{port}/app             │")
    print(f"  │  API Docs   : http://localhost:{port}/docs            │")
    print(f"  │  Video Feed : http://localhost:{port}/video_feed      │")
    print(f"  │                                                        │")
    print(f"  │  Admin login  : admin / admin123                      │")
    print(f"  │  Teacher login: teacher / teacher123                  │")
    print(f"  │  Press Ctrl+C to stop                                 │")
    print(f"  └──────────────────────────────────────────────────────┘\n")

    try:
        uvicorn.run(app, host=config.API_HOST, port=port,
                    log_level="warning")
    except OSError as e:
        print(f"\n  ERROR: {e}")
        print(f"  Kill the process using port {port} and retry.")
        
        