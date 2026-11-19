import calendar
import io
import json
import os
import re
import shutil
import threading
import time
from datetime import date, datetime, timedelta
from functools import wraps

import cv2
import pymysql
from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from openpyxl import Workbook
from openpyxl.styles import Font
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
from ml import face, predict, train as trainer

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
os.makedirs(config.DATASET_DIR, exist_ok=True)
os.makedirs(config.MODEL_DIR, exist_ok=True)


# ------------------------------------------------------------------ helper
def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                if request.is_json:
                    return jsonify(ok=False, msg="Sesi habis, silakan login ulang."), 401
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                if request.is_json:
                    return jsonify(ok=False, msg="Tidak punya akses."), 403
                flash("Anda tidak punya akses ke halaman itu.", "danger")
                return redirect(url_for("index"))
            return f(*a, **kw)
        return wrapper
    return deco


def current_user():
    return db.query("SELECT * FROM users WHERE id=%s", (session["user_id"],), one=True)


def foto_count(kode):
    folder = os.path.join(config.DATASET_DIR, kode)
    if not os.path.isdir(folder):
        return 0
    return len([f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".png", ".jpeg"))])


def hitung_status(now):
    h, m = map(int, config.JAM_MASUK.split(":"))
    batas = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(minutes=config.TOLERANSI_MENIT)
    return "terlambat" if now > batas else "tepat waktu"


def load_metrics():
    if os.path.exists(config.METRICS_PATH):
        with open(config.METRICS_PATH) as f:
            return json.load(f)
    return None


REKAP_SQL = """
    SELECT a.id, u.kode_karyawan, u.nama_lengkap, u.jabatan,
           DATE_FORMAT(a.tanggal,'%%d-%%m-%%Y') AS tanggal,
           TIME_FORMAT(a.jam_masuk,'%%H:%%i:%%s') AS jam_masuk,
           TIME_FORMAT(a.jam_pulang,'%%H:%%i:%%s') AS jam_pulang,
           a.status
    FROM attendance a JOIN users u ON u.id = a.user_id
    WHERE a.tanggal BETWEEN %s AND %s {extra}
    ORDER BY a.tanggal DESC, u.nama_lengkap
"""


def query_rekap(dari, sampai, user_id=None):
    if user_id:
        return db.query(REKAP_SQL.format(extra="AND a.user_id=%s"), (dari, sampai, user_id))
    return db.query(REKAP_SQL.format(extra=""), (dari, sampai))


def rentang_default():
    today = date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


# ------------------------------------------------------------------ auth
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard" if session["role"] == "admin" else "beranda"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db.query("SELECT * FROM users WHERE username=%s", (request.form["username"].strip(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=u["id"], role=u["role"], nama=u["nama_lengkap"])
            return redirect(url_for("index"))
        flash("Username atau password salah.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------ ADMIN
@app.route("/admin")
@login_required("admin")
def dashboard():
    stat = {
        "total": db.query("SELECT COUNT(*) c FROM users WHERE role='karyawan'", one=True)["c"],
        "hadir": db.query("SELECT COUNT(*) c FROM attendance WHERE tanggal=CURDATE()", one=True)["c"],
        "terlambat": db.query("SELECT COUNT(*) c FROM attendance WHERE tanggal=CURDATE() AND status='terlambat'", one=True)["c"],
        "wajah": db.query("SELECT COUNT(*) c FROM users WHERE role='karyawan' AND wajah_terdaftar=1", one=True)["c"],
    }
    hari_ini = query_rekap(date.today().isoformat(), date.today().isoformat())
    return render_template("admin/dashboard.html", stat=stat, hari_ini=hari_ini)

@app.route("/admin/karyawan", methods=["GET", "POST"])
@login_required("admin")
def kelola_karyawan():
    if request.method == "POST":
        f = request.form
        kode, nama, jab = f["kode"].strip(), f["nama"].strip(), f["jabatan"].strip()
        username, pw = f["username"].strip(), f["password"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", kode):
            flash("ID hanya boleh huruf, angka, '-' dan '_' (maks 20 karakter).", "danger")
        elif len(pw) < 6:
            flash("Password minimal 6 karakter.", "danger")
        else:
            try:
                db.execute(
                    "INSERT INTO users (kode_karyawan,nama_lengkap,jabatan,username,password_hash,role) "
                    "VALUES (%s,%s,%s,%s,%s,'karyawan')",
                    (kode, nama, jab, username, generate_password_hash(pw)))
                flash(f"Karyawan {nama} berhasil ditambahkan. Lanjutkan ke menu Registrasi Wajah.", "success")
            except pymysql.err.IntegrityError:
                flash("ID atau username sudah dipakai.", "danger")
        return redirect(url_for("kelola_karyawan"))
    rows = db.query("SELECT * FROM users ORDER BY FIELD(role,'admin','karyawan'), created_at DESC")
    for r in rows:
        r["foto"] = foto_count(r["kode_karyawan"]) if r["role"] == "karyawan" else 0
    n_admin = sum(1 for r in rows if r["role"] == "admin")
    return render_template("admin/karyawan.html", rows=rows, n_karyawan=len(rows) - n_admin, n_admin=n_admin)


@app.post("/admin/karyawan/hapus/<int:uid>")
@login_required("admin")
def hapus_karyawan(uid):
    u = db.query("SELECT * FROM users WHERE id=%s AND role='karyawan'", (uid,), one=True)
    if u:
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        shutil.rmtree(os.path.join(config.DATASET_DIR, u["kode_karyawan"]), ignore_errors=True)
        flash(f"{u['nama_lengkap']} dihapus. Latih ulang model agar data wajahnya hilang dari model.", "success")
    return redirect(url_for("kelola_karyawan"))


@app.post("/admin/karyawan/edit/<int:uid>")
@login_required("admin")
def edit_karyawan(uid):
    u = db.query("SELECT * FROM users WHERE id=%s", (uid,), one=True)   # karyawan maupun admin
    if not u:
        flash("Akun tidak ditemukan.", "danger")
        return redirect(url_for("kelola_karyawan"))
    f = request.form
    nama, jab = f.get("nama", "").strip(), f.get("jabatan", "").strip()
    username, pw = f.get("username", "").strip(), f.get("password", "")
    # ID sengaja tidak bisa diubah: dipakai sebagai nama folder foto & kelas model
    if not nama or not jab or not username:
        flash("Nama, jabatan, dan username wajib diisi.", "danger")
    elif pw and len(pw) < 6:
        flash("Password baru minimal 6 karakter.", "danger")
    else:
        try:
            if pw:
                db.execute("UPDATE users SET nama_lengkap=%s, jabatan=%s, username=%s, password_hash=%s WHERE id=%s",
                           (nama, jab, username, generate_password_hash(pw), uid))
                flash(f"Data {nama} diperbarui dan password diganti.", "success")
            else:
                db.execute("UPDATE users SET nama_lengkap=%s, jabatan=%s, username=%s WHERE id=%s",
                           (nama, jab, username, uid))
                flash(f"Data {nama} berhasil diperbarui.", "success")
            if uid == session.get("user_id"):      # admin mengedit akunnya sendiri
                session["nama"] = nama
        except pymysql.err.IntegrityError:
            flash("Username sudah dipakai akun lain.", "danger")
    return redirect(url_for("kelola_karyawan"))
    
@app.route("/admin/registrasi")
@login_required("admin")
def registrasi():
    rows = db.query("SELECT id,kode_karyawan,nama_lengkap,wajah_terdaftar FROM users WHERE role='karyawan' ORDER BY nama_lengkap")
    for r in rows:
        r["foto"] = foto_count(r["kode_karyawan"])
    return render_template("admin/registrasi.html", rows=rows, jumlah=config.JUMLAH_FOTO,
                           min_foto=config.MIN_FOTO_TRAIN, metrics=load_metrics())


@app.post("/admin/registrasi/upload")
@login_required("admin")
def registrasi_upload():
    d = request.get_json(silent=True) or {}
    kode = d.get("kode", "")
    if not db.query("SELECT id FROM users WHERE kode_karyawan=%s AND role='karyawan'", (kode,), one=True):
        return jsonify(ok=False, msg="Karyawan tidak ditemukan.")
    crop = face.detect_face(face.decode_data_url(d.get("image", "")))
    if crop is None:
        return jsonify(ok=False, msg="Wajah tidak terdeteksi.", jumlah=foto_count(kode))
    folder = os.path.join(config.DATASET_DIR, kode)
    os.makedirs(folder, exist_ok=True)
    cv2.imwrite(os.path.join(folder, f"{int(time.time() * 1000)}.jpg"), crop)
    return jsonify(ok=True, jumlah=foto_count(kode))


@app.post("/admin/registrasi/reset/<kode>")
@login_required("admin")
def registrasi_reset(kode):
    if re.fullmatch(r"[A-Za-z0-9_-]{1,20}", kode):
        shutil.rmtree(os.path.join(config.DATASET_DIR, kode), ignore_errors=True)
        flash("Foto wajah dihapus. Silakan ambil ulang.", "success")
    return redirect(url_for("registrasi"))


# ---- training di background thread
TRAIN = {"state": "idle", "message": "Belum ada proses training.", "percent": 0}


def _run_train():
    try:
        trainer_result = trainer.train(lambda **kw: TRAIN.update(kw))
        predict.load(force=True)
        kodes = trainer_result["classes"]
        db.execute("UPDATE users SET wajah_terdaftar=0 WHERE role='karyawan'")
        db.execute("UPDATE users SET wajah_terdaftar=1 WHERE kode_karyawan IN (%s)" % ",".join(["%s"] * len(kodes)), kodes)
        TRAIN.update(state="done", percent=100,
                     message=f"Training selesai. Accuracy data test: {trainer_result['test_accuracy'] * 100:.2f}%")
    except Exception as e:
        TRAIN.update(state="error", message=str(e))


@app.post("/admin/train")
@login_required("admin")
def train_start():
    if TRAIN["state"] == "running":
        return jsonify(ok=False, msg="Training masih berjalan.")
    TRAIN.update(state="running", percent=1, message="Menyiapkan data...")
    threading.Thread(target=_run_train, daemon=True).start()
    return jsonify(ok=True)


@app.get("/admin/train/status")
@login_required("admin")
def train_status():
    return jsonify(TRAIN)


@app.route("/admin/model/<path:filename>")
@login_required("admin")
def model_file(filename):
    return send_from_directory(config.MODEL_DIR, filename)


@app.route("/admin/rekap")
@login_required("admin")
def rekap_admin():
    d0, d1 = rentang_default()
    dari, sampai = request.args.get("dari", d0), request.args.get("sampai", d1)
    uid = request.args.get("karyawan", type=int)
    rows = query_rekap(dari, sampai, uid)
    karyawan = db.query("SELECT id,nama_lengkap FROM users WHERE role='karyawan' ORDER BY nama_lengkap")
    return render_template("admin/rekap.html", rows=rows, karyawan=karyawan, dari=dari, sampai=sampai, uid=uid)


@app.route("/admin/rekap/export")
@login_required("admin")
def rekap_export():
    d0, d1 = rentang_default()
    dari, sampai = request.args.get("dari", d0), request.args.get("sampai", d1)
    rows = query_rekap(dari, sampai, request.args.get("karyawan", type=int))
    wb = Workbook()
    ws = wb.active
    ws.title = "Rekap Absensi"
    ws.append(["No", "ID", "Nama", "Jabatan", "Tanggal", "Jam Masuk", "Jam Pulang", "Status"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for i, r in enumerate(rows, 1):
        ws.append([i, r["kode_karyawan"], r["nama_lengkap"], r["jabatan"], r["tanggal"],
                   r["jam_masuk"] or "-", r["jam_pulang"] or "-", r["status"]])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"rekap_absensi_{dari}_{sampai}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ------------------------------------------------------------------ KARYAWAN
def absen_hari_ini(uid):
    return db.query(
        "SELECT TIME_FORMAT(jam_masuk,'%%H:%%i:%%s') jam_masuk, TIME_FORMAT(jam_pulang,'%%H:%%i:%%s') jam_pulang, status "
        "FROM attendance WHERE user_id=%s AND tanggal=CURDATE()", (uid,), one=True)


@app.route("/beranda")
@login_required("karyawan")
def beranda():
    u = current_user()
    today = date.today()
    ringkas = db.query(
        "SELECT COUNT(*) hadir, COALESCE(SUM(status='terlambat'),0) terlambat FROM attendance "
        "WHERE user_id=%s AND YEAR(tanggal)=%s AND MONTH(tanggal)=%s", (u["id"], today.year, today.month), one=True)
    return render_template("karyawan/beranda.html", u=u, absen=absen_hari_ini(u["id"]), ringkas=ringkas,
                           jam=config.JAM_MASUK, tol=config.TOLERANSI_MENIT)


@app.route("/scan")
@login_required("karyawan")
def scan():
    return render_template("karyawan/scan.html", u=current_user(), absen=absen_hari_ini(session["user_id"]))


@app.post("/scan/proses")
@login_required("karyawan")
def scan_proses():
    u = current_user()
    if not u["wajah_terdaftar"]:
        return jsonify(ok=False, msg="Wajah Anda belum terdaftar. Hubungi admin.")
    if not predict.is_ready():
        return jsonify(ok=False, msg="Model belum dilatih. Hubungi admin.")

    crop = face.detect_face(face.decode_data_url((request.get_json(silent=True) or {}).get("image", "")))
    if crop is None:
        return jsonify(ok=False, msg="Wajah tidak terdeteksi. Hadapkan wajah ke kamera dengan cahaya cukup.")

    res = predict.verify(crop, u["kode_karyawan"])
    print(f"[SCAN] akun={u['kode_karyawan']} prediksi={res['pred']} conf={res['conf']:.3f} "
          f"sim_akun={res['sim_own']} sim_lain_tertinggi={res['sim_other']} diterima={res['ok']}", flush=True)
    if not res["ok"]:
        return jsonify(ok=False, msg=res["msg"])
    conf = res["conf"]

    now = datetime.now()
    row = db.query("SELECT * FROM attendance WHERE user_id=%s AND tanggal=CURDATE()", (u["id"],), one=True)
    if row is None:
        status = hitung_status(now)
        db.execute("INSERT INTO attendance (user_id,tanggal,jam_masuk,status,skor_masuk) VALUES (%s,CURDATE(),%s,%s,%s)",
                   (u["id"], now.strftime("%H:%M:%S"), status, round(conf, 4)))
        return jsonify(ok=True, tipe="masuk", status=status, jam=now.strftime("%H:%M:%S"),
                       msg=f"Absen masuk berhasil ({status}).", conf=round(conf * 100, 1))
    if row["jam_pulang"] is None:
        masuk_dt = datetime.combine(date.today(), (datetime.min + row["jam_masuk"]).time())
        if now - masuk_dt < timedelta(minutes=config.JEDA_MENIT):
            return jsonify(ok=False, msg=f"Anda baru absen masuk. Absen pulang bisa setelah {config.JEDA_MENIT} menit.")
        db.execute("UPDATE attendance SET jam_pulang=%s, skor_pulang=%s WHERE id=%s",
                   (now.strftime("%H:%M:%S"), round(conf, 4), row["id"]))
        return jsonify(ok=True, tipe="pulang", jam=now.strftime("%H:%M:%S"),
                       msg="Absen pulang berhasil.", conf=round(conf * 100, 1))
    return jsonify(ok=False, msg="Absen masuk dan pulang hari ini sudah tercatat.")


@app.route("/rekap")
@login_required("karyawan")
def rekap_karyawan():
    bulan = request.args.get("bulan", date.today().strftime("%Y-%m"))
    try:
        y, m = map(int, bulan.split("-"))
        dari = date(y, m, 1)
        sampai = date(y, m, calendar.monthrange(y, m)[1])
    except ValueError:
        abort(400)
    rows = query_rekap(dari.isoformat(), sampai.isoformat(), session["user_id"])
    return render_template("karyawan/rekap.html", rows=rows, bulan=bulan)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
