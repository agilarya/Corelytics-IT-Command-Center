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
