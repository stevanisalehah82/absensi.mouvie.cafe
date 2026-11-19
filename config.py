import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = "ganti-dengan-kunci-rahasia-kamu"

# ---- Koneksi MySQL (sesuaikan) ----
DB = dict(
    host="localhost",
    user="root",
    password="",            # isi password MySQL kamu
    database="mouvie_absensi",
    charset="utf8mb4",
)

# ---- Aturan absensi ----
JAM_MASUK = "08:00"         # jam masuk standar
TOLERANSI_MENIT = 10        # lewat dari 08:10 dianggap terlambat
JEDA_MENIT = 1              # jeda minimal antara absen masuk dan pulang
THRESHOLD = 0.90            # minimal confidence ResNet-50 agar absen diterima

# ---- Dataset & model ----
JUMLAH_FOTO = 100           # target foto per karyawan saat registrasi
MIN_FOTO_TRAIN = 30         # karyawan dengan foto kurang dari ini tidak ikut training
IMG_SIZE = 224
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
MODEL_DIR = os.path.join(BASE_DIR, "ml", "output")
MODEL_PATH = os.path.join(MODEL_DIR, "resnet50_mouvie.pth")
METRICS_PATH = os.path.join(MODEL_DIR, "metrics.json")

# ---- Hyperparameter training ----
BATCH_SIZE = 16
EPOCH_FREEZE = 3            # tahap 1: hanya layer fc yang dilatih
EPOCH_FINETUNE = 7          # tahap 2: seluruh layer dilatih (lr kecil)
LR_FREEZE = 1e-3
LR_FINETUNE = 1e-4
