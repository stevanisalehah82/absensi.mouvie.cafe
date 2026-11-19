CREATE DATABASE IF NOT EXISTS mouvie_absensi
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE mouvie_absensi;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  kode_karyawan VARCHAR(20) NOT NULL UNIQUE,
  nama_lengkap VARCHAR(100) NOT NULL,
  jabatan VARCHAR(50),
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','karyawan') NOT NULL DEFAULT 'karyawan',
  wajah_terdaftar TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  tanggal DATE NOT NULL,
  jam_masuk TIME,
  jam_pulang TIME,
  status ENUM('tepat waktu','terlambat'),
  skor_masuk DECIMAL(5,4),
  skor_pulang DECIMAL(5,4),
  UNIQUE KEY uq_user_tanggal (user_id, tanggal),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
