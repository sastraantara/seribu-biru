import os
import csv
import zipfile
from io import StringIO, BytesIO
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, Response, session, jsonify, send_file
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, case, or_
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# Menginisialisasi aplikasi Flask
app = Flask(__name__)
# Menambahkan secret key (wajib untuk memunculkan pesan sukses/flash)
app.config['SECRET_KEY'] = 'kunci_rahasia_super_aman_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pelaporan.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Konfigurasi folder penyimpanan foto
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Membuat folder otomatis jika belum ada saat server berjalan
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

with app.app_context():
    print("DATABASE =", db.engine.url.database)
    print("FULL PATH =", os.path.abspath(db.engine.url.database))

# =====================================================
# DATA PETUGAS (Hardcoded untuk kemudahan)
# =====================================================
DAFTAR_PETUGAS = {
    "PIYAN": {"nama": "Pak Piyan", "role": ["Kolektor", "Presser"]},
    "EBI": {"nama": "Pak Ebi", "role": ["Kolektor", "Presser"]},
    "DARTI": {"nama": "Bu Darti", "role": ["Sorter", "Presser"]},
    "AISYAH": {"nama": "Bu Aisyah", "role": ["Sorter", "Presser"]},
    "IJAN": {"nama": "Pak Ijan", "role": ["Sorter", "Presser", "Kolektor"]},
    "QQ001": {
        "nama": "Rizqi", 
        "role": ["Kolektor", "Sorter", "Presser", "Curator", "Auditor", "Performa","Gudang"]
    },
    "NB001": {
        "nama": "Nicolas", 
        "role": ["Kolektor", "Sorter", "Presser", "Curator", "Auditor", "Performa", "Gudang"]
    },
    "JC001": {
        "nama": "Jeannete", 
        "role": ["Kolektor", "Sorter", "Presser", "Curator", "Auditor", "Performa", "Gudang"]
    },
    "SNY001": {
        "nama": "Super Admin", 
        "role": ["Kolektor", "Sorter", "Presser", "Curator", "Auditor", "Performa", "Gudang"]
    }
}

# -----------------------------------------------------
# MEMBUAT TABEL DATABASE
# -----------------------------------------------------

# 1. Tabel Utama: Batch
class Batch(db.Model):
    id_batch = db.Column(db.String(50), primary_key=True)
    tanggal = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Draft')
    
    # Status per Bagian
    status_kolektor = db.Column(db.String(20), default='Pending')
    status_sorter = db.Column(db.String(20), default='Pending')
    status_presser = db.Column(db.String(20), default='Pending')
    
    # Relasi penghapusan Batch menghapus semua data terkait
    laporan_kolektor = db.relationship('LaporanKolektor', backref='batch', lazy=True, cascade="all, delete-orphan")
    laporan_sorter = db.relationship('LaporanSorter', backref='batch', lazy=True, cascade="all, delete-orphan")
    laporan_presser = db.relationship('LaporanPresser', backref='batch', lazy=True, cascade="all, delete-orphan")
    riwayat_log = db.relationship('LogRiwayat', backref='batch', lazy=True, cascade="all, delete-orphan")

    # Catatan Revisi per Bagian
    catatan_kolektor = db.Column(db.Text, nullable=True)
    catatan_sorter = db.Column(db.Text, nullable=True)
    catatan_presser = db.Column(db.Text, nullable=True)

# 2. Tabel Referensi: Kategori Sampah
class KategoriSampah(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_kategori = db.Column(db.String(100), nullable=False)

# 3. Tabel Laporan: Kolektor
class LaporanKolektor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_batch = db.Column(db.String(50), db.ForeignKey('batch.id_batch'), nullable=False)
    nama_petugas = db.Column(db.String(100))
    waktu_submit = db.Column(db.DateTime, default=datetime.utcnow)
    foto_sebelum = db.Column(db.String(255))
    foto_saat = db.Column(db.String(255))
    foto_setelah = db.Column(db.String(255))
    foto_karung_lokasi = db.Column(db.String(255))
    foto_timbang_basah = db.Column(db.String(255))
    foto_fasilitas = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    waktu_foto = db.Column(db.DateTime)
    berat_kotor = db.Column(db.Float)

class FotoDokumentasi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_batch = db.Column(db.String(50), db.ForeignKey('batch.id_batch'), nullable=False)
    bagian = db.Column(db.String(20)) # 'kolektor', 'sorter', atau 'presser'
    kategori_foto = db.Column(db.String(50)) # 'sebelum', 'saat', 'bekerja', dll
    path_foto = db.Column(db.String(255))
    is_approved = db.Column(db.Boolean, default=False) 
    is_selected = db.Column(db.Boolean, default=False) 

# 4. Tabel Laporan: Sorter
class LaporanSorter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_batch = db.Column(db.String(50), db.ForeignKey('batch.id_batch'), nullable=False)
    nama_petugas = db.Column(db.String(100))
    waktu_submit = db.Column(db.DateTime, default=datetime.utcnow)
    foto_bekerja = db.Column(db.String(255))
    foto_seluruh_karung = db.Column(db.String(255))

# 5. Tabel Detail Sortiran 
class DetailSortiran(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_sorter = db.Column(db.Integer, db.ForeignKey('laporan_sorter.id'), nullable=False)
    id_kategori = db.Column(db.Integer, db.ForeignKey('kategori_sampah.id'), nullable=False)
    berat = db.Column(db.Float)

# 6. Tabel Laporan: Presser
class LaporanPresser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_batch = db.Column(db.String(50), db.ForeignKey('batch.id_batch'), nullable=False)
    nama_petugas = db.Column(db.String(100))
    waktu_submit = db.Column(db.DateTime, default=datetime.utcnow)
    foto_bekerja = db.Column(db.String(255))
    foto_seluruh_press = db.Column(db.String(255))

# 7. Tabel Detail Presser 
class DetailPresser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_presser = db.Column(db.Integer, db.ForeignKey('laporan_presser.id'), nullable=False)
    id_kategori = db.Column(db.Integer, db.ForeignKey('kategori_sampah.id'), nullable=False)
    berat = db.Column(db.Float)

class FotoKategori(db.Model):
    __tablename__ = 'foto_kategori'
    id = db.Column(db.Integer, primary_key=True)
    jenis = db.Column(db.String(20), nullable=False)
    id_detail = db.Column(db.Integer, nullable=False)
    path_foto = db.Column(db.String(255), nullable=False)
    is_selected = db.Column(db.Boolean, default=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class LogRiwayat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_batch = db.Column(db.String(50), db.ForeignKey('batch.id_batch'), nullable=False)
    waktu = db.Column(db.DateTime, default=datetime.utcnow)
    aktor = db.Column(db.String(100)) 
    aksi = db.Column(db.String(100))  
    catatan = db.Column(db.Text, nullable=True)

    @property
    def waktu_wib(self):
        return self.waktu + timedelta(hours=7)

# 8. Tabel Khusus Rekam Jejak Penghapusan
class RiwayatHapus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_batch = db.Column(db.String(50)) 
    waktu_hapus = db.Column(db.DateTime, default=datetime.utcnow)
    aktor = db.Column(db.String(100))
    keterangan = db.Column(db.Text)

    @property
    def waktu_wib(self):
        return self.waktu_hapus + timedelta(hours=7)
    
# 9. Tabel Data Gudang (Inventory Penjualan)
class DataGudang(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_batch = db.Column(db.String(50), db.ForeignKey('batch.id_batch'), nullable=False)
    status_stok = db.Column(db.String(20), default='Di Gudang') 
    pembeli = db.Column(db.String(150), nullable=True)
    tanggal_keluar = db.Column(db.DateTime, nullable=True)
    catatan_jual = db.Column(db.Text, nullable=True) # <-- KOLOM BARU

# -----------------------------------------------------
# EKSEKUSI PEMBUATAN DATABASE & DATA AWAL
# -----------------------------------------------------
with app.app_context():
    db.create_all()
    
    if KategoriSampah.query.count() == 0:
        daftar_kategori = [
            "Gelas plastik", "Botol plastik bening", "Botol plastik warna", 
            "Botol keras", "Kontainer keras", "Kresek", "Tutup botol", 
            "Alat makan plastik", "Sedotan plastik", "Sachet/kemasan", 
            "Multilayer", "Sol sandal/sepatu", "Styrofoam", 
            "Mainan/korek/sikat gigi/benda plastik kecil", "Tetrapack", 
            "Ghostnet", "Pipa", "Masker", "Popok", "Putung rokok"
        ]
        for nama in daftar_kategori:
            kategori_baru = KategoriSampah(nama_kategori=nama)
            db.session.add(kategori_baru)
        db.session.commit()
        print("20 Kategori Sampah berhasil dimasukkan ke database!")

# =====================================================
# FUNGSI PEMBANTU: EKSTRAKSI EXIF GPS KE DESIMAL
# =====================================================
def dapatkan_koordinat_exif(image_path):
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if not exif_data:
            return None, None

        gps_info = {}
        for tag, value in exif_data.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_info[sub_decoded] = value[t]
                break

        if not gps_info or 'GPSLatitude' not in gps_info or 'GPSLongitude' not in gps_info:
            return None, None

        def konversi_ke_desimal(dms, ref):
            derajat = float(dms[0])
            menit = float(dms[1])
            detik = float(dms[2])
            desimal = derajat + (menit / 60.0) + (detik / 3600.0)
            if ref in ['S', 'W']:  
                desimal = -desimal
            return desimal

        lat = konversi_ke_desimal(gps_info['GPSLatitude'], gps_info['GPSLatitudeRef'])
        lon = konversi_ke_desimal(gps_info['GPSLongitude'], gps_info['GPSLongitudeRef'])
        
        return lat, lon
        
    except Exception as e:
        print(f"Gagal mengekstrak EXIF GPS: {e}")
        return None, None

# -----------------------------------------------------
# RUTE WEB
# -----------------------------------------------------
@app.route('/')
def landing_page():
    return render_template('landing.html')

@app.route('/login/<target_role>', methods=['GET', 'POST'])
def login_petugas(target_role):
    pesan_error = None  
    
    if request.method == 'POST':
        id_masuk = request.form.get('id_petugas').upper() 
        petugas = DAFTAR_PETUGAS.get(id_masuk)
        
        if petugas:
            roles_diizinkan = petugas['role']
            target_role_kapital = target_role.capitalize()
            
            if target_role_kapital in roles_diizinkan:
                session['petugas_nama'] = petugas['nama']
                return redirect(f'/{target_role}')
            else:
                pesan_error = f"Akses Ditolak: ID {id_masuk} tidak memiliki izin sebagai {target_role_kapital}."
        else:
            pesan_error = "ID Petugas tidak ditemukan di sistem!"
            
    return render_template('login.html', role=target_role, error=pesan_error)

@app.route('/logout')
def logout():
    session.clear() 
    return redirect('/')

# =====================================================
# API ENDPOINTS
# =====================================================
@app.route('/api/info_batch/<id_batch>')
def info_batch(id_batch):
    try:
        kolektor = LaporanKolektor.query.filter_by(id_batch=id_batch).first()
        if kolektor:
            waktu_wib = kolektor.waktu_submit + timedelta(hours=7)
            waktu_teks = waktu_wib.strftime('%d/%m/%Y - %H:%M')
            jawaban_teks = f"{kolektor.nama_petugas} pada {waktu_teks}"
            return jsonify({"status": "ok", "pengirim": jawaban_teks})
            
        return jsonify({"status": "not_found"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/info_batch_lengkap/<id_batch>')
def info_batch_lengkap(id_batch):
    try:
        kolektor = LaporanKolektor.query.filter_by(id_batch=id_batch).first()
        sorter = LaporanSorter.query.filter_by(id_batch=id_batch).first()
        
        teks_kolektor = "Belum mengisi / Tidak ditemukan"
        if kolektor:
            waktu_k_wib = kolektor.waktu_submit + timedelta(hours=7)
            teks_kolektor = f"{kolektor.nama_petugas} pada {waktu_k_wib.strftime('%d/%m/%Y - %H:%M')}"
            
        teks_sorter = "Belum mengisi / Tidak ditemukan"
        if sorter:
            waktu_s_wib = sorter.waktu_submit + timedelta(hours=7)
            teks_sorter = f"{sorter.nama_petugas} pada {waktu_s_wib.strftime('%d/%m/%Y - %H:%M')}"

        return jsonify({
            "status": "ok",
            "kolektor": teks_kolektor,
            "sorter": teks_sorter
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# =====================================================
# RUTE WEB: OPERATOR LAPANGAN (SORTER)
# =====================================================
@app.route('/sorter')
def halaman_sorter():
    if 'petugas_nama' not in session: 
        return redirect('/')
    nama = session['petugas_nama']
    kategori_dari_db = KategoriSampah.query.all()
    
    laporan_petugas = LaporanSorter.query.filter_by(nama_petugas=nama).all()
    list_revisi = []
    for lp in laporan_petugas:
        b = Batch.query.get(lp.id_batch)
        if b and b.status_sorter == 'Rejected':
            list_revisi.append({'id_batch': b.id_batch, 'catatan': b.catatan_sorter})

    rekap_tanggal = db.session.query(
        Batch.id_batch.label('tanggal'),
        func.count(LaporanKolektor.id).label('jumlah_petugas'),
        func.sum(LaporanKolektor.berat_kotor).label('total_kg_kolektor')
    ).join(LaporanKolektor, Batch.id_batch == LaporanKolektor.id_batch)\
     .group_by(Batch.id_batch).order_by(Batch.id_batch.desc()).all()

    detail_kolektor_db = LaporanKolektor.query.all()
    detail_kolektor = {}
    for dk in detail_kolektor_db:
        tgl = dk.id_batch
        if tgl not in detail_kolektor:
            detail_kolektor[tgl] = []
        
        waktu_str = (dk.waktu_submit + timedelta(hours=7)).strftime('%H:%M WIB') if dk.waktu_submit else '-'
        detail_kolektor[tgl].append({
            'nama': dk.nama_petugas,
            'waktu': waktu_str,
            'berat': dk.berat_kotor
        })

    laporan_terakhir = LaporanKolektor.query.order_by(LaporanKolektor.waktu_submit.desc()).first()
    if laporan_terakhir:
        tanggal_terakhir = laporan_terakhir.id_batch 
        semua_setoran_terakhir = LaporanKolektor.query.filter_by(id_batch=tanggal_terakhir).all()
        list_nama = list(set([lp.nama_petugas for lp in semua_setoran_terakhir]))
        if len(list_nama) == 1:
            teks_penyetor = list_nama[0]
        elif len(list_nama) == 2:
            teks_penyetor = f"{list_nama[0]} dan {list_nama[1]}"
        else:
            teks_penyetor = ", ".join(list_nama[:-1]) + f", dan {list_nama[-1]}"
        total_kg_terakhir = sum([lp.berat_kotor for lp in semua_setoran_terakhir])
    else:
        tanggal_terakhir = None
        teks_penyetor = None
        total_kg_terakhir = 0
        
    sudah_disortir = [s.id_batch for s in LaporanSorter.query.with_entities(LaporanSorter.id_batch).distinct().all()]

    return render_template('sorter.html', 
                           nama_petugas=nama, 
                           daftar_kategori=kategori_dari_db, 
                           list_revisi=list_revisi,
                           rekap_tanggal=rekap_tanggal,
                           detail_kolektor=detail_kolektor,
                           tanggal_terakhir=tanggal_terakhir,
                           teks_penyetor=teks_penyetor,
                           total_kg_terakhir=total_kg_terakhir,
                           sudah_disortir=sudah_disortir)

# =====================================================
# RUTE WEB: OPERATOR LAPANGAN (KOLEKTOR)
# =====================================================
@app.route('/kolektor')
def halaman_kolektor():
    if 'petugas_nama' not in session: 
        return redirect('/')
    nama = session['petugas_nama']
    
    laporan_petugas = LaporanKolektor.query.filter_by(nama_petugas=nama).all()
    list_revisi = []
    for lp in laporan_petugas:
        b = Batch.query.get(lp.id_batch)
        if b and b.status_kolektor == 'Rejected':
            list_revisi.append({'id_batch': b.id_batch, 'catatan': b.catatan_kolektor})

    laporan_terakhir = LaporanKolektor.query.order_by(LaporanKolektor.waktu_submit.desc()).first()
    
    if laporan_terakhir:
        tanggal_terakhir = laporan_terakhir.id_batch 
        semua_setoran_terakhir = LaporanKolektor.query.filter_by(id_batch=tanggal_terakhir).all()
        list_nama = list(set([lp.nama_petugas for lp in semua_setoran_terakhir]))
        
        if len(list_nama) == 1:
            teks_penyetor = list_nama[0]
        elif len(list_nama) == 2:
            teks_penyetor = f"{list_nama[0]} dan {list_nama[1]}"
        else:
            teks_penyetor = ", ".join(list_nama[:-1]) + f", dan {list_nama[-1]}"
    else:
        tanggal_terakhir = None
        teks_penyetor = None

    return render_template('kolektor.html', 
                           nama_petugas=nama, 
                           list_revisi=list_revisi,
                           tanggal_terakhir=tanggal_terakhir,
                           teks_penyetor=teks_penyetor) 

@app.route('/submit_kolektor', methods=['POST'])
def submit_kolektor():
    tanggal_input = request.form.get('tanggal_kegiatan')
    if not tanggal_input:
        return "Tanggal kegiatan wajib diisi!", 400
        
    id_batch = tanggal_input 

    batch = Batch.query.get(id_batch)
    if not batch:
        tgl_obj = datetime.strptime(tanggal_input, '%Y-%m-%d').date()
        batch = Batch(
            id_batch=id_batch,
            tanggal=tgl_obj,
            status='Menunggu_Kurasi',
            status_kolektor='Pending'
        )
        db.session.add(batch)
        db.session.commit()

    if batch.status_kolektor == 'Rejected':
        batch.status_kolektor = 'Pending'
        batch.catatan_kolektor = None

    laporan = LaporanKolektor.query.filter_by(
        id_batch=id_batch,
        nama_petugas=session.get('petugas_nama')
    ).first()

    laporan_baru = False
    if not laporan:
        laporan = LaporanKolektor(
            id_batch=id_batch,
            nama_petugas=session.get('petugas_nama')
        )
        db.session.add(laporan)
        laporan_baru = True

    laporan.berat_kotor = float(request.form.get('berat_kotor', 0))

    lat_manual = request.form.get('latitude')
    lon_manual = request.form.get('longitude')
    
    if lat_manual and lon_manual:
        try:
            laporan.latitude = float(lat_manual.replace(',', '.'))
            laporan.longitude = float(lon_manual.replace(',', '.'))
        except ValueError:
            pass

    nama_aman = secure_filename(session.get('petugas_nama').replace(" ", "_"))
    FotoDokumentasi.query.filter(
        FotoDokumentasi.id_batch == id_batch,
        FotoDokumentasi.bagian == 'kolektor',
        FotoDokumentasi.path_foto.ilike(f"%_{nama_aman}_%")
    ).delete(synchronize_session=False)
    db.session.flush()

    mapping_foto = {
        'foto_sebelum': 'sebelum', 'foto_saat': 'saat', 'foto_setelah': 'setelah',
        'foto_karung_lokasi': 'karung_lokasi', 'foto_timbang_basah': 'timbang_basah', 'foto_fasilitas': 'fasilitas'
    }

    for field_name, kategori in mapping_foto.items():
        files = request.files.getlist(field_name)
        for i, f in enumerate(files):
            if f and f.filename:
                waktu_unik = datetime.utcnow().strftime("%H%M%S")
                fname = secure_filename(f"{id_batch}_{nama_aman}_{kategori}_{waktu_unik}_{f.filename}")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                f.save(save_path)
                db.session.add(
                    FotoDokumentasi(
                        id_batch=id_batch,
                        bagian='kolektor',
                        kategori_foto=kategori,
                        path_foto=f"static/uploads/{fname}",
                        is_selected=False
                    )
                )
                
                if field_name == 'foto_sebelum' and i == 0:
                    if not (lat_manual and lon_manual):
                        lat, lon = dapatkan_koordinat_exif(save_path)
                        if lat and lon:
                            laporan.latitude = lat
                            laporan.longitude = lon

    log = LogRiwayat(
        id_batch=id_batch, 
        aktor=session.get('petugas_nama'),
        aksi="Submit Kolektor" if laporan_baru else "Re-submit Kolektor",
        catatan=f"Menyetorkan data lapangan ({laporan.berat_kotor} Kg)."
    )
    db.session.add(log)
    db.session.commit()

    return render_template('success.html', pesan=f"Laporan Kolektor untuk tanggal {tanggal_input} berhasil disimpan!")

@app.route('/submit_sorter', methods=['POST'])
def submit_sorter():
    if request.method != 'POST':
        return redirect('/')

    tanggal_input = request.form.get('tanggal_kegiatan')
    if not tanggal_input:
        return "Error: Tanggal kegiatan kosong!", 400

    id_batch_input = tanggal_input

    batch = Batch.query.get(id_batch_input)
    if not batch:
        return """
        Data Kolektor untuk tanggal tersebut belum ada!
        Pastikan Kolektor sudah menyetorkan data terlebih dahulu sebelum disortir.
        """, 400
    
    list_kol = LaporanKolektor.query.filter_by(id_batch=id_batch_input).all()
    total_kolektor = sum([k.berat_kotor for k in list_kol if k.berat_kotor])

    total_input_sekarang = 0
    for kat in KategoriSampah.query.all():
        nilai = request.form.get(f'kategori_{kat.id}')
        if nilai:
            try:
                berat = float(nilai)
                if berat > 0:
                    total_input_sekarang += berat
            except ValueError:
                pass

    list_sor_lain = LaporanSorter.query.filter(
        LaporanSorter.id_batch == id_batch_input,
        LaporanSorter.nama_petugas != session.get('petugas_nama')
    ).all()
    
    total_sorter_lain = 0
    for s_lain in list_sor_lain:
        details = DetailSortiran.query.filter_by(id_sorter=s_lain.id).all()
        total_sorter_lain += sum([d.berat for d in details if d.berat])

    total_gabungan_sorter = total_input_sekarang + total_sorter_lain

    if total_gabungan_sorter > total_kolektor:
        sisa_kuota = total_kolektor - total_sorter_lain
        return f"""
        <div style="font-family: Arial, sans-serif; text-align: center; margin-top: 10%;">
            <h1 style="color: #d9534f;">⚠️ GAGAL DISIMPAN! ⚠️</h1>
            <h3 style="color: #333;">Total sampah yang disortir melebih batas.</h3>
            
            <div style="background-color: #f9f9f9; padding: 20px; border-radius: 10px; display: inline-block; text-align: left; border: 1px solid #ccc; font-size: 1.1em;">
                <p><b>Total Kotor Kolektor:</b> {total_kolektor} Kg</p>
                <p><b>Input Anda Sekarang:</b> <span style="color: red;">{total_input_sekarang} Kg</span></p>
                <p><b>Input Sorter Lainnya:</b> {total_sorter_lain} Kg</p>
                <hr>
                <p><b>Total Gabungan Sortiran:</b> <span style="color: red; font-weight: bold;">{total_gabungan_sorter} Kg</span> (Melebihi {total_gabungan_sorter - total_kolektor} Kg)</p>
            </div>
            
            <p style="color: #666; margin-top: 20px;">
                <i>*Volume sampah yang disortir boleh kurang karena air menguap,<br>
                tetapi secara logika tidak mungkin bertambah berat. Maksimal yang bisa Anda input adalah {sisa_kuota} Kg.</i>
            </p>
            
            <button onclick="window.history.back()" style="margin-top: 20px; padding: 12px 25px; font-size: 16px; background-color: #0275d8; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                ⬅️ Kembali & Perbaiki Angka
            </button>
        </div>
        """, 400

    if batch.status_sorter == 'Rejected':
        batch.status_sorter = 'Pending'
        batch.catatan_sorter = None
        if batch.status_kolektor != 'Rejected' and batch.status_presser != 'Rejected':
            batch.status = 'Menunggu_Kurasi'

    nama_aman = secure_filename(session.get('petugas_nama').replace(" ", "_"))

    FotoDokumentasi.query.filter(
        FotoDokumentasi.id_batch == id_batch_input,
        FotoDokumentasi.bagian == 'sorter',
        FotoDokumentasi.path_foto.ilike(f"%_{nama_aman}_%")
    ).delete(synchronize_session=False)

    for field in ['foto_bekerja', 'foto_seluruh_karung']:
        files = request.files.getlist(field)
        for i, f in enumerate(files):
            if f and f.filename:
                fname = secure_filename(f"sort_{field}_{id_batch_input}_{nama_aman}_{f.filename}")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                f.save(save_path)
                db.session.add(
                    FotoDokumentasi(
                        id_batch=id_batch_input, bagian='sorter', kategori_foto=field,
                        path_foto=f"static/uploads/{fname}", is_selected=False
                    )
                )

    sorter = LaporanSorter.query.filter_by(
        id_batch=id_batch_input, 
        nama_petugas=session.get('petugas_nama')
    ).first()
    sorter_baru = False

    if not sorter:
        sorter = LaporanSorter(id_batch=id_batch_input, nama_petugas=session.get('petugas_nama'))
        db.session.add(sorter)
        db.session.commit()
        sorter_baru = True

    details_lama = DetailSortiran.query.filter_by(id_sorter=sorter.id).all()
    for dl in details_lama:
        FotoKategori.query.filter_by(jenis='sorter', id_detail=dl.id).delete()
    DetailSortiran.query.filter_by(id_sorter=sorter.id).delete()

    for kat in KategoriSampah.query.all():
        nilai = request.form.get(f'kategori_{kat.id}')
        if not nilai: continue
        try:
            berat = float(nilai)
        except ValueError: continue
        if berat <= 0: continue

        detail = DetailSortiran(id_sorter=sorter.id, id_kategori=kat.id, berat=berat)
        db.session.add(detail)
        db.session.flush() 

        files = request.files.getlist(f'foto_karung_{kat.id}')
        for foto in files:
            if foto and foto.filename:
                fname = secure_filename(f"karung_{id_batch_input}_{nama_aman}_kat{kat.id}_{foto.filename}")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                foto.save(save_path)
                db.session.add(
                    FotoKategori(
                        jenis='sorter', id_detail=detail.id,
                        path_foto=f"static/uploads/{fname}", is_selected=False
                    )
                )

    log = LogRiwayat(
        id_batch=id_batch_input, aktor=session.get('petugas_nama'),
        aksi="Submit Sorter" if sorter_baru else "Re-submit Sorter",
        catatan="Mengupdate data hasil sortiran harian."
    )
    db.session.add(log)
    db.session.commit()

    return render_template('success.html', pesan=f"Laporan Sorter untuk tanggal {tanggal_input} berhasil disimpan!")

# =====================================================
# RUTE WEB: PRESSER
# =====================================================
@app.route('/presser')
def halaman_presser():
    if 'petugas_nama' not in session: 
        return redirect('/')
    nama = session['petugas_nama']
    kategori_dari_db = KategoriSampah.query.all()
    
    laporan_petugas = LaporanPresser.query.filter_by(nama_petugas=nama).all()
    list_revisi = []
    for lp in laporan_petugas:
        b = Batch.query.get(lp.id_batch)
        if b and b.status_presser == 'Rejected':
            list_revisi.append({'kode_karung': b.id_batch, 'catatan': b.catatan_presser})

    return render_template('presser.html', 
                           nama_petugas=nama, 
                           daftar_kategori=kategori_dari_db, 
                           list_revisi=list_revisi)

@app.route('/submit_presser', methods=['POST'])
def submit_presser():
    if request.method != 'POST':
        return redirect('/')

    tanggal_press = request.form.get('tanggal_kegiatan')
    kode_revisi = request.form.get('kode_karung', '').strip().upper()
    
    if not tanggal_press:
        return "Error: Tanggal kegiatan wajib diisi!", 400
        
    tgl_obj = datetime.strptime(tanggal_press, '%Y-%m-%d').date()
    files_bekerja = request.files.getlist('foto_bekerja')
    list_kode_terbuat = []

    PREFIX_KATEGORI = {
        "Gelas plastik": "GP", "Botol plastik bening": "BPB", "Botol plastik warna": "BPW", 
        "Botol keras": "BK", "Kontainer keras": "KK", "Kresek": "KRS", "Tutup botol": "TB", 
        "Alat makan plastik": "AMP", "Sedotan plastik": "SP", "Sachet/kemasan": "SC", 
        "Multilayer": "ML", "Sol sandal/sepatu": "SOL", "Styrofoam": "STY", 
        "Mainan/korek/sikat gigi/benda plastik kecil": "MIX", "Tetrapack": "TP", 
        "Ghostnet": "GN", "Pipa": "PIP", "Masker": "MSK", "Popok": "PPK", "Putung rokok": "PR"
    }

    if kode_revisi:
        batch = Batch.query.get(kode_revisi)
        if not batch: return "Error: Kode Karung Revisi tidak ditemukan!", 404
        
        if batch.status_presser == 'Rejected':
            batch.status_presser = 'Pending'
            batch.catatan_presser = None
            batch.status = 'Menunggu_Kurasi'

        FotoDokumentasi.query.filter_by(id_batch=kode_revisi, bagian='presser').delete()
        for i, f in enumerate(files_bekerja):
            if f and f.filename:
                fname = secure_filename(f"press_kerja_{kode_revisi}_{f.filename}")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                f.save(save_path)
                db.session.add(FotoDokumentasi(
                    id_batch=kode_revisi, bagian='presser', kategori_foto='foto_bekerja',
                    path_foto=f"static/uploads/{fname}", is_selected=False
                ))

        presser = LaporanPresser.query.filter_by(id_batch=kode_revisi).first()
        if not presser:
            presser = LaporanPresser(id_batch=kode_revisi, nama_petugas=session.get('petugas_nama'))
            db.session.add(presser)
            db.session.flush()

        details_lama = DetailPresser.query.filter_by(id_presser=presser.id).all()
        for dl in details_lama:
            FotoKategori.query.filter_by(jenis='presser', id_detail=dl.id).delete()
        DetailPresser.query.filter_by(id_presser=presser.id).delete()

        for kat in KategoriSampah.query.all():
            nilai = request.form.get(f'kategori_{kat.id}')
            if not nilai: continue
            try: berat = float(nilai)
            except ValueError: continue
            if berat <= 0: continue

            detail = DetailPresser(id_presser=presser.id, id_kategori=kat.id, berat=berat)
            db.session.add(detail)
            db.session.flush()

            files_bal = request.files.getlist(f'foto_bal_{kat.id}')
            for foto in files_bal:
                if foto and foto.filename:
                    fname = secure_filename(f"bal_{kode_revisi}_{kat.id}_{foto.filename}")
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                    foto.save(save_path)
                    db.session.add(FotoKategori(
                        jenis='presser', id_detail=detail.id, path_foto=f"static/uploads/{fname}", is_selected=False
                    ))
        
        log = LogRiwayat(id_batch=kode_revisi, aktor=session.get('petugas_nama'), aksi="Re-submit Presser", catatan="Merevisi data karung press.")
        db.session.add(log)
        db.session.commit()
        return render_template('success.html', pesan=f"Data Revisi Karung {kode_revisi} Berhasil Disimpan!")

    for kat in KategoriSampah.query.all():
        nilai = request.form.get(f'kategori_{kat.id}')
        if not nilai: continue
        try: berat = float(nilai)
        except ValueError: continue
        if berat <= 0: continue

        prefix = PREFIX_KATEGORI.get(kat.nama_kategori, f"K{kat.id}")
        tgl_str = tgl_obj.strftime('%y%m%d') 
        
        count_total = Batch.query.filter(Batch.id_batch.like(f"{prefix}-%")).count()
        urutan = count_total + 1
        
        kode_karung = f"{prefix}-{tgl_str}-{urutan:03d}" 
        
        while Batch.query.get(kode_karung):
            urutan += 1
            kode_karung = f"{prefix}-{tgl_str}-{urutan:03d}"

        batch = Batch(id_batch=kode_karung, tanggal=tgl_obj, status='Menunggu_Kurasi',
                      status_kolektor='Approved', status_sorter='Approved', status_presser='Pending')
        db.session.add(batch)
        
        presser = LaporanPresser(id_batch=kode_karung, nama_petugas=session.get('petugas_nama'))
        db.session.add(presser)
        db.session.flush()

        detail = DetailPresser(id_presser=presser.id, id_kategori=kat.id, berat=berat)
        db.session.add(detail)
        db.session.flush()

        files_bal = request.files.getlist(f'foto_bal_{kat.id}')
        for foto in files_bal:
            if foto and foto.filename:
                fname = secure_filename(f"bal_{kode_karung}_{kat.id}_{foto.filename}")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                foto.seek(0)
                foto.save(save_path)
                db.session.add(FotoKategori(
                    jenis='presser', id_detail=detail.id, path_foto=f"static/uploads/{fname}", is_selected=False
                ))
                
        list_kode_terbuat.append(kode_karung)
        
        log = LogRiwayat(id_batch=kode_karung, aktor=session.get('petugas_nama'), aksi="Submit Presser", catatan=f"Karung {kat.nama_kategori} didaftarkan otomatis.")
        db.session.add(log)

    if list_kode_terbuat:
        timestamp = datetime.utcnow().strftime("%H%M%S")
        for i, f in enumerate(files_bekerja):
            if f and f.filename:
                fname = secure_filename(f"press_kerja_{tanggal_press}_{timestamp}_{f.filename}")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                f.save(save_path)
                
                for kode in list_kode_terbuat:
                    db.session.add(FotoDokumentasi(
                        id_batch=kode, bagian='presser', kategori_foto='foto_bekerja',
                        path_foto=f"static/uploads/{fname}", is_selected=False
                    ))
    
    db.session.commit()

    if not list_kode_terbuat:
        return "Error: Tidak ada satupun angka berat kategori yang diisi!", 400

    pesan_sukses = f"""
    <div style="text-align: center;">
        <br>
        <h4 style="color: #28a745;">✅ Berhasil merekam {len(list_kode_terbuat)} Karung Bal!</h4>
        <br>
        <div style="background-color: #fff3cd; padding: 20px; border-radius: 8px; border: 2px dashed #ffc107; display: inline-block;">
            <h5 style="color: #856404; font-weight: bold; margin-bottom: 15px;">⚠️ TUGAS SELANJUTNYA ⚠️</h5>
            <p style="color: #333; margin-bottom: 15px;">
                Silakan ambil <b>spidol permanen</b> dan <b>labeli fisik karung</b> Anda <br>
                dengan nama batch di bawah ini agar tidak tertukar di gudang:
            </p>
            <div style="font-size: 1.5em; font-weight: bold; color: #000; background: white; padding: 10px 30px; border-radius: 5px; border: 1px solid #ffce3a; letter-spacing: 2px;">
                {"<hr style='margin: 10px 0;'>".join(list_kode_terbuat)}
            </div>
        </div>
    </div>
    """
    return render_template('success.html', pesan=pesan_sukses)

@app.route('/curator/select_photo', methods=['POST'])
def select_photo():
    foto_id = request.form.get('foto_id')
    foto = FotoKategori.query.get(foto_id)
    if not foto:
        return redirect(request.referrer)

    foto.is_selected = not foto.is_selected
    db.session.commit()
    return redirect(request.referrer)

@app.route('/curator/select_documentation', methods=['POST'])
def select_documentation():
    foto_id = request.form.get('foto_id')
    foto = FotoDokumentasi.query.get(foto_id)
    if not foto:
        return redirect(request.referrer)

    foto.is_selected = not foto.is_selected
    db.session.commit()
    return redirect(url_for('inspect_batch', id_batch=foto.id_batch))

# =====================================================
# RUTE WEB: MANAGEMENT (CURATOR)
# =====================================================
@app.route('/curator')
def dashboard_curator():
    if 'petugas_nama' not in session:
        return redirect('/')
    nama = session['petugas_nama']
    
    waktu_sekarang = datetime.utcnow() + timedelta(hours=7)
    default_bulan = '01' 
    default_tahun = waktu_sekarang.strftime('%Y')
    
    bulan_filter = request.args.get('bulan', default_bulan)
    tahun_filter = request.args.get('tahun', default_tahun)
    
    query_batches = Batch.query.filter(Batch.status != 'Draft').order_by(Batch.tanggal.desc()).all()
    tahun_tersedia = list(set([b.tanggal.strftime('%Y') for b in query_batches]))
    
    if not tahun_tersedia:
        tahun_tersedia = [default_tahun]
    elif default_tahun not in tahun_tersedia:
        tahun_tersedia.append(default_tahun)
        
    tahun_tersedia.sort(reverse=True)

    batches_harian = []
    batches_presser = []
    
    for b in query_batches:
        match_bulan = (bulan_filter == 'all' or b.tanggal.strftime('%m') == bulan_filter)
        match_tahun = (tahun_filter == 'all' or b.tanggal.strftime('%Y') == tahun_filter)
        if not (match_bulan and match_tahun):
            continue

        logs = LogRiwayat.query.filter_by(id_batch=b.id_batch).order_by(LogRiwayat.waktu.desc()).all()
        nama_kurator = "Pending Curation" 
        for log in logs:
            if 'Approved' in log.aksi or 'Rejected' in log.aksi or 'Revoke' in log.aksi:
                nama_kurator = log.aktor
                break
                
        cek_presser = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()
        list_kol = LaporanKolektor.query.filter_by(id_batch=b.id_batch).all()
        list_sor = LaporanSorter.query.filter_by(id_batch=b.id_batch).all()
        
        pengirim_presser = cek_presser.nama_petugas if cek_presser else "-"
        pengirim_kolektor = " & ".join([k.nama_petugas for k in list_kol]) if list_kol else "-" 
        pengirim_sorter = " & ".join([s.nama_petugas for s in list_sor]) if list_sor else "-" 
        
        item_data = {
            'data': b,
            'kurator': nama_kurator,
            'pengirim_presser': pengirim_presser,
            'pengirim_kolektor': pengirim_kolektor,
            'pengirim_sorter': pengirim_sorter
        }
        
        if cek_presser and not list_kol and not list_sor:
            batches_presser.append(item_data)
        else:
            batches_harian.append(item_data)

    return render_template('curator.html', 
                           batches_harian=batches_harian, 
                           batches_presser=batches_presser, 
                           nama_petugas=nama,
                           bulan_terpilih=bulan_filter,
                           tahun_terpilih=tahun_filter,
                           tahun_tersedia=tahun_tersedia)

@app.route('/curator/inspect/<id_batch>')
def inspect_batch(id_batch):
    if 'petugas_nama' not in session:
        return redirect('/')

    batch = Batch.query.get_or_404(id_batch)

    list_kol = LaporanKolektor.query.filter_by(id_batch=id_batch).all()
    kolektor_gabungan = None
    if list_kol:
        kolektor_gabungan = LaporanKolektor(
            nama_petugas=" & ".join([k.nama_petugas for k in list_kol]),
            waktu_submit=max([k.waktu_submit for k in list_kol if k.waktu_submit] or [datetime.utcnow()]),
            berat_kotor=sum([k.berat_kotor for k in list_kol if k.berat_kotor]),
            latitude=list_kol[0].latitude,
            longitude=list_kol[0].longitude
        )
        
        lokasi_list = []
        for k in list_kol:
            if k.latitude is not None and k.longitude is not None:
                lokasi_list.append({'nama': k.nama_petugas, 'lat': k.latitude, 'lon': k.longitude})
        
        kolektor_gabungan.lokasi = lokasi_list

    list_sor = LaporanSorter.query.filter_by(id_batch=id_batch).all()
    sorter_gabungan = None
    detail_sorter = []
    
    if list_sor:
        sorter_gabungan = LaporanSorter(
            nama_petugas=" & ".join([s.nama_petugas for s in list_sor]),
            waktu_submit=max([s.waktu_submit for s in list_sor if s.waktu_submit] or [datetime.utcnow()])
        )
        
        sorter_ids = [s.id for s in list_sor]
        details = db.session.query(
            DetailSortiran.id_kategori,
            KategoriSampah.nama_kategori,
            func.sum(DetailSortiran.berat).label('total_berat')
        ).join(
            KategoriSampah, DetailSortiran.id_kategori == KategoriSampah.id
        ).filter(
            DetailSortiran.id_sorter.in_(sorter_ids)
        ).group_by(
            DetailSortiran.id_kategori, KategoriSampah.nama_kategori
        ).all()

        for id_kat, nama, berat in details:
            fotos = db.session.query(FotoKategori).join(
                DetailSortiran, FotoKategori.id_detail == DetailSortiran.id
            ).filter(
                DetailSortiran.id_sorter.in_(sorter_ids),
                DetailSortiran.id_kategori == id_kat,
                FotoKategori.jenis == 'sorter'
            ).all()

            detail_sorter.append({'id': id_kat, 'nama': nama, 'berat': berat, 'fotos': fotos})

    presser = LaporanPresser.query.filter_by(id_batch=id_batch).first()
    detail_presser = []
    if presser:
        details_p = db.session.query(DetailPresser, KategoriSampah.nama_kategori)\
            .join(KategoriSampah, DetailPresser.id_kategori == KategoriSampah.id)\
            .filter(DetailPresser.id_presser == presser.id).all()
        for detail, nama in details_p:
            fotos = FotoKategori.query.filter_by(jenis='presser', id_detail=detail.id).all()
            detail_presser.append({'id': detail.id, 'nama': nama, 'berat': detail.berat, 'fotos': fotos})

    semua_foto = FotoDokumentasi.query.filter_by(id_batch=id_batch).all()
    logs_aktivitas = LogRiwayat.query.filter_by(id_batch=id_batch).order_by(LogRiwayat.waktu.asc()).all()

    return render_template(
        'inspect.html', batch=batch, 
        kolektor=kolektor_gabungan, sorter=sorter_gabungan, presser=presser,
        semua_foto=semua_foto, detail_sorter=detail_sorter, detail_presser=detail_presser,
        riwayat_log=logs_aktivitas
    )

@app.route('/curator/hapus_batch', methods=['POST'])
def hapus_batch():
    if 'petugas_nama' not in session: return redirect('/')
    id_batch = request.form.get('id_batch')
    batch = Batch.query.get(id_batch)
    if batch:
        db.session.delete(batch)
        db.session.commit()
    return redirect(url_for('dashboard_curator'))

@app.route('/curator/action', methods=['POST'])
def curator_action():
    if request.method == 'POST':
        id_batch = request.form.get('id_batch')
        part = request.form.get('part')
        action = request.form.get('action')
        catatan = request.form.get('catatan', '')
        
        batch = Batch.query.get(id_batch)
        
        if part == 'kolektor':
            batch.status_kolektor = 'Approved' if action == 'approve' else 'Rejected'
            batch.catatan_kolektor = catatan if action == 'reject' else None
        elif part == 'sorter':
            batch.status_sorter = 'Approved' if action == 'approve' else 'Rejected'
            batch.catatan_sorter = catatan if action == 'reject' else None
        elif part == 'presser':
            batch.status_presser = 'Approved' if action == 'approve' else 'Rejected'
            batch.catatan_presser = catatan if action == 'reject' else None
            
        cek_presser = LaporanPresser.query.filter_by(id_batch=id_batch).first()
        cek_kolektor = LaporanKolektor.query.filter_by(id_batch=id_batch).first()
        
        if cek_presser and not cek_kolektor:
            if batch.status_presser == 'Rejected':
                batch.status = 'Perlu_Revisi'
            elif batch.status_presser == 'Approved':
                batch.status = 'Disetujui'
            else:
                batch.status = 'Menunggu_Kurasi'
        else:
            if batch.status_kolektor == 'Rejected' or batch.status_sorter == 'Rejected':
                batch.status = 'Perlu_Revisi'
            elif batch.status_kolektor == 'Approved' and batch.status_sorter == 'Approved':
                batch.status = 'Disetujui' 
            else:
                batch.status = 'Menunggu_Kurasi'

        status_aksi = f"Approved ({part.capitalize()})" if action == 'approve' else f"Rejected ({part.capitalize()})"
        log = LogRiwayat(
            id_batch=id_batch,
            aktor=session.get('petugas_nama'), 
            aksi=status_aksi,
            catatan=catatan if action == 'reject' else f"{part.capitalize()} data components verified as valid."
        )
        db.session.add(log)
        db.session.commit()
        return redirect(url_for('inspect_batch', id_batch=id_batch))

@app.route('/curator/tarik_data', methods=['POST'])
def tarik_data_auditor():
    if 'petugas_nama' not in session:
        return redirect('/')
        
    id_batch = request.form.get('id_batch')
    batch = Batch.query.get(id_batch)
    
    if batch and batch.status == 'Disetujui':
        batch.status = 'Menunggu_Kurasi' 
        
        log = LogRiwayat(
            id_batch=id_batch,
            aktor=session.get('petugas_nama'),
            aksi="Revoked Data",
            catatan="Data revoked from Auditor Dashboard for re-curation." 
        )
        db.session.add(log)
        db.session.commit()
        
    return redirect(url_for('inspect_batch', id_batch=id_batch))

KAMUS_KATEGORI = {
    "Gelas plastik": "Plastic Cups",
    "Botol plastik bening": "Clear Plastic Bottles",
    "Botol plastik warna": "Colored Plastic Bottles",
    "Botol keras": "Hard Plastic Bottles",
    "Kontainer keras": "Hard Containers",
    "Kresek": "Plastic Bags",
    "Tutup botol": "Bottle Caps",
    "Alat makan plastik": "Plastic Cutlery",
    "Sedotan plastik": "Plastic Straws",
    "Sachet/kemasan": "Sachets / Packaging",
    "Multilayer": "Multilayer Plastics",
    "Sol sandal/sepatu": "Shoe / Sandal Soles",
    "Styrofoam": "Styrofoam",
    "Mainan/korek/sikat gigi/benda plastik kecil": "Small Plastics (Toys/Lighters/etc)",
    "Tetrapack": "Tetra Pak",
    "Ghostnet": "Ghost Nets",
    "Pipa": "Pipes",
    "Masker": "Face Masks",
    "Popok": "Diapers",
    "Putung rokok": "Cigarette Butts"
}

# =====================================================
# RUTE WEB: AUDITOR (DASHBOARD & ANALYTICS)
# =====================================================
@app.route('/auditor')
def dashboard_auditor():
    if 'petugas_nama' not in session:
        return redirect('/')
    nama_auditor = session['petugas_nama']

    waktu_sekarang = datetime.utcnow() + timedelta(hours=7)
    default_bulan = waktu_sekarang.strftime('%m')
    default_tahun = waktu_sekarang.strftime('%Y')

    bulan_filter = request.args.get('bulan', default_bulan)
    tahun_filter = request.args.get('tahun', default_tahun)

    query_batches = Batch.query.filter_by(status='Disetujui').order_by(Batch.tanggal.desc()).all()
    
    tahun_tersedia = list(set([b.tanggal.strftime('%Y') for b in Batch.query.filter_by(status='Disetujui').all()]))
    if not tahun_tersedia:
        tahun_tersedia = [default_tahun]
    elif default_tahun not in tahun_tersedia:
        tahun_tersedia.append(default_tahun)
    tahun_tersedia.sort(reverse=True)

    batches_valid = []
    for b in query_batches:
        match_bulan = (bulan_filter == 'all' or b.tanggal.strftime('%m') == bulan_filter)
        match_tahun = (tahun_filter == 'all' or b.tanggal.strftime('%Y') == tahun_filter)
        if match_bulan and match_tahun:
            batches_valid.append(b)

    dict_tanggal = {}
    dict_kategori = {}
    dict_presser = {}
    
    arsip_harian = []
    arsip_presser = []

    for b in batches_valid:
        kolektor = LaporanKolektor.query.filter_by(id_batch=b.id_batch).first()
        sorter = LaporanSorter.query.filter_by(id_batch=b.id_batch).first()
        presser = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()

        if kolektor:
            tgl_str = b.tanggal.strftime('%d %b %Y')
            dict_tanggal[tgl_str] = dict_tanggal.get(tgl_str, 0) + kolektor.berat_kotor

        if sorter:
            details = DetailSortiran.query.filter_by(id_sorter=sorter.id).all()
            for d in details:
                if d.berat > 0:
                    kat = KategoriSampah.query.get(d.id_kategori)
                    nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
                    dict_kategori[nama_inggris] = dict_kategori.get(nama_inggris, 0) + d.berat

        if presser:
            details_p = DetailPresser.query.filter_by(id_presser=presser.id).all()
            for d in details_p:
                if d.berat > 0:
                    kat = KategoriSampah.query.get(d.id_kategori)
                    nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
                    dict_presser[nama_inggris] = dict_presser.get(nama_inggris, 0) + d.berat

        log_kurator = LogRiwayat.query.filter(
            LogRiwayat.id_batch == b.id_batch, 
            LogRiwayat.aksi.like('%Approved%')
        ).order_by(LogRiwayat.waktu.desc()).first()
        
        nama_kurator = log_kurator.aktor if log_kurator else "System"

        item_arsip = {
            'id_batch': b.id_batch,
            'tanggal': b.tanggal,
            'kurator': nama_kurator
        }
        
        if presser and not kolektor and not sorter:
            arsip_presser.append(item_arsip)
        else:
            arsip_harian.append(item_arsip)

    return render_template('auditor.html',
                           arsip_harian=arsip_harian,
                           arsip_presser=arsip_presser,
                           labels_tanggal=list(dict_tanggal.keys()),
                           data_tanggal=list(dict_tanggal.values()),
                           labels_kategori=list(dict_kategori.keys()),
                           data_kategori=list(dict_kategori.values()),
                           labels_presser=list(dict_presser.keys()),
                           data_presser=list(dict_presser.values()),
                           bulan_terpilih=bulan_filter,
                           tahun_terpilih=tahun_filter,
                           tahun_tersedia=tahun_tersedia,
                           nama_petugas=nama_auditor)

@app.route('/auditor/download_photos/<id_batch>')
def download_selected_photos_auditor(id_batch):
    batch = Batch.query.filter_by(id_batch=id_batch).first()
    if not batch:
        flash('Data batch tidak ditemukan!', 'error')
        return redirect(url_for('dashboard_auditor'))
        
    memory_file = BytesIO()
    arsip_foto = [] 

    fotos_umum = FotoDokumentasi.query.filter_by(id_batch=id_batch, is_selected=True).all()
    for f in fotos_umum:
        kategori_asli = f.kategori_foto.lower() if f.kategori_foto else "lainnya"
        nama_cantik = "Foto"
        
        if f.bagian == 'kolektor':
            if kategori_asli == 'sebelum': nama_cantik = 'Before Cleanup'
            elif kategori_asli == 'saat': nama_cantik = 'During Cleanup'
            elif kategori_asli == 'setelah': nama_cantik = 'After Cleanup'
            elif kategori_asli == 'karung_lokasi': nama_cantik = 'Bags at Location'
            elif kategori_asli == 'timbang_basah': nama_cantik = 'Mixed Plastics Scale'
            elif kategori_asli == 'fasilitas': nama_cantik = 'Facilities'
            else: nama_cantik = kategori_asli.title()
        elif f.bagian == 'sorter':
            if 'bekerja' in kategori_asli: nama_cantik = 'Sorter at Work'
            elif 'seluruh_karung' in kategori_asli: nama_cantik = 'All Sorter Bags'
            else: nama_cantik = 'Sorter Documentation'
        elif f.bagian == 'presser':
            if 'bekerja' in kategori_asli: nama_cantik = 'Presser at Work'
            elif 'seluruh_press' in kategori_asli: nama_cantik = 'All Presser Bales'
            else: nama_cantik = 'Presser Documentation'
            
        arsip_foto.append({
            'path_asli': f.path_foto,
            'nama_baru': f"{id_batch}_{nama_cantik}_Doc{f.id}"
        })

    fotos_sorter = db.session.query(FotoKategori, KategoriSampah.nama_kategori)\
        .join(DetailSortiran, FotoKategori.id_detail == DetailSortiran.id)\
        .join(LaporanSorter, DetailSortiran.id_sorter == LaporanSorter.id)\
        .join(KategoriSampah, DetailSortiran.id_kategori == KategoriSampah.id)\
        .filter(LaporanSorter.id_batch == id_batch, FotoKategori.jenis == 'sorter', FotoKategori.is_selected == True).all()

    for f, nama_kategori in fotos_sorter:
        arsip_foto.append({
            'path_asli': f.path_foto,
            'nama_baru': f"{id_batch}_Detailed Sorted Weight - {nama_kategori}_Kat{f.id}"
        })

    fotos_presser = db.session.query(FotoKategori, KategoriSampah.nama_kategori)\
        .join(DetailPresser, FotoKategori.id_detail == DetailPresser.id)\
        .join(LaporanPresser, DetailPresser.id_presser == LaporanPresser.id)\
        .join(KategoriSampah, DetailPresser.id_kategori == KategoriSampah.id)\
        .filter(LaporanPresser.id_batch == id_batch, FotoKategori.jenis == 'presser', FotoKategori.is_selected == True).all()

    for f, nama_kategori in fotos_presser:
        arsip_foto.append({
            'path_asli': f.path_foto,
            'nama_baru': f"{id_batch}_Final Bale - {nama_kategori}_Kat{f.id}"
        })

    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in arsip_foto:
            nama_file_fisik = os.path.basename(item['path_asli'])
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], nama_file_fisik)
            
            if os.path.exists(file_path):
                ext = os.path.splitext(nama_file_fisik)[1]
                nama_final = f"{item['nama_baru']}{ext}"
                zf.write(file_path, arcname=nama_final)

    memory_file.seek(0)
    return send_file(
        memory_file, 
        download_name=f"Seribu_Biru_Photos_{id_batch}.zip", 
        as_attachment=True
    )

@app.route('/export_csv_harian')
def export_csv_harian():
    if 'petugas_nama' not in session:
        return redirect('/')
        
    si = StringIO()
    cw = csv.writer(si)
    kategori_all = KategoriSampah.query.order_by(KategoriSampah.id).all()
    
    header = [
        'Batch_ID', 'Activity_Date', 'Final_Status', 
        'Collector_Time_WIB', 'Collector_Name', 'Gross_Weight_Kg', 'Location_Coordinates', 
        'Sorter_Time_WIB', 'Sorter_Name'
    ]
    for kat in kategori_all:
        nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
        header.append(f"{nama_inggris}_(Kg)")
    header.extend(['Curator_Time_WIB', 'Curator_Name'])
    cw.writerow(header)
    
    batches = Batch.query.filter_by(status='Disetujui').order_by(Batch.tanggal.desc()).all()
    
    for b in batches:
        list_kol = LaporanKolektor.query.filter_by(id_batch=b.id_batch).all()
        list_sor = LaporanSorter.query.filter_by(id_batch=b.id_batch).all()
        presser = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()
        
        if presser and not list_kol and not list_sor: 
            continue

        row = [b.id_batch, b.tanggal.strftime('%Y-%m-%d'), b.status]
        
        if list_kol:
            waktu_terakhir = max([k.waktu_submit for k in list_kol if k.waktu_submit] or [datetime.utcnow()])
            waktu_kol = (waktu_terakhir + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')
            nama_kol = " & ".join([k.nama_petugas for k in list_kol])
            berat_kol = sum([k.berat_kotor for k in list_kol if k.berat_kotor])
            
            lokasi_list = []
            for k in list_kol:
                if k.latitude is not None and k.longitude is not None:
                    lokasi_list.append(f"{k.latitude}, {k.longitude}")
            
            lokasi_str = " | ".join(lokasi_list) if lokasi_list else "-"
            row.extend([waktu_kol, nama_kol, berat_kol, lokasi_str])
        else:
            row.extend(['-', '-', 0, '-'])
            
        if list_sor:
            waktu_terakhir = max([s.waktu_submit for s in list_sor if s.waktu_submit] or [datetime.utcnow()])
            waktu_sorter = (waktu_terakhir + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')
            nama_sorter = " & ".join([s.nama_petugas for s in list_sor])
            row.extend([waktu_sorter, nama_sorter])
            
            sorter_ids = [s.id for s in list_sor]
            detail_s = DetailSortiran.query.filter(DetailSortiran.id_sorter.in_(sorter_ids)).all()
            
            dict_s = {}
            for d in detail_s:
                dict_s[d.id_kategori] = dict_s.get(d.id_kategori, 0) + d.berat
                
            for kat in kategori_all:
                row.append(dict_s.get(kat.id, 0))
        else:
            row.extend(['-', '-'])
            for kat in kategori_all:
                row.append(0)
                
        log_kurator = LogRiwayat.query.filter(
            LogRiwayat.id_batch == b.id_batch, 
            LogRiwayat.aksi.like('%Approved%')
        ).order_by(LogRiwayat.waktu.desc()).first()
        
        if log_kurator and log_kurator.waktu:
            waktu_kurasi = (log_kurator.waktu + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')
            row.extend([waktu_kurasi, log_kurator.aktor])
        else:
            row.extend(['-', '-'])
            
        cw.writerow(row)
        
    output = Response(si.getvalue(), mimetype='text/csv')
    output.headers["Content-Disposition"] = "attachment; filename=Seribu_Biru_Daily_Report.csv"
    return output

@app.route('/export_csv_presser')
def export_csv_presser():
    si = StringIO()
    cw = csv.writer(si)
    kategori_all = KategoriSampah.query.order_by(KategoriSampah.id).all()
    
    header = ['Unique_Bale_Code', 'Pressing_Date', 'Final_Status', 'Presser_Time_WIB', 'Presser_Name']
    for kat in kategori_all:
        nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
        header.append(f"{nama_inggris}_(Kg)")
    header.extend(['Curator_Time_WIB', 'Curator_Name'])
    cw.writerow(header)
    
    batches = Batch.query.filter_by(status='Disetujui').order_by(Batch.tanggal.desc()).all()
    for b in batches:
        kol = LaporanKolektor.query.filter_by(id_batch=b.id_batch).first()
        sorter = LaporanSorter.query.filter_by(id_batch=b.id_batch).first()
        presser = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()
        
        if not (presser and not kol and not sorter): 
            continue

        row = [b.id_batch, b.tanggal.strftime('%Y-%m-%d'), b.status]
        
        if presser and presser.waktu_submit:
            waktu_presser = (presser.waktu_submit + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')
            row.extend([waktu_presser, presser.nama_petugas])
            detail_p = DetailPresser.query.filter_by(id_presser=presser.id).all()
            dict_p = {d.id_kategori: d.berat for d in detail_p}
            for kat in kategori_all:
                row.append(dict_p.get(kat.id, 0))
        else:
            row.extend(['-', '-'])
            for kat in kategori_all:
                row.append(0)

        log_kurator = LogRiwayat.query.filter(LogRiwayat.id_batch == b.id_batch, LogRiwayat.aksi.like('%Approved%')).order_by(LogRiwayat.waktu.desc()).first()
        if log_kurator and log_kurator.waktu:
            waktu_kurasi = (log_kurator.waktu + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')
            row.extend([waktu_kurasi, log_kurator.aktor])
        else:
            row.extend(['-', '-'])
            
        cw.writerow(row)
        
    output = Response(si.getvalue(), mimetype='text/csv')
    output.headers["Content-Disposition"] = "attachment; filename=Seribu_Biru_Press_Bales.csv"
    return output

# =====================================================
# RUTE WEB: SUPER ADMIN (PERFORMA OPERATOR & TRACKING)
# =====================================================
@app.route('/performa')
def halaman_performa():
    if session.get('petugas_nama') != 'Super Admin':
        return "Akses Ditolak: Halaman ini bersifat rahasia dan khusus Super Admin.", 403

    kolektor_stats = db.session.query(
        LaporanKolektor.nama_petugas,
        func.count(func.distinct(case((Batch.status_kolektor == 'Approved', LaporanKolektor.id_batch), else_=None))).label('total_kerja'),
        func.sum(case((Batch.status_kolektor == 'Approved', LaporanKolektor.berat_kotor), else_=0)).label('total_kg'),
        func.count(func.distinct(case((Batch.status_kolektor == 'Rejected', LaporanKolektor.id_batch), else_=None))).label('total_revisi')
    ).join(Batch, LaporanKolektor.id_batch == Batch.id_batch)\
     .group_by(LaporanKolektor.nama_petugas).all()

    sorter_stats = db.session.query(
        LaporanSorter.nama_petugas,
        func.count(func.distinct(case((Batch.status_sorter == 'Approved', LaporanSorter.id_batch), else_=None))).label('total_kerja'),
        func.sum(case((Batch.status_sorter == 'Approved', DetailSortiran.berat), else_=0)).label('total_kg'),
        func.count(func.distinct(case((Batch.status_sorter == 'Rejected', LaporanSorter.id_batch), else_=None))).label('total_revisi')
    ).join(Batch, LaporanSorter.id_batch == Batch.id_batch)\
     .outerjoin(DetailSortiran, LaporanSorter.id == DetailSortiran.id_sorter)\
     .group_by(LaporanSorter.nama_petugas).all()

    presser_stats = db.session.query(
        LaporanPresser.nama_petugas,
        func.count(func.distinct(case((Batch.status_presser == 'Approved', LaporanPresser.id_batch), else_=None))).label('total_kerja'),
        func.sum(case((Batch.status_presser == 'Approved', DetailPresser.berat), else_=0)).label('total_kg'),
        func.count(func.distinct(case((Batch.status_presser == 'Rejected', LaporanPresser.id_batch), else_=None))).label('total_revisi')
    ).join(Batch, LaporanPresser.id_batch == Batch.id_batch)\
     .outerjoin(DetailPresser, LaporanPresser.id == DetailPresser.id_presser)\
     .group_by(LaporanPresser.nama_petugas).all()

    semua_batch = Batch.query.order_by(Batch.tanggal.desc()).all()
    tracking_data = []

    for b in semua_batch:
        kol = LaporanKolektor.query.filter_by(id_batch=b.id_batch).first()
        sor = LaporanSorter.query.filter_by(id_batch=b.id_batch).first()
        prs = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()

        def format_waktu(waktu_db):
            if waktu_db:
                return (waktu_db + timedelta(hours=7)).strftime('%d %b %Y, %H:%M')
            return None

        stat_kol = 'Submitted' if kol and b.status_kolektor in ['Pending', None, ''] else (b.status_kolektor or 'Pending')
        stat_sor = 'Submitted' if sor and b.status_sorter in ['Pending', None, ''] else (b.status_sorter or 'Pending')
        stat_prs = 'Submitted' if prs and b.status_presser in ['Pending', None, ''] else (b.status_presser or 'Pending')

        tracking_data.append({
            'id_batch': b.id_batch,
            'status_akhir': b.status,
            'kol_status': stat_kol,
            'kol_nama': kol.nama_petugas if kol else '-',
            'kol_waktu': format_waktu(kol.waktu_submit) if kol else '-',
            'sor_status': stat_sor,
            'sor_nama': sor.nama_petugas if sor else '-',
            'sor_waktu': format_waktu(sor.waktu_submit) if sor else '-',
            'prs_status': stat_prs,
            'prs_nama': prs.nama_petugas if prs else '-',
            'prs_waktu': format_waktu(prs.waktu_submit) if prs else '-'
        })

    riwayat_hapus = RiwayatHapus.query.order_by(RiwayatHapus.waktu_hapus.desc()).all()

    return render_template('performa.html', 
                           kolektor=kolektor_stats, 
                           sorter=sorter_stats, 
                           presser=presser_stats,
                           tracking=tracking_data,
                           riwayat_hapus=riwayat_hapus,
                           nama_admin=session.get('petugas_nama'))

@app.route('/superadmin/hapus_batch/<id_batch>', methods=['POST'])
def superadmin_hapus_batch(id_batch):
    if session.get('petugas_nama') != 'Super Admin':
        return "Akses Ditolak: Hanya Super Admin yang dapat menghapus data.", 403

    batch = db.session.get(Batch, id_batch)
    if not batch:
        return redirect(url_for('halaman_performa'))

    alasan = request.form.get('alasan_hapus', '').strip()
    if not alasan:
        alasan = "Dihapus tanpa alasan spesifik."

    log_hapus = RiwayatHapus(
        id_batch=id_batch,
        aktor=session.get('petugas_nama'),
        keterangan=f"Alasan: {alasan} (Semua data dan foto fisik telah musnah)"
    )
    db.session.add(log_hapus)

    fotos_umum = FotoDokumentasi.query.filter_by(id_batch=id_batch).all()
    for f in fotos_umum:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(f.path_foto))
        if os.path.exists(file_path):
            os.remove(file_path)
    FotoDokumentasi.query.filter_by(id_batch=id_batch).delete()

    sorter = LaporanSorter.query.filter_by(id_batch=id_batch).first()
    if sorter:
        details_s = DetailSortiran.query.filter_by(id_sorter=sorter.id).all()
        for ds in details_s:
            fotos_kat = FotoKategori.query.filter_by(jenis='sorter', id_detail=ds.id).all()
            for fk in fotos_kat:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(fk.path_foto))
                if os.path.exists(file_path):
                    os.remove(file_path)
            FotoKategori.query.filter_by(jenis='sorter', id_detail=ds.id).delete()
        DetailSortiran.query.filter_by(id_sorter=sorter.id).delete()

    presser = LaporanPresser.query.filter_by(id_batch=id_batch).first()
    if presser:
        details_p = DetailPresser.query.filter_by(id_presser=presser.id).all()
        for dp in details_p:
            fotos_kat = FotoKategori.query.filter_by(jenis='presser', id_detail=dp.id).all()
            for fk in fotos_kat:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(fk.path_foto))
                if os.path.exists(file_path):
                    os.remove(file_path)
            FotoKategori.query.filter_by(jenis='presser', id_detail=dp.id).delete()
        DetailPresser.query.filter_by(id_presser=presser.id).delete()

    db.session.delete(batch)
    db.session.commit()

    flash(f'Batch {id_batch} telah berhasil dihapus permanen!', 'success')
    return redirect(url_for('halaman_performa'))

# =====================================================
# RUTE WEB: MANAJEMEN GUDANG (INVENTORY)
# =====================================================
@app.route('/gudang')
def halaman_gudang():
    if 'petugas_nama' not in session:
        return redirect('/')
        
    batches = Batch.query.filter_by(status='Disetujui').all()
    
    list_gudang = []
    total_gudang_kg = 0
    total_terjual_kg = 0
    
    kategori_gudang = {}
    kategori_terjual = {}
    kategori_sorter = {} 
    
    semua_kategori = KategoriSampah.query.all()
    for k in semua_kategori:
        nama_inggris = KAMUS_KATEGORI.get(k.nama_kategori, k.nama_kategori)
        kategori_gudang[nama_inggris] = 0
        kategori_terjual[nama_inggris] = 0
        kategori_sorter[nama_inggris] = 0 

    for b in batches:
        kol = LaporanKolektor.query.filter_by(id_batch=b.id_batch).first()
        sor = LaporanSorter.query.filter_by(id_batch=b.id_batch).first()
        prs = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()
        
        if prs and not kol and not sor:
            gudang_info = DataGudang.query.filter_by(id_batch=b.id_batch).first()
            status_stok = gudang_info.status_stok if gudang_info else 'Di Gudang'
            pembeli = gudang_info.pembeli if gudang_info and gudang_info.pembeli else '-'
            catatan_jual = gudang_info.catatan_jual if gudang_info and gudang_info.catatan_jual else '-'
            tgl_keluar = (gudang_info.tanggal_keluar + timedelta(hours=7)).strftime('%d-%m-%Y') if gudang_info and gudang_info.tanggal_keluar else '-'
            
            berat_total_batch = 0
            detail_kategori_str = []
            
            details = DetailPresser.query.filter_by(id_presser=prs.id).all()
            for d in details:
                if d.berat > 0:
                    kat = KategoriSampah.query.get(d.id_kategori)
                    nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
                    berat_total_batch += d.berat
                    detail_kategori_str.append(f"{nama_inggris} ({d.berat} Kg)")
                    
                    if status_stok == 'Di Gudang':
                        kategori_gudang[nama_inggris] += d.berat
                    else:
                        kategori_terjual[nama_inggris] += d.berat
                        
            if status_stok == 'Di Gudang':
                total_gudang_kg += berat_total_batch
            else:
                total_terjual_kg += berat_total_batch
                
            list_gudang.append({
                'id_batch': b.id_batch,
                'tanggal_press': b.tanggal.strftime('%Y-%m-%d'),
                'rincian': ", ".join(detail_kategori_str),
                'berat_total': berat_total_batch,
                'status_stok': status_stok,
                'pembeli': pembeli,
                'catatan_jual': catatan_jual, 
                'tanggal_keluar': tgl_keluar
            })
            
    list_gudang.sort(key=lambda x: x['tanggal_press'], reverse=True)
    
    stok_sorter_list = []
    total_sisa_sorter_kg = 0
    
    for kat in semua_kategori:
        total_in = db.session.query(func.sum(DetailSortiran.berat))\
            .join(LaporanSorter, DetailSortiran.id_sorter == LaporanSorter.id)\
            .join(Batch, LaporanSorter.id_batch == Batch.id_batch)\
            .filter(DetailSortiran.id_kategori == kat.id, Batch.status_sorter == 'Approved').scalar() or 0
            
        total_out = db.session.query(func.sum(DetailPresser.berat))\
            .join(LaporanPresser, DetailPresser.id_presser == LaporanPresser.id)\
            .join(Batch, LaporanPresser.id_batch == Batch.id_batch)\
            .filter(DetailPresser.id_kategori == kat.id, Batch.status_presser == 'Approved').scalar() or 0
            
        sisa = total_in - total_out
        if sisa < 0: 
            sisa = 0 
            
        nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
        kategori_sorter[nama_inggris] = round(sisa, 2)
            
        if total_in > 0 or total_out > 0:
            stok_sorter_list.append({
                'nama_kategori': nama_inggris,
                'total_sortir': round(total_in, 2),
                'total_press': round(total_out, 2),
                'sisa_stok': round(sisa, 2)
            })
            total_sisa_sorter_kg += sisa
            
    stok_sorter_list.sort(key=lambda x: x['sisa_stok'], reverse=True)

    return render_template('gudang.html',
                           list_gudang=list_gudang,
                           total_gudang_kg=total_gudang_kg,
                           total_terjual_kg=total_terjual_kg,
                           labels_kategori=list(kategori_gudang.keys()),
                           data_gudang=list(kategori_gudang.values()),
                           data_terjual=list(kategori_terjual.values()),
                           data_sorter=list(kategori_sorter.values()), 
                           stok_sorter_list=stok_sorter_list,         
                           total_sisa_sorter_kg=round(total_sisa_sorter_kg, 2), 
                           nama_petugas=session['petugas_nama'])

@app.route('/gudang/jual', methods=['POST'])
def jual_gudang():
    if 'petugas_nama' not in session: 
        return redirect('/')
    
    id_batch = request.form.get('id_batch')
    pembeli = request.form.get('pembeli')
    catatan_jual = request.form.get('catatan_jual') 
    
    if id_batch and pembeli:
        gudang = DataGudang.query.filter_by(id_batch=id_batch).first()
        if not gudang:
            gudang = DataGudang(id_batch=id_batch)
            db.session.add(gudang)
            
        gudang.status_stok = 'Terjual'
        gudang.pembeli = pembeli
        gudang.catatan_jual = catatan_jual 
        gudang.tanggal_keluar = datetime.utcnow()
        
        log = LogRiwayat(
            id_batch=id_batch,
            aktor=session.get('petugas_nama'),
            aksi="Sold (Out)",
            catatan=f"Bale has been sold to: {pembeli}. Note: {catatan_jual}"
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f"✅ Berhasil: Karung Bal {id_batch} telah laku terjual kepada {pembeli}!", "success")
        
    return redirect('/gudang')

@app.route('/gudang/batal_jual', methods=['POST'])
def batal_jual_gudang():
    if 'petugas_nama' not in session: 
        return redirect('/')
    
    id_batch = request.form.get('id_batch')
    
    if id_batch:
        gudang = DataGudang.query.filter_by(id_batch=id_batch).first()
        if gudang and gudang.status_stok == 'Terjual':
            gudang.status_stok = 'Di Gudang'
            gudang.pembeli = None
            gudang.catatan_jual = None
            gudang.tanggal_keluar = None
            
            log = LogRiwayat(
                id_batch=id_batch,
                aktor=session.get('petugas_nama'),
                aksi="Sale Cancelled (Refund)",
                catatan="Sale cancelled (Refund), bale returned to warehouse stock."
            )
            db.session.add(log)
            db.session.commit()
            
            flash(f"⚠️ Dibatalkan: Penjualan {id_batch} ditarik kembali ke stok Gudang.", "warning")
            
    return redirect('/gudang')

@app.route('/export_csv_gudang')
def export_csv_gudang():
    if 'petugas_nama' not in session:
        return redirect('/')
        
    si = StringIO()
    cw = csv.writer(si)
    
    cw.writerow(['--- SORTER INVENTORY (WORK IN PROGRESS) ---'])
    cw.writerow(['Material_Category', 'Total_Sorted_In_(Kg)', 'Total_Pressed_Out_(Kg)', 'Remaining_Stock_(Kg)'])
    
    semua_kategori = KategoriSampah.query.all()
    for kat in semua_kategori:
        total_in = db.session.query(func.sum(DetailSortiran.berat))\
            .join(LaporanSorter, DetailSortiran.id_sorter == LaporanSorter.id)\
            .join(Batch, LaporanSorter.id_batch == Batch.id_batch)\
            .filter(DetailSortiran.id_kategori == kat.id, Batch.status_sorter == 'Approved').scalar() or 0
            
        total_out = db.session.query(func.sum(DetailPresser.berat))\
            .join(LaporanPresser, DetailPresser.id_presser == LaporanPresser.id)\
            .join(Batch, LaporanPresser.id_batch == Batch.id_batch)\
            .filter(DetailPresser.id_kategori == kat.id, Batch.status_presser == 'Approved').scalar() or 0
            
        sisa = total_in - total_out
        if sisa < 0: 
            sisa = 0 
            
        if total_in > 0 or total_out > 0:
            nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
            cw.writerow([nama_inggris, round(total_in, 2), round(total_out, 2), round(sisa, 2)])
            
    cw.writerow([])
    cw.writerow([])

    cw.writerow(['--- PRESSER INVENTORY (FINISHED GOODS) ---'])
    header_press = ['Bale_Code', 'Press_Finished_Date', 'Material_Details', 'Total_Weight_(Kg)', 'Warehouse_Status', 'Buyer_Name', 'Sale_Note', 'Release_Date_Sold']
    cw.writerow(header_press)
    
    batches = Batch.query.filter_by(status='Disetujui').order_by(Batch.tanggal.desc()).all()
    
    for b in batches:
        kol = LaporanKolektor.query.filter_by(id_batch=b.id_batch).first()
        sor = LaporanSorter.query.filter_by(id_batch=b.id_batch).first()
        prs = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()
        
        if prs and not kol and not sor:
            gudang_info = DataGudang.query.filter_by(id_batch=b.id_batch).first()
            status_stok = gudang_info.status_stok if gudang_info else 'Di Gudang'
            status_stok_en = 'In Warehouse' if status_stok == 'Di Gudang' else 'Sold'
            pembeli = gudang_info.pembeli if gudang_info and gudang_info.pembeli else '-'
            catatan_jual = gudang_info.catatan_jual if gudang_info and gudang_info.catatan_jual else '-'
            
            tgl_keluar = '-'
            if gudang_info and gudang_info.tanggal_keluar:
                tgl_keluar = (gudang_info.tanggal_keluar + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M WIB')
            
            berat_total = 0
            rincian = []
            details = DetailPresser.query.filter_by(id_presser=prs.id).all()
            for d in details:
                if d.berat > 0:
                    kat = KategoriSampah.query.get(d.id_kategori)
                    nama_inggris = KAMUS_KATEGORI.get(kat.nama_kategori, kat.nama_kategori)
                    berat_total += d.berat
                    rincian.append(f"{nama_inggris} ({d.berat}Kg)")
                    
            row = [
                b.id_batch,
                b.tanggal.strftime('%Y-%m-%d'),
                " | ".join(rincian),
                berat_total,
                status_stok_en,
                pembeli,
                catatan_jual,
                tgl_keluar
            ]
            cw.writerow(row)
            
    output = Response(si.getvalue(), mimetype='text/csv')
    output.headers["Content-Disposition"] = "attachment; filename=Seribu_Biru_Full_Inventory.csv"
    return output

@app.route('/superadmin/bersihkan_storage', methods=['POST'])
def bersihkan_storage():
    if session.get('petugas_nama') != 'Super Admin':
        return redirect('/')

    batas_waktu = datetime.utcnow().date() - timedelta(days=1)
    batches_lama = Batch.query.filter(Batch.tanggal < batas_waktu).all()
    jumlah_file_terhapus = 0

    for b in batches_lama:
        fotos_umum = FotoDokumentasi.query.filter_by(id_batch=b.id_batch).all()
        for f in fotos_umum:
            path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(f.path_foto))
            if os.path.exists(path):
                os.remove(path)
                jumlah_file_terhapus += 1
        FotoDokumentasi.query.filter_by(id_batch=b.id_batch).delete()

        sorter = LaporanSorter.query.filter_by(id_batch=b.id_batch).first()
        if sorter:
            details_s = DetailSortiran.query.filter_by(id_sorter=sorter.id).all()
            for ds in details_s:
                fotos_kat = FotoKategori.query.filter_by(jenis='sorter', id_detail=ds.id).all()
                for fk in fotos_kat:
                    path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(fk.path_foto))
                    if os.path.exists(path):
                        os.remove(path)
                        jumlah_file_terhapus += 1
                FotoKategori.query.filter_by(jenis='sorter', id_detail=ds.id).delete()

        presser = LaporanPresser.query.filter_by(id_batch=b.id_batch).first()
        if presser:
            details_p = DetailPresser.query.filter_by(id_presser=presser.id).all()
            for dp in details_p:
                fotos_kat = FotoKategori.query.filter_by(jenis='presser', id_detail=dp.id).all()
                for fk in fotos_kat:
                    path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(fk.path_foto))
                    if os.path.exists(path):
                        os.remove(path)
                        jumlah_file_terhapus += 1
                FotoKategori.query.filter_by(jenis='presser', id_detail=dp.id).delete()

    db.session.commit()

    if jumlah_file_terhapus > 0:
        log_hapus = RiwayatHapus(
            id_batch="AUTO-CLEANUP SERVER",
            aktor=session.get('petugas_nama'),
            keterangan=f"Membersihkan storage: {jumlah_file_terhapus} file foto fisik yang berumur lebih dari 1 bulan telah dimusnahkan. Data teks & metrik angka tetap dipertahankan."
        )
        db.session.add(log_hapus)
        db.session.commit()
        flash(f'Server lega! {jumlah_file_terhapus} foto usang berhasil dibersihkan dari storage.', 'success')
    else:
        flash('Storage masih aman! Tidak ada foto yang usianya lebih dari 30 hari.', 'info')

    return redirect('/performa')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)