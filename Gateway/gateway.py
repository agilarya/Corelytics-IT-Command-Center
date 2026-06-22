from flask import Flask, request, jsonify
import requests
from datetime import datetime
import os
import logging
from dotenv import load_dotenv

# Load konfigurasi dari .env
load_dotenv()

app = Flask(__name__)

# CONFIG LOGGING: Menulis ke Console DAN ke File 'gateway_log.txt'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("gateway_log.txt", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- KONFIGURASI UTAMA DARI .ENV ---
SNIPE_URL = os.getenv("SNIPE_URL")
API_TOKEN = os.getenv("API_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SECRET_TOKEN = os.getenv("SECRET_TOKEN")

# Murni pake skema dari .env (http://agent.trikasa.com)
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "").strip()

def lapor_ke_dashboard(hostname, status, pesan, ip, ram="N/A", cpu="N/A", free_c="N/A", health="N/A"):
    """Meneruskan laporan log dan spek ke Dashboard Cloud"""
    try:
        payload = {
            "hostname": hostname,
            "status": status,
            "pesan": pesan,
            "ip": ip,
            "ram": ram,
            "cpu": cpu,
            "free_c": free_c,
            "health_storage": health
        }
        url_target = f"{DASHBOARD_URL}/api/lapor_agent"
        logging.info(f"📡 [FORWARD] Mengirim data {hostname} ke Dashboard: {url_target}...")
        
        res = requests.post(url_target, json=payload, timeout=5)
        logging.info(f"✅ Berhasil meneruskan log {hostname} ke Dashboard. Respon HTTP: {res.status_code} | Body: {res.text}")
    except Exception as e:
        logging.error(f"❌ Gagal hubungi Dashboard: {str(e)}")

def kirim_telegram(hostname, ip, pesan):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return 
    try:
        url_tele = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        teks_tele = f"🚨 *GATEWAY ALERT (PC PRODUKSI)* 🚨\n\n💻 *PC:* {hostname}\n🌐 *IP:* {ip}\n📝 *Pesan:* {pesan}"
        payload_tele = {"chat_id": TELEGRAM_CHAT_ID, "text": teks_tele, "parse_mode": "Markdown"}
        requests.post(url_tele, json=payload_tele, timeout=5)
        logging.info("📲 Notifikasi bahaya dikirim ke Telegram.")
    except Exception as e:
        logging.error(f"❌ Gagal kirim Telegram: {e}")

# ==========================================
# ROUTE 1: MENERIMA DATA SENSUS DARI AGENT LOKAL
# ==========================================
@app.route('/api/relay', methods=['POST'])
def relay_data():
    try:
        token_masuk = request.headers.get('X-Secret-Token')
        if token_masuk != SECRET_TOKEN:
            logging.warning("🛑 BLOKIR: Ada akses ilegal tanpa token yang valid!")
            return jsonify({"status": "error", "message": "Akses Ditolak!"}), 403

        pack = request.json
        hostname = pack.get('hostname')
        ip = pack.get('ip')
        ram = pack.get('ram', 'N/A')
        free_c = pack.get('free_c', 'N/A')
        cpu = pack.get('cpu', 'N/A')
        total_disk = pack.get('total_disk', 'N/A')
        partisi = pack.get('partisi', 'N/A')
        health_storage = pack.get('health_storage', 'N/A')
        is_bahaya = pack.get('is_bahaya', False)
        pesan_log = pack.get('pesan_log', 'Tidak ada pesan')
        last_seen = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

        logging.info(f"📡 Menerima paket sensus sah dari: {hostname} ({ip})")

        headers = {"Accept": "application/json", "Content-Type": "application/json", "Authorization": f"Bearer {API_TOKEN}"}
        search_url = f"{SNIPE_URL}/api/v1/hardware?search={hostname}"
        res = requests.get(search_url, headers=headers, timeout=5)

        if res.status_code == 200 and res.json().get('total', 0) > 0:
            assets = res.json().get('rows', [])
            asset_id = None
            host_pc_asli = hostname.strip().upper()
            
            for asset in assets:
                nama_asset = str(asset.get('name', '')).strip().upper()
                custom_host = str(asset.get('custom_fields', {}).get('Hostname PC', {}).get('value', '')).strip().upper()
                if host_pc_asli == nama_asset or host_pc_asli == custom_host:
                    asset_id = asset.get('id')
                    break
            
            if asset_id:
                update_url = f"{SNIPE_URL}/api/v1/hardware/{asset_id}"
                payload = {
                    "_snipeit_ip_address_13": ip,
                    "_snipeit_ram_usage_14": ram,
                    "_snipeit_available_storage_c_12": free_c,
                    "_snipeit_processor_18": cpu,
                    "_snipeit_available_storage_d_19": total_disk,
                    "_snipeit_storage_20": partisi,
                    "_snipeit_last_seen_17": last_seen,
                    "_snipeit_health_storage_16": health_storage
                }
                update_req = requests.patch(update_url, headers=headers, json=payload, timeout=5)
                
                if update_req.status_code == 200:
                    respon_snipe = update_req.json()
                    if respon_snipe.get('status') == 'success':
                        logging.info(f"✅ Snipe-IT Terupdate untuk PC {hostname}!")
                        status_final = "ERROR" if is_bahaya else "SUKSES"
                        
                        lapor_ke_dashboard(hostname, status_final, pesan_log, ip, ram, cpu, free_c, health_storage)
                        if is_bahaya: kirim_telegram(hostname, ip, pesan_log)
                        return jsonify({"status": "success", "message": "Relay data aman bos!"}), 200
                    else:
                        pesan_tolak = respon_snipe.get('messages', 'Format data tidak sesuai')
                        pesan_err = f"Ditolak Snipe-IT: {pesan_tolak}"
                        logging.error(f"❌ ERROR SNIPE-IT: {pesan_err}")
                        lapor_ke_dashboard(hostname, "ERROR", pesan_err, ip, ram, cpu, free_c, health_storage)
                        return jsonify({"status": "error", "message": "Snipe-IT rejected data"}), 400
                else:
                    logging.error(f"❌ Patch Snipe-IT Gagal dengan kode HTTP: {update_req.status_code}")
                    lapor_ke_dashboard(hostname, "ERROR", f"Gateway gagal injek data (HTTP {update_req.status_code})", ip, ram, cpu, free_c, health_storage)
                    return jsonify({"status": "error", "message": "Snipe-IT patch failed"}), 500
            else:
                pesan_err = f"PC '{host_pc_asli}' terdeteksi di API, tapi tidak sinkron dengan nama di Snipe-IT."
                logging.error(f"❌ ERROR: {pesan_err}")
                lapor_ke_dashboard(hostname, "ERROR", pesan_err, ip, ram, cpu, free_c, health_storage)
                kirim_telegram(hostname, ip, pesan_err)
                return jsonify({"status": "error", "message": "Hostname mismatch"}), 400
        else:
            pesan_err = f"PC '{hostname}' belum didaftarkan di sistem Snipe-IT."
            logging.error(f"❌ ERROR: {pesan_err}")
            lapor_ke_dashboard(hostname, "ERROR", pesan_err, ip, ram, cpu, free_c, health_storage)
            return jsonify({"status": "error", "message": "Asset not found"}), 400

    except Exception as e:
        logging.error(f"❌ Error Sistem Gateway: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# ROUTE 2: MENERIMA PERINTAH SINKRONISASI DARI DASHBOARD
# ==========================================
@app.route('/api/force_sync', methods=['POST'])
def force_sync():
    data = request.json or {}
    token_masuk = data.get('secret')
    
    if token_masuk != SECRET_TOKEN:
        logging.warning("🛑 BLOKIR: Dashboard Secret Token salah!")
        return jsonify({"error": "Unauthorized"}), 403
        
    ip_target = data.get('ip')
    hostname_target = data.get('hostname')
    
    logging.info(f"🔄 Perintah Sinkronisasi Manual dari Dashboard untuk {hostname_target} ({ip_target})")
    
    try:
        agent_url = f"http://{ip_target}:5001/do_sync"
        req = requests.get(agent_url, headers={"X-Secret-Token": SECRET_TOKEN}, timeout=4)
        if req.status_code == 200:
            logging.info(f"✅ Sukses mendelegasikan perintah sinkronisasi ke PC {hostname_target}")
            return jsonify({"status": "success"}), 200
        else:
            logging.error(f"❌ Agent menolak perintah dengan kode: {req.status_code}")
            return jsonify({"error": "Agent menolak perintah"}), req.status_code
    except Exception as e:
        logging.error(f"❌ Gagal kontak Agent: {str(e)}")
        return jsonify({"error": f"Tidak dapat terhubung ke Agent: {str(e)}"}), 502

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
