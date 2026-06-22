# 🌐 Corelytics IT Command Center

![Status](https://img.shields.io/badge/Status-Production_Ready-success)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-blue)
![Tech Stack](https://img.shields.io/badge/Tech-Python%20%7C%20Flask%20%7C%20PowerShell-orange)

An Enterprise-grade IT Asset Monitoring and Management System designed to bridge local PC endpoints across multiple VLANs with a centralized Snipe-IT database. 

## 🚀 Key Features
* **System-Level Agent:** Deploys silently as `NT AUTHORITY\SYSTEM` bypassing UAC prompts.
* **Smart Hardware Sensors:** Real-time extraction of S.M.A.R.T SSD health, CPU, RAM, and Storage capacity via WMI and `psutil`.
* **Dual-Trigger Monitoring:** Agent reports autonomously daily (via internal scheduler) OR instantly upon Force Sync from the dashboard.
* **Automated Deployment:** Bulletproof PowerShell & Batch scripts for auto-installing, hiding directories, and configuring Windows Firewall restrictions dynamically.
* **Glassmorphism UI:** Modern, fully responsive Web Dashboard for Analytics, Live Traffic Monitoring, and Asset Procurement.

## 🛠️ Tech Stack Used
Backend: Python 3, Flask, Requests.

Agent Sensors: WMI, PyWin32, Psutil.

Deployment: Windows PowerShell, Batch Scripts, Task Scheduler.

Frontend: HTML5, CSS3 (Glassmorphism), Bootstrap 5, Chart.js.

## ⚙️ How to Deploy (Quick Start)
Gateway Setup: Deploy gateway.py on your central server (e.g., Proxmox LXC/VM). Ensure it can route to your client VLANs.

Dashboard Setup: Run app.py in the Dashboard_UI folder.

Compile Agent: Run Compile_Agent.bat to package agent.py into a standalone executable.

Mass Deployment: Place the generated .exe alongside install.bat and pasang_agent.ps1 on a USB drive. Run install.bat as Administrator on target machines.

## 🔄 System Workflow & Pipeline

The entire ecosystem relies on a seamless, bidirectional communication pipeline between the endpoints, the gateway, and the asset management database:

1. **Prerequisite (Snipe-IT Setup):** The core foundation requires an active Snipe-IT instance with API access enabled.
2. **Asset Mapping:** The system strictly uses the PC's `Hostname` as the primary identifier to match physical machines with their corresponding asset records in Snipe-IT.
3. **Silent Deployment:** The Python-based Agent is installed on local client PCs using a combination of Batch and PowerShell scripts, running stealthily under `NT AUTHORITY\SYSTEM`.
4. **Data Relay via Gateway:** The Agent extracts local hardware metrics (IP, CPU, RAM, SSD S.M.A.R.T health) and sends the payload to the Proxmox-hosted Flask Gateway, avoiding direct client-to-database exposure.
5. **API Integration:** The Gateway processes the incoming payload and automatically updates the specific asset fields in the Snipe-IT database via REST API.
6. **Bidirectional Communication:** The Agent doesn't just send data; it actively listens on Port `5001`, maintaining a two-way communication channel with the Dashboard.
7. **On-Demand Synchronization:** IT Administrators can trigger a "Force Sync" directly from the Corelytics Web Dashboard. The Gateway shoots a command to the field Agent, forcing an immediate hardware scan and updating both the Snipe-IT database and the Dashboard UI in real-time.


## 🏗️ System Architecture

```mermaid
graph TD
    classDef client fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#fff,rx:10px,ry:10px;
    classDef server fill:#0f172a,stroke:#f97316,stroke-width:2px,color:#fff,rx:10px,ry:10px;
    classDef cloud fill:#0f172a,stroke:#10b981,stroke-width:2px,color:#fff,rx:10px,ry:10px;
    classDef db fill:#0f172a,stroke:#8b5cf6,stroke-width:2px,color:#fff,rx:10px,ry:10px;

    subgraph "Production Area (VLANs)"
        PC1["🖥️ PC Client\nAgent.exe (SYSTEM)\nPort 5001"]:::client
        PC2["🖥️ PC Client\nAgent.exe (SYSTEM)\nPort 5001"]:::client
    end

    subgraph "Server Farm"
        Gateway["⚙️ Corelytics Gateway\nFlask Relay"]:::server
        SnipeIT[("🗄️ Snipe-IT DB\nAsset Tracker")]:::db
    end

    subgraph "Command Center"
        Dashboard["📊 Web Dashboard\nMonitoring & Analytics"]:::cloud
    end

    PC1 -- "1. Daily Liveness / Hardware Log" --> Gateway
    PC2 -- "1. Daily Liveness / Hardware Log" --> Gateway
    Gateway -. "2. Force Sync Request" .-> PC1
    Gateway -- "3. API Asset Update" --> SnipeIT
    Gateway -- "4. Real-time Status" --> Dashboard
    Dashboard -- "5. Trigger Sync" --> Gateway
