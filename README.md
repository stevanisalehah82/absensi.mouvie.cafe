# Absensi Face Recognition ResNet-50 - Mouvie Cafe

Flask + MySQL + PyTorch (ResNet-50 transfer learning).

## 1. Instalasi
1. Python 3.10/3.11, MySQL 8 (XAMPP / MySQL Server).
2. `python -m venv venv` lalu aktifkan (`venv\Scripts\activate` di Windows).
3. `pip install -r requirements.txt`
   (PyTorch versi CPU/GPU bisa dipilih di https://pytorch.org/get-started/locally/)
4. Buat database: `mysql -u root -p < database.sql` (atau import lewat phpMyAdmin).
5. Edit `config.py` -> isi password MySQL.
6. Buat admin: `python seed_admin.py` (default: admin / admin123). Ganti password lewat argumen:
   `python seed_admin.py admin PasswordBaru`
7. Jalankan: `python app.py` lalu buka :/http/127.0.0.1:5000

## 2. Alur pemakaian
**Admin**
1. Login -> Kelola Karyawan -> tambah karyawan (ID, nama, jabatan, username, password).
2. Registrasi Wajah -> pilih karyawan -> Mulai ambil foto (100 foto otomatis, ganti-ganti pose).
3. Ulangi untuk semua karyawan (minimal 2 orang).
4. Klik "Latih model" dan tunggu selesai. Grafik dan confusion matrix muncul, juga tersimpan di `ml/output/`.
5. Rekap Absensi -> filter tanggal/karyawan -> ekspor Excel.

**Karyawan**
1. Login dengan username/password dari admin.
2. Scan Absen -> hadapkan wajah -> tekan Scan. Scan pertama = masuk, scan kedua = pulang.
3. Beranda dan Rekap Absensi menampilkan riwayat sendiri.

## 3. Aturan absensi (ubah di config.py)
- Jam masuk 08:00, toleransi 10 menit (lewat 08:10 = terlambat).
- Absen diterima jika confidence >= 0.90 DAN wajah cocok dengan akun yang login.

## 4. Training manual (opsional)
`python -m ml.train` (hasil sama dengan tombol di web).
