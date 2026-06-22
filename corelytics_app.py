from flask import Flask, request, render_template, Response, redirect, url_for, session, jsonify
from functools import wraps
from datetime import datetime, timedelta, timezone
from io import StringIO
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
import threading
import json
import os
import uuid
import requests
import csv
import telebot
import google.generativeai as genai
import gspread

# ==========================================
# ⚙️ INISIALISASI & KONFIGURASI
# ==========================================
WIB = timezone(timedelta(hours=7))
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'Rahasiadong@321')

# Mekanisme Anti-Bruteforce Sederhana
failed_logins = {}

# 🔥 KUNCI KEAMANAN THREAD (Mencegah JSON Korup saat diakses bersamaan)
db_lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

DB_FILE = os.path.join(BASE_DIR, 'database_agent.json')
DB_PESANAN = os.path.join(BASE_DIR, 'database_pesanan.json')
FILE_KATALOG = os.path.join(BASE_DIR, 'katalog_snipe.json')
JSON_GOOGLE = os.path.join(BASE_DIR, 'kunci_rahasia.json')

# ==========================================
# 📁 FUNGSI DATABASE (JSON)
# ==========================================
def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError: 
            return {}
    return {}

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

# ==========================================
# 🤖 KONFIGURASI TELEGRAM BOT & GEMINI AI
# ==========================================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN_KANTOR', 'DUMMY_TOKEN_KANTOR').strip()
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

def kirim_notif_telegram(pesan):
    if TELEGRAM_CHAT_ID and "DUMMY" not in TELEGRAM_TOKEN:
        try:
            bot.send_message(TELEGRAM_CHAT_ID, pesan, parse_mode="HTML")
        except Exception as e:
            print(f"[!] Gagal mengirim Telegram: {e}")

# ==========================================
# 🔒 MIDDLEWARE & AUTENTIKASI
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip: ip = ip.split(',')[0].strip()

    if failed_logins.get(ip, 0) >= 5:
        return "Akses dari IP Anda diblokir sementara karena terlalu banyak percobaan gagal.", 403

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == os.getenv('ADMIN_USER') and password == os.getenv('ADMIN_PASS'):
            session['logged_in'] = True
            failed_logins.pop(ip, None)
            return redirect(url_for('halaman_utama'))
        else:
            failed_logins[ip] = failed_logins.get(ip, 0) + 1
            return render_template('login.html', error="Username atau Password salah!")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# 🧠 TELEGRAM COMMANDS & AI INSIGHT
# ==========================================
@bot.message_handler(commands=['cekpc'])
def command_cekpc(message):
    if str(message.chat.id) != str(TELEGRAM_CHAT_ID): return
    try:
        with db_lock:
            database_log = load_json(DB_FILE)
            
        total_pc = len(database_log)
        online, offline, error = 0, 0, 0
        rincian_kendala = []

        for pc, data in database_log.items():
            status = data.get('status', '')
            if status == 'SUKSES': online += 1
            elif status == 'OFFLINE': offline += 1
            elif status == 'ERROR':
                error += 1
                rincian_kendala.append(f"- `{pc}`: {data.get('pesan', 'Tanpa deskripsi')}")

        laporan = f"📊 *LAPORAN STATUS ASET PC KANTOR*\n\n"
        laporan += f"Total Perangkat: {total_pc}\n🟢 Responsif: {online}\n🔴 Luring (>24 Jam): {offline}\n⚠️ Kendala: {error}\n\n"
        if error > 0: laporan += "*Rincian Bermasalah:*\n" + "\n".join(rincian_kendala)

        bot.reply_to(message, laporan, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Gagal memuat data aset: {str(e)}")

@bot.message_handler(commands=['insight'])
def command_insight(message):
    if str(message.chat.id) != str(TELEGRAM_CHAT_ID): return
    msg_temp = bot.reply_to(message, "⏳ *AI sedang menganalisa status hardware kantor...*", parse_mode="Markdown")

    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key: 
            return bot.edit_message_text("❌ API Key Gemini belum dikonfigurasi.", chat_id=message.chat.id, message_id=msg_temp.message_id)

        with db_lock:
            database_log = load_json(DB_FILE)
            
        status_pc = {pc: {"status": d.get('status'), "health": d.get('health_storage')} for pc, d in database_log.items()}

        prompt = f"""
        Analisa data hardware kantor berikut dan berikan laporan ringkas (maksimal 3 paragraf):
        1. Ringkasan status PC dan Storage Health.
        2. Identifikasi anomali/error.
        3. Rekomendasi tindakan teknisi IT.
        Format menggunakan standar Markdown Telegram. Data: {status_pc}
        """

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        bot.edit_message_text(response.text, chat_id=message.chat.id, message_id=msg_temp.message_id, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text(f"⚠️ Error AI: {str(e)}", chat_id=message.chat.id, message_id=msg_temp.message_id)

@app.route(f'/api/telegram_webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Ditolak', 403

# ==========================================
# 📡 ROUTES: DASHBOARD & MONITORING
# ==========================================
@app.route('/')
@login_required
def halaman_utama():
    sekarang = datetime.now(WIB).replace(tzinfo=None)
    pc_health_list = []
    
    with db_lock:
        database_log = load_json(DB_FILE)
        perlu_disimpan = False

        for pc, data in list(database_log.items()):
            try:
                waktu_lapor = datetime.strptime(data['waktu'], "%d-%m-%Y %H:%M:%S")
                if (sekarang - waktu_lapor).total_seconds() / 3600 > 24 and data.get('status') != 'OFFLINE':
                    database_log[pc].update({'status': 'OFFLINE', 'pesan': 'PC mati > 24 jam.'})
                    perlu_disimpan = True
            except ValueError:
                pass

            health_str = str(data.get('health_storage', '100')).replace('%', '').strip()
            health_val = int(health_str) if health_str.isdigit() else 100
            pc_health_list.append({"pc": pc, "health": health_val})

        if perlu_disimpan:
            save_json(DB_FILE, database_log)

    pc_health_list.sort(key=lambda x: x["health"])
    top_5_worst = pc_health_list[:5]

    return render_template('dashboard.html',
                           logs=database_log,
                           total_pc=len(database_log),
                           total_sukses=sum(1 for d in database_log.values() if d['status'] == 'SUKSES'),
                           total_error=sum(1 for d in database_log.values() if d['status'] == 'ERROR'),
                           total_offline=sum(1 for d in database_log.values() if d['status'] == 'OFFLINE'),
                           chart_labels=[item["pc"] for item in top_5_worst],
                           chart_data=[item["health"] for item in top_5_worst])

@app.route('/pc-monitor')
@login_required
def pc_monitor():
    with db_lock:
        logs = load_json(DB_FILE)

    total_pc = len(logs)
    total_sukses = sum(1 for d in logs.values() if d.get('status') == 'SUKSES')
    total_offline = sum(1 for d in logs.values() if d.get('status') == 'OFFLINE')
    total_error = total_pc - (total_sukses + total_offline)

    return render_template('pc_monitor.html', 
                           logs=logs, 
                           total_pc=total_pc, 
                           total_sukses=total_sukses, 
                           total_error=total_error, 
                           total_offline=total_offline)

@app.route('/api/hapus/<hostname>', methods=['DELETE'])
@login_required
def hapus_data_pc(hostname):
    with db_lock:
        database_log = load_json(DB_FILE)
        if hostname in database_log:
            del database_log[hostname]
            save_json(DB_FILE, database_log)
            return jsonify({"status": "sukses", "pesan": "Data berhasil dihapus"}), 200
            
    return jsonify({"status": "error", "pesan": "PC tidak ditemukan"}), 404
                           
@app.route('/api/lapor_agent', methods=['POST'])
def terima_laporan():
    data = request.json or {}
    hostname = data.get('hostname', 'Unknown')
    
    with db_lock:
        database_log = load_json(DB_FILE)
        data_lama = database_log.get(hostname, {})

        database_log[hostname] = {
            'waktu': datetime.now(WIB).strftime("%d-%m-%Y %H:%M:%S"),
            'status': data.get('status', 'ERROR'),
            'ip': data.get('ip', data_lama.get('ip', 'Tidak ada IP')),
            'pesan': data.get('pesan', 'Tidak ada pesan'),
            'ram': data.get('ram', data_lama.get('ram', 'N/A')),
            'cpu': data.get('cpu', data_lama.get('cpu', 'N/A')),
            'free_c': data.get('free_c', data_lama.get('free_c', 'N/A')),
            'health_storage': data.get('health_storage', data_lama.get('health_storage', 'N/A'))
        }
        save_json(DB_FILE, database_log)
        
    return {"status": "diterima"}, 200

# ==========================================
# 🔄 ROUTES: SINKRONISASI MANUAL SERVER 2 & SNIPE-IT
# ==========================================

def update_asset_snipe_it(hostname, data_pc):
    """
    Mencari Asset berdasarkan Name/Hostname di Snipe-IT
    lalu mengupdate notes atau custom fields-nya.
    """
    URL_SNIPE_IT = "https://go.trikasa.com/api/v1"
    TOKEN = os.getenv('SNIPE_IT_TOKEN')
    
    if not TOKEN:
        return False

    headers = {
        "Authorization": f"Bearer {TOKEN}", 
        "Accept": "application/json", 
        "Content-Type": "application/json"
    }
    
    try:
        search_url = f"{URL_SNIPE_IT}/hardware?search={hostname}"
        res_search = requests.get(search_url, headers=headers).json()
        
        if res_search.get('total', 0) > 0:
            asset_id = res_search['rows'][0]['id']
            update_url = f"{URL_SNIPE_IT}/hardware/{asset_id}"
            
            payload = {
                "notes": f"Update Otomatis via API: CPU: {data_pc.get('cpu')}, RAM: {data_pc.get('ram')}, Sisa Disk C: {data_pc.get('free_c')}, SSD Health: {data_pc.get('health_storage')}"
            }
            
            res_update = requests.put(update_url, json=payload, headers=headers)
            return res_update.status_code == 200
        else:
            return False
    except Exception as e:
        print(f"Error update asset Snipe-IT: {e}")
        return False

@app.route('/api/sync_single_pc/<hostname>', methods=['GET'])
@login_required
def sync_single_pc(hostname):
    SECRET_TOKEN = os.getenv('SECRET_TOKEN', 'IT_Command_Center_2026_TopSecret')
    
    # 🔥 DISET KE HTTP (TANPA S) SESUAI KONDISI LAPANGAN
    GATEWAY_URL = "https://api-gateway.trikasa.com/api/force_sync"

    with db_lock:
        database_log = load_json(DB_FILE)

    if hostname not in database_log:
        return jsonify({"status": "error", "pesan": f"Hostname '{hostname}' tidak terdaftar di Dashboard."}), 404

    ip_pc = database_log[hostname].get('ip')
    if not ip_pc or ip_pc == 'Tidak ada IP':
        return jsonify({"status": "error", "pesan": f"IP Address PC '{hostname}' tidak valid."}), 400

    payload = {
        "secret": SECRET_TOKEN,
        "hostname": hostname,
        "ip": ip_pc
    }

    try:
        response = requests.post(GATEWAY_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            return jsonify({
                "status": "sukses", 
                "pesan": f"Perintah sinkronisasi berhasil dikirim ke PC {hostname} ({ip_pc})!"
            }), 200
        else:
            try: pesan_err = response.json().get('error', 'Ditolak Gateway')
            except: pesan_err = f"HTTP Error {response.status_code}"
            return jsonify({"status": "error", "pesan": f"Gateway gagal: {pesan_err}"}), response.status_code

    except Exception as e:
        return jsonify({"status": "error", "pesan": f"Gagal terhubung ke api-gateway: {str(e)}"}), 500


@app.route('/api/export_csv')
@login_required
def export_csv():
    with db_lock:
        database_log = load_json(DB_FILE)
        
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Hostname', 'IP Address', 'Status', 'Waktu Lapor', 'Pesan / Detail', 'CPU', 'RAM', 'Sisa Disk C', 'Kesehatan SSD'])
    for pc, data in database_log.items():
        cw.writerow([pc, data.get('ip', ''), data.get('status', ''), data.get('waktu', ''), data.get('pesan', ''), data.get('cpu', ''), data.get('ram', ''), data.get('free_c', ''), data.get('health_storage', '')])
    
    output = si.getvalue()
    nama_file = f"Laporan_Aset_IT_{datetime.now(WIB).strftime('%d%m%Y')}.csv"
    return Response(output, mimetype='text/csv', headers={"Content-Disposition": f"attachment;filename={nama_file}"})

# ==========================================
# 📦 ROUTES: PROCUREMENT & SNIPE-IT
# ==========================================
def sinkron_ke_gsheets(data_pesanan):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_GOOGLE, scope)
        client = gspread.authorize(creds)
        sheet = client.open("List Barang").worksheet("Permintaan TJL")

        nomor_urut = max(len(sheet.col_values(2)) - 2, 1)
        row_baru = [nomor_urut, data_pesanan['nama_barang'], "", 0, data_pesanan['qty'], "Unit/Pcs", data_pesanan['kebutuhan'], data_pesanan['tgl_pengajuan'], ""]
        sheet.append_row(row_baru)
        return True
    except Exception as e: 
        print(f"Error GSheets: {e}")
        return False

def sinkron_ke_snipe_it_procurement(data_pesanan):
    URL_SNIPE_IT = "https://go.trikasa.com/api/v1"
    TOKEN = os.getenv('SNIPE_IT_TOKEN')
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json", "Content-Type": "application/json"}
    
    with db_lock:
        katalog_snipe = load_json(FILE_KATALOG)
        
    nama_barang = data_pesanan['nama_barang']
    if nama_barang not in katalog_snipe: return False
    
    url_item = f"{URL_SNIPE_IT}/{katalog_snipe[nama_barang]['kategori']}/{katalog_snipe[nama_barang]['id']}"

    try:
        res_get = requests.get(url_item, headers=headers).json()
        requests.put(url_item, json={"qty": res_get.get('qty', 0) + data_pesanan['qty']}, headers=headers)
        return True
    except Exception as e: 
        print(f"Error Snipe-IT: {e}")
        return False

@app.route('/admin-procurement-rahasia', methods=['GET', 'POST'])
@login_required
def halaman_procurement():
    with db_lock:
        database_pesanan = load_json(DB_PESANAN)

    if request.method == 'POST':
        id_pesanan = str(uuid.uuid4())[:6].upper()
        database_pesanan[id_pesanan] = {
            'nama_barang': request.form.get('nama_barang'),
            'kategori': request.form.get('kategori'),
            'qty': int(request.form.get('qty')),
            'kebutuhan': request.form.get('kebutuhan'),
            'tgl_pengajuan': datetime.now(WIB).strftime("%d-%m-%Y"),
            'tgl_datang': 'Belum Datang',
            'status': 'Menunggu'
        }
        with db_lock:
            save_json(DB_PESANAN, database_pesanan)
        
        sinkron_ke_gsheets(database_pesanan[id_pesanan])
        return redirect(url_for('halaman_procurement'))

    return render_template('procurement.html', pesanan=database_pesanan)

@app.route('/api/terima_barang/<id_pesanan>', methods=['POST'])
@login_required
def terima_barang(id_pesanan):
    with db_lock:
        database_pesanan = load_json(DB_PESANAN)
        
    if id_pesanan in database_pesanan:
        status_sync = sinkron_ke_snipe_it_procurement(database_pesanan[id_pesanan])
        database_pesanan[id_pesanan].update({
            'status': 'Selesai',
            'tgl_datang': f"{datetime.now(WIB).strftime('%d-%m-%Y')} (Sync: {'OK' if status_sync else 'Gagal'})"
        })
        with db_lock:
            save_json(DB_PESANAN, database_pesanan)
            
        return {"status": "sukses", "pesan": "Barang diterima!"}, 200
        
    return {"status": "error", "pesan": "ID Pesanan tidak ditemukan"}, 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)