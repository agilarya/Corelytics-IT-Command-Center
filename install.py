import subprocess
import sys

with open('log_install.txt', 'w') as log_file:
    try:
        log_file.write("Memulai instalasi...\n")
        
        # Eksekusi pip install secara paksa lewat sistem
        proses = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            capture_output=True, text=True
        )
        
        log_file.write("--- HASIL OUTPUT ---\n")
        log_file.write(proses.stdout + "\n")
        
        log_file.write("--- PESAN ERROR (KALAU ADA) ---\n")
        log_file.write(proses.stderr + "\n")
        
        log_file.write("\nProses Selesai dengan Kode: " + str(proses.returncode))
        
    except Exception as e:
        log_file.write("SISTEM GAGAL MENGEKSEKUSI:\n" + str(e))