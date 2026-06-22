import requests
import psutil
import socket
import math
import subprocess
import json
import os
import winreg
import threading
import schedule
import time
from flask import Flask, request, jsonify

# ==========================================
# KONFIGURASI AGENT LOKAL (AREA PRODUKSI)
# ==========================================
GATEWAY_URL = "http://192.168.0.0:5000/api/relay"
SECRET_TOKEN = "IT_Command_Center"
HOSTNAME_PC = socket.gethostname()

app_agent = Flask(__name__)

def ambil_ip_asli():
    """Ambil IP LAN asli yang nyambung ke jaringan (Abaikan IP VirtualBox/VMware)"""
    try:
        # Bikin soket bohongan buat ngecek rute IP ke arah Gateway
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Tembak IP Gateway Proxmox lu (nggak harus beneran konek)
        s.connect(("192.168.22.238", 80)) 
        ip_lokal = s.getsockname()[0]
        s.close()
        return ip_lokal
    except Exception:
        return '127.0.0.1'

def get_real_cpu_name():
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return cpu_name.strip()
    except Exception:
        return "CPU Tidak Terdeteksi"

def get_total_disk_size():
    try:
        total_bytes = 0
        for part in psutil.disk_partitions(all=False):
            if os.name == 'nt' and ('cdrom' in part.opts or part.fstype == ''):
                continue
            usage = psutil.disk_usage(part.mountpoint)
            total_bytes += usage.total
        return f"{math.ceil(total_bytes / (1024**3))} GB"
    except Exception:
        return "Gagal Hitung Disk"

def get_all_partitions():
    parts = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            total = math.ceil(usage.total / (1024**3))
            parts.append(f"{part.device} ({total}GB)")
        except: continue
    return ", ".join(parts)

def get_ssd_health_smart():
    try:
        cmd_wmi = 'wmic diskdrive get status'
        status_wmi = subprocess.check_output(cmd_wmi, shell=True).decode('utf-8').strip()
        
        if "OK" not in status_wmi and status_wmi != "":
            baris_status = status_wmi.split('\n')
            for status in baris_status:
                teks = status.strip()
                if teks != "Status" and teks != "OK" and teks != "":
                    return 1, 999 

        cmd_ps = 'powershell "Get-PhysicalDisk | Get-StorageReliabilityCounter | Select-Object -Property Wear, ReadErrorsTotal | ConvertTo-Json"'
        result_ps = subprocess.check_output(cmd_ps, shell=True).decode('utf-8')
        
        if not result_ps.strip(): return 100, 0
        
        data = json.loads(result_ps)
        if isinstance(data, list):
            max_wear = 0
            total_bad = 0
            for disk in data:
                wear = disk.get('Wear') or 0
                bad = disk.get('ReadErrorsTotal') or 0
                if wear > max_wear: max_wear = wear
                total_bad += bad
            return (100 - max_wear), total_bad
        else:
            keausan = data.get('Wear') or 0
            bad_sectors = data.get('ReadErrorsTotal') or 0
            return (100 - keausan), bad_sectors
    except Exception:
        return 100, 0
    
def lapor_ke_gateway():
    print(f" Memulai Sensus PC Lokal: {HOSTNAME_PC}")
    try:
        ip = ambil_ip_asli()
        cpu = get_real_cpu_name()
        total_disk = get_total_disk_size()
        partisi = get_all_partitions()
        ram = f"{math.ceil(psutil.virtual_memory().total / (1024**3))} GB"
        
        usage_c = psutil.disk_usage('C:\\')
        free_c = f"{round(usage_c.free / (1024**3), 2)} GB"
        
        persen_terpakai = usage_c.percent
        sisa_umur, bad_sectors = get_ssd_health_smart()
        
        is_bahaya = False
        if bad_sectors > 0:
            health_storage = f"🔴 KRITIS: Ada {bad_sectors} Bad Sector!"
            pesan_log = f"🚨 HARDWARE RUSAK: Ditemukan {bad_sectors} Bad Sector di SSD PC {HOSTNAME_PC}!"
            is_bahaya = True
        elif sisa_umur < 15:
            health_storage = f"🔴 KRITIS: Umur SSD sisa {sisa_umur}%"
            pesan_log = f"🚨 SSD SEKARAT: Umur SSD PC {HOSTNAME_PC} tinggal {sisa_umur}%. Segera ganti!"
            is_bahaya = True
        elif persen_terpakai > 90:
            health_storage = "🟡 Warning: Disk Penuh"
            pesan_log = f"🚨 STORAGE PENUH: Sisa disk C di PC {HOSTNAME_PC} tinggal {free_c}!"
            is_bahaya = True
        else:
            health_storage = f"✅ Sehat (Umur: {sisa_umur}%)"
            pesan_log = "Update Snipe-IT berhasil via Gateway. Hardware Sehat."

        print(f"💻 CPU: {cpu} | IP: {ip} | Status: {health_storage}")

        payload = {
            "hostname": HOSTNAME_PC,
            "ip": ip,
            "ram": ram,
            "free_c": free_c,
            "cpu": cpu,
            "total_disk": total_disk,
            "partisi": partisi,
            "health_storage": health_storage,
            "is_bahaya": is_bahaya,
            "pesan_log": pesan_log
        }
        
        headers = {
            "X-Secret-Token": SECRET_TOKEN,
            "Content-Type": "application/json"
        }
        
        print(f"📡 Mengirim data ke Gateway LAN ({GATEWAY_URL})...")
        res = requests.post(GATEWAY_URL, json=payload, headers=headers, timeout=10)
        
        if res.status_code == 200:
            print("✅ SUKSES! Data berhasil diterima oleh Gateway.")
        else:
            print(f"❌ GAGAL! Gateway menolak. Kode: {res.status_code}")

    except Exception as e:
        print(f"❌ Error Sistem Lokal: {str(e)}")

# ==========================================
# LISTENER BUAT MENERIMA PERINTAH DARI GATEWAY
# ==========================================
@app_agent.route('/do_sync', methods=['GET'])
def do_sync():
    token_masuk = request.headers.get('X-Secret-Token')
    if token_masuk != SECRET_TOKEN:
        return jsonify({"error": "Akses Ditolak"}), 403
    
    # Taruh fungsi lapor di thread supaya cepat ngerespon gateway tanpa nunggu kalkulasi HDD selesai
    threading.Thread(target=lapor_ke_gateway).start()
    
    return jsonify({"status": "Sensus mulai dijalankan!"}), 200

# ==========================================
# FUNGSI JADWAL OTOMATIS (ALARM)
# ==========================================
def jalankan_jadwal():
    """Fungsi gaib yang berjalan di background untuk mengecek jam"""
    # Set jadwal lapor harian
    schedule.every().day.at("12:00").do(lapor_ke_gateway)
    schedule.every().day.at("16:00").do(lapor_ke_gateway)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Cek jam setiap 1 menit

if __name__ == "__main__":
    # 1. Saat pertama kali PC/Agent nyala, lakukan laporan otomatis 1x
    lapor_ke_gateway()
    
    # 2. Nyalakan mandor jadwal di latar belakang
    thread_jadwal = threading.Thread(target=jalankan_jadwal, daemon=True)
    thread_jadwal.start()
    
    # 3. Nyalakan server listener di Port 5001 (CUKUP TULIS 1 KALI SAJA YANG VERSI AMAN INI)
    app_agent.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
