# 1. Gunakan sistem operasi Linux ringan yang sudah terpasang Python 3.10
FROM python:3.10-slim

# 2. Buat folder bernama /app di dalam kontainer sebagai ruang kerja
WORKDIR /app

# 3. Salin file daftar library (requirements.txt) dari laptop ke dalam kontainer
COPY requirements.txt .

# 4. Instal semua library yang dibutuhkan (termasuk Flask, dll)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Instal Gunicorn (mesin penggerak web) untuk berjaga-jaga jika belum ada di requirements
RUN pip install gunicorn

# 6. Salin SELURUH sisa kode aplikasi Anda dari laptop ke dalam kontainer
COPY . .

# 7. Beri tahu kontainer untuk membuka lubang komunikasi di Port 8000
EXPOSE 8000

# 8. Perintah untuk menyalakan aplikasi saat kontainer dihidupkan
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]