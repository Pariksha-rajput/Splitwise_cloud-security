# Fairsplit — Project Architecture

**Student:** Pariksha Rajput
**Course:** CS581 — Cloud Security
**Platform:** Microsoft Azure
**Live URL:** https://20.100.154.95.nip.io

---

## Table of Contents

1. [High-Level Architecture Overview](#1-high-level-architecture-overview)
2. [Azure Infrastructure Architecture](#2-azure-infrastructure-architecture)
3. [Network Architecture](#3-network-architecture)
4. [AKS Cluster Architecture](#4-aks-cluster-architecture)
5. [Application Architecture](#5-application-architecture)
6. [Request Flow Architecture](#6-request-flow-architecture)
7. [Container and Image Architecture](#7-container-and-image-architecture)
8. [Security Architecture](#8-security-architecture)
9. [Monitoring and Logging Architecture](#9-monitoring-and-logging-architecture)
10. [Secret Management Architecture](#10-secret-management-architecture)
11. [CI/CD and Deployment Architecture](#11-cicd-and-deployment-architecture)
12. [Component Inventory](#12-component-inventory)

---

## 1. High-Level Architecture Overview

```
+-----------------------------------------------------------------------------------+
|                              MICROSOFT AZURE                                      |
|                         Resource Group: secure-aks-rg                             |
|                                                                                   |
|   Developer                                                                       |
|   Machine        ACR                    AKS Cluster                               |
|   +-------+    +-------+    +----------------------------------+                  |
|   | code  |--->| image |    |  VNet: 10.0.0.0/16               |                  |
|   | build |    | push  |    |                                  |                  |
|   +-------+    +-------+    |  Frontend Subnet  Backend Subnet |                  |
|      |           |          |  10.0.1.0/24      10.0.2.0/24   |                  |
|      |           |          |  +-----------+    +-----------+  |                  |
|      |           +--------->|  | NGINX Pod |    | Flask Pod |  |                  |
|      |    Terraform         |  | (public)  |    | (private) |  |                  |
|      +------------------+   |  +-----------+    +-----------+  |                  |
|                         |   +----------------------------------+                  |
|                         v                                                         |
|                    Azure Resources                                                |
|              (VNet, NSG, AKS, ACR, KV,                                           |
|               Log Analytics, Defender,                                            |
|               Monitor Alerts)                                                     |
|                                                                                   |
|   Internet User                                                                   |
|   +--------+  HTTPS   Azure LB    NGINX Ingress   Frontend   Backend             |
|   |Browser |--------->20.100. --->Controller  --->Pod    --->Pod                  |
|   +--------+          154.95                                                      |
+-----------------------------------------------------------------------------------+
```

---

## 2. Azure Infrastructure Architecture

```
Azure Subscription
└── Resource Group: secure-aks-rg  (region: eastus / configured region)
    │
    ├── Virtual Network: 10.0.0.0/16
    │   ├── Subnet: frontend-subnet  (10.0.1.0/24)
    │   │   └── NSG: frontend-nsg
    │   │       ├── Allow TCP 80  from Internet (HTTP)
    │   │       ├── Allow TCP 443 from Internet (HTTPS)
    │   │       └── Deny all other inbound
    │   │
    │   └── Subnet: backend-subnet  (10.0.2.0/24)
    │       └── NSG: backend-nsg
    │           ├── Allow TCP 5000 from VNet (10.0.0.0/16) only
    │           └── Deny all internet inbound
    │
    ├── AKS Cluster: secure-aks-cluster
    │   ├── Identity: SystemAssigned Managed Identity
    │   ├── RBAC: Enabled
    │   ├── Network plugin: Azure CNI
    │   ├── Load balancer SKU: Standard
    │   ├── OMS Agent (log forwarding to Log Analytics)
    │   ├── Microsoft Defender (runtime threat detection)
    │   ├── Node Pool: frontendpool → frontend-subnet
    │   └── Node Pool: backendpool  → backend-subnet
    │
    ├── Azure Container Registry: fairsplitacrq0w0x3
    │   ├── SKU: Standard (built-in vulnerability scanning)
    │   └── Role: AcrPull → AKS kubelet identity (no passwords)
    │
    ├── Azure Key Vault: fairsplit-kv-q0w0x3
    │   └── Stores: application secrets (production reference)
    │
    ├── Log Analytics Workspace: aks-log-workspace
    │   ├── Receives: pod stdout logs via OMS agent
    │   ├── Receives: kube-audit logs via Diagnostic Settings
    │   └── Receives: Defender alerts
    │
    ├── Microsoft Defender for Containers
    │   └── Monitors: runtime container behavior, kubectl exec
    │
    └── Azure Monitor
        ├── Alert Rule: brute-force-detection   (PT5M, severity 0)
        ├── Alert Rule: scanning-detection      (PT1M, severity 0)
        ├── Alert Rule: idor-attempt-detection  (PT5M, severity 0)
        ├── Alert Rule: log-tamper-detection    (PT5M, severity 0)
        └── Action Group: fairsplit-security-alerts
            └── Email: pariksha.rajput2912@gmail.com
```

---

## 3. Network Architecture

```
                          INTERNET
                              |
                        HTTPS :443
                        HTTP  :80
                              |
                    +---------v----------+
                    |  Azure Standard    |
                    |  Load Balancer     |
                    |  IP: 20.100.154.95 |
                    +---------+----------+
                              |
               +--------------v--------------+
               |      frontend-subnet         |
               |      10.0.1.0/24            |
               |                             |
               |  NSG: frontend-nsg          |
               |  ALLOW: TCP 80, 443         |
               |  DENY:  all other inbound   |
               |                             |
               |  +----------------------+   |
               |  | NGINX Ingress        |   |
               |  | Controller Pod       |   |
               |  | (ingress-nginx ns)   |   |
               |  | - TLS termination    |   |
               |  | - HTTP->HTTPS redir  |   |
               |  | - Host routing       |   |
               |  +----------+-----------+   |
               |             |               |
               |  +----------v-----------+   |
               |  | frontend Pod         |   |
               |  | nginx:alpine         |   |
               |  | port: 80             |   |
               |  | proxy_pass :5000     |   |
               |  +----------+-----------+   |
               +-------------|--------------+
                             |
               +--------------v--------------+
               |      backend-subnet          |
               |      10.0.2.0/24            |
               |                             |
               |  NSG: backend-nsg           |
               |  ALLOW: TCP 5000 from VNet  |
               |  DENY:  all internet        |
               |                             |
               |  +----------------------+   |
               |  | backend Pod          |   |
               |  | Flask + Gunicorn     |   |
               |  | port: 5000           |   |
               |  | 2 workers            |   |
               |  +----------+-----------+   |
               |             |               |
               |  +----------v-----------+   |
               |  | Azure Disk PVC       |   |
               |  | /app/instance/       |   |
               |  | fairsplit.db (1Gi)   |   |
               |  +----------------------+   |
               +-----------------------------+
```

---

## 4. AKS Cluster Architecture

```
AKS Cluster: secure-aks-cluster
│
├── Namespace: ingress-nginx
│   └── ingress-nginx-controller (Deployment)
│       ├── Image: ingress-nginx/controller
│       ├── Node: frontendpool (nodeSelector: agentpool=frontendpool)
│       ├── Service: LoadBalancer (IP: 20.100.154.95)
│       └── Reads: Ingress resources in all namespaces
│
├── Namespace: cert-manager
│   ├── cert-manager (Deployment) — manages Certificate objects
│   ├── cert-manager-cainjector   — injects CA bundles
│   ├── cert-manager-webhook      — validates cert resources
│   └── ClusterIssuer: letsencrypt-prod
│       └── ACME HTTP-01 via Let's Encrypt
│
└── Namespace: fairsplit
    │
    ├── ServiceAccount: backend-sa
    │   └── Role: backend-role (read Secrets only)
    │
    ├── Secret: app-secret      (SECRET_KEY)
    ├── Secret: smtp-secret     (SMTP_HOST, SMTP_USER, SMTP_PASS)
    ├── Secret: fairsplit-tls   (TLS cert + key from cert-manager)
    │
    ├── PersistentVolumeClaim: fairsplit-db-pvc
    │   ├── Size: 1Gi
    │   ├── StorageClass: managed-csi (Azure Disk)
    │   └── AccessMode: ReadWriteOnce
    │
    ├── ConfigMap: nginx-config (NGINX reverse proxy config)
    │
    ├── NetworkPolicy: backend-policy
    │   └── Ingress: allow port 5000 from pods with app=frontend only
    │
    ├── Deployment: frontend
    │   ├── Image: nginx:alpine
    │   ├── Replicas: 1
    │   ├── Node: frontendpool
    │   └── Mounts: nginx-config ConfigMap
    │
    ├── Deployment: backend
    │   ├── Image: fairsplitacrq0w0x3.azurecr.io/fairsplit:latest
    │   ├── Replicas: 1
    │   ├── Node: backendpool
    │   ├── ServiceAccount: backend-sa
    │   ├── securityContext:
    │   │   ├── runAsNonRoot: true
    │   │   ├── runAsUser: 1000
    │   │   ├── allowPrivilegeEscalation: false
    │   │   └── fsGroup: 1000
    │   ├── Env (from Secrets): SECRET_KEY, DATABASE_URL, SMTP_*
    │   └── Mounts: fairsplit-db-pvc at /app/instance/
    │
    ├── Service: frontend  (ClusterIP, port 80)
    ├── Service: backend   (ClusterIP, port 5000)
    │
    └── Ingress: fairsplit-ingress
        ├── Host: 20.100.154.95.nip.io
        ├── TLS: fairsplit-tls (Let's Encrypt)
        ├── ssl-redirect: true
        └── Backend: frontend:80
```

---

## 5. Application Architecture

```
+------------------------------------------------------------------+
|                     FAIRSPLIT APPLICATION                        |
|                                                                  |
|  Frontend Pod (nginx:alpine)                                     |
|  +------------------------------------------------------------+  |
|  |  NGINX Reverse Proxy                                       |  |
|  |  listen 80                                                 |  |
|  |  proxy_pass http://backend:5000                            |  |
|  |  Sets: X-Real-IP, X-Forwarded-For, X-Forwarded-Proto      |  |
|  +------------------------------------------------------------+  |
|                              |                                   |
|                              v                                   |
|  Backend Pod (python:3.11-slim)                                  |
|  +------------------------------------------------------------+  |
|  |  Gunicorn WSGI Server (2 workers, port 5000)               |  |
|  |  +------------------------------------------------------+  |  |
|  |  |  Flask Application (app.py)                          |  |  |
|  |  |                                                      |  |  |
|  |  |  Routes:                                             |  |  |
|  |  |  GET  /              Landing page                    |  |  |
|  |  |  POST /signup        User registration               |  |  |
|  |  |  POST /login         Authentication                  |  |  |
|  |  |  GET  /dashboard     Financial snapshot              |  |  |
|  |  |  GET  /expenses      Expense list                    |  |  |
|  |  |  POST /expenses/add  Create expense                  |  |  |
|  |  |  POST /expenses/<id>/settle  Settle expense          |  |  |
|  |  |  GET  /balances      Debt overview                   |  |  |
|  |  |  GET  /wallet        Wallet management               |  |  |
|  |  |  GET  /payments      Payment history                 |  |  |
|  |  |  GET  /notifications Activity feed                   |  |  |
|  |  |  GET/DELETE /system/logs  Protected audit endpoint   |  |  |
|  |  |                                                      |  |  |
|  |  |  Modules:                                            |  |  |
|  |  |  security.py  — threat detection middleware          |  |  |
|  |  |  Flask-SQLAlchemy — ORM                              |  |  |
|  |  |  Flask-Bcrypt     — password hashing                 |  |  |
|  |  |  smtplib          — email notifications              |  |  |
|  |  +------------------------------------------------------+  |  |
|  +------------------------------------------------------------+  |
|                              |                                   |
|                              v                                   |
|  Azure Disk PVC (/app/instance/fairsplit.db)                     |
|  +------------------------------------------------------------+  |
|  |  SQLite Database                                           |  |
|  |  Tables: user, expense, expense_split, expense_members,   |  |
|  |          expense_settled, payment, wallet,                 |  |
|  |          notification, notification_settings              |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
```

---

## 6. Request Flow Architecture

### HTTPS Request Flow

```
Step 1: User types https://20.100.154.95.nip.io in browser
        |
        v
Step 2: nip.io DNS resolves 20.100.154.95.nip.io --> 20.100.154.95
        |
        v
Step 3: Azure Standard Load Balancer (20.100.154.95:443)
        forwards to NGINX Ingress Controller pod
        |
        v
Step 4: NGINX Ingress Controller
        a. Terminates TLS (decrypts using fairsplit-tls Secret)
        b. Checks Host header: 20.100.154.95.nip.io -- matches rule
        c. Checks path: / -- matches Prefix rule
        d. Forwards decrypted HTTP to frontend Service:80
        |
        v
Step 5: frontend Service (ClusterIP)
        Kubernetes DNS load balances to frontend pod
        |
        v
Step 6: frontend Pod (nginx:alpine)
        NGINX receives request on port 80
        proxy_pass http://backend:5000
        Adds X-Real-IP, X-Forwarded-For headers
        |
        v
Step 7: backend Service (ClusterIP)
        Kubernetes DNS routes to backend pod
        |
        v
Step 8: backend Pod (Gunicorn + Flask)
        a. security.py checks: is IP blocked? (brute force check)
        b. Flask route handler processes request
        c. SQLAlchemy reads/writes fairsplit.db on Azure Disk
        d. Returns HTML response
        |
        v
Step 9: Response travels back through chain
        Flask --> Gunicorn --> backend Service --> frontend Pod
        --> frontend Service --> NGINX Ingress (re-encrypts TLS)
        --> Azure LB --> Browser
```

### HTTP to HTTPS Redirect Flow

```
Browser --> http://20.100.154.95.nip.io (port 80)
        |
        v
Azure LB --> NGINX Ingress Controller (port 80)
        |
        | ssl-redirect: "true" annotation
        v
301 Moved Permanently --> https://20.100.154.95.nip.io
        |
        v
Browser follows redirect --> full HTTPS flow above
```

---

## 7. Container and Image Architecture

### Image Build and Push Pipeline

```
Developer Machine
+------------------+
| Dockerfile       |
| COPY Spiltwise/  |
| app.py           |       docker build
| security.py  +----------+----------->  Local Image
| templates/   |          |               fairsplit:latest
+------------------+       |                    |
                           |                    | docker push
                           v                    v
                    az acr login          Azure Container
                    (Azure CLI)           Registry (ACR)
                    OAuth token           fairsplitacrq0w0x3
                    no password           .azurecr.io/
                                         fairsplit:latest
                                              |
                                              | Managed Identity
                                              | (AcrPull role)
                                              v
                                         AKS Node (kubelet)
                                         containerd pulls image
                                              |
                                              v
                                         Container running
                                         Flask/Gunicorn :5000
```

### Docker Image Layers

```
python:3.11-slim (base)
    |
    + COPY requirements.txt
    + RUN pip install (Flask, Gunicorn, Bcrypt, SQLAlchemy...)
    |
    + COPY app.py security.py
    + COPY templates/
    |
    + RUN useradd -m appuser (UID 1000)
    + USER appuser
    |
    + CMD gunicorn --bind 0.0.0.0:5000 --workers 2 app:app

Total size: ~62 MB
```

### Images in Use

| Image | Source | Used By | Size |
|---|---|---|---|
| `fairsplitacrq0w0x3.azurecr.io/fairsplit:latest` | ACR (custom built) | backend pod | ~62 MB |
| `nginx:alpine` | Docker Hub | frontend pod | ~40 MB |
| `ingress-nginx/controller` | registry.k8s.io | ingress-nginx pod | ~290 MB |
| `cert-manager-controller` | quay.io/jetstack | cert-manager pod | ~60 MB |
| `cert-manager-cainjector` | quay.io/jetstack | cert-manager pod | ~55 MB |
| `cert-manager-webhook` | quay.io/jetstack | cert-manager pod | ~45 MB |

---

## 8. Security Architecture

### Defense in Depth — 7 Layers

```
+------------------------------------------------------------------------+
|  LAYER 1: Azure NSG                                                    |
|  frontend-nsg: Allow TCP 80,443 from Internet only                     |
|  backend-nsg:  Allow TCP 5000 from VNet (10.0.0.0/16) only            |
+------------------------------------------------------------------------+
                              |
+------------------------------------------------------------------------+
|  LAYER 2: Kubernetes NetworkPolicy                                     |
|  backend: accept port 5000 ONLY from pods labeled app=frontend         |
|  frontend: accept port 80 ONLY from ingress-nginx namespace            |
+------------------------------------------------------------------------+
                              |
+------------------------------------------------------------------------+
|  LAYER 3: NGINX Ingress Controller                                     |
|  TLS termination (Let's Encrypt certificate)                           |
|  HTTP --> HTTPS redirect (301)                                         |
|  Host-based routing (unknown hosts dropped)                            |
+------------------------------------------------------------------------+
                              |
+------------------------------------------------------------------------+
|  LAYER 4: Frontend NGINX (reverse proxy)                               |
|  Never exposes backend port externally                                 |
|  Forwards X-Real-IP so Flask gets real client IP                       |
+------------------------------------------------------------------------+
                              |
+------------------------------------------------------------------------+
|  LAYER 5: Flask Authentication                                         |
|  @login_required decorator on all non-public routes                   |
|  Bcrypt password hashing (cost factor 12)                              |
|  Signed session cookie (Flask SECRET_KEY)                              |
+------------------------------------------------------------------------+
                              |
+------------------------------------------------------------------------+
|  LAYER 6: security.py Middleware                                       |
|  Brute force:   3 failures/5min  --> IP blocked + CRITICAL log         |
|  IDOR:          expense ownership verified before settlement            |
|  Scanning:      10 unauth hits/1min --> CRITICAL log                   |
|  Log tampering: DELETE /system/logs --> 403 + CRITICAL log             |
+------------------------------------------------------------------------+
                              |
+------------------------------------------------------------------------+
|  LAYER 7: Azure Monitor + Microsoft Defender                           |
|  4 Scheduled Query Alert rules --> email notifications                 |
|  Defender for Containers: runtime threat detection                     |
|  kube-audit: records all kubectl operations permanently                |
+------------------------------------------------------------------------+
```

### Security Events and Responses

| Event | Trigger | Severity | App Response | Azure Response |
|---|---|---|---|---|
| `FAILED_LOGIN` | Each wrong password | WARNING | Logged | - |
| `BRUTE_FORCE_DETECTED` | 3 failures in 5 min | CRITICAL | IP blocked | Email alert |
| `UNAUTHORIZED_ACCESS` | Unauthenticated route hit | WARNING | Redirect to login | - |
| `SCANNING_DETECTED` | 10 hits in 1 min | CRITICAL | Logged | Email alert |
| `IDOR_ATTEMPT_DETECTED` | Settling another user's expense | CRITICAL | 403 Forbidden | Email alert |
| `LOG_TAMPER_ATTEMPT` | DELETE/PATCH /system/logs | CRITICAL | 403 Forbidden | Email alert |

### Container Security Configuration

```yaml
securityContext (pod level):
  fsGroup: 1000              # Azure Disk mounted with correct ownership

securityContext (container level):
  runAsNonRoot: true         # Cannot run as root
  runAsUser: 1000            # Explicit UID (appuser)
  allowPrivilegeEscalation: false  # Cannot gain root even via setuid
```

### RBAC Architecture

```
backend-sa (ServiceAccount)
    |
    +-- backend-role (Role)
    |   rules:
    |   - apiGroups: [""]
    |     resources: ["secrets"]
    |     verbs: ["get"]          # read-only, one namespace only
    |
    +-- backend-binding (RoleBinding)
        Binds backend-sa to backend-role in fairsplit namespace only

Result: A compromised backend pod CANNOT
  - list/delete other pods
  - create deployments
  - access other namespaces
  - escalate to cluster-admin
```

---

## 9. Monitoring and Logging Architecture

```
+------------------------------------------------------------------+
|                    MONITORING PIPELINE                           |
|                                                                  |
|  Flask App (security.py)                                         |
|  log_security_event() --> JSON to stdout                         |
|       |                                                          |
|       v                                                          |
|  Gunicorn stdout                                                 |
|       |                                                          |
|       v                                                          |
|  Kubernetes logging driver                                       |
|  (captures container stdout)                                     |
|       |                                                          |
|       v                                                          |
|  OMS Agent (DaemonSet on every node)                            |
|  ships logs every 60 seconds                                     |
|       |                                                          |
|       v                                                          |
|  Log Analytics Workspace: aks-log-workspace                      |
|  Table: ContainerLog                                             |
|       |                                                          |
|       v                                                          |
|  Azure Monitor Scheduled Query Rules                             |
|  (queries ContainerLog every 1-5 minutes)                        |
|       |                                                          |
|       +--> brute-force-detection   BRUTE_FORCE_DETECTED          |
|       +--> scanning-detection      SCANNING_DETECTED             |
|       +--> idor-attempt-detection  IDOR_ATTEMPT_DETECTED         |
|       +--> log-tamper-detection    LOG_TAMPER_ATTEMPT            |
|       |                                                          |
|       v                                                          |
|  Action Group: fairsplit-security-alerts                         |
|  Email --> pariksha.rajput2912@gmail.com                         |
+------------------------------------------------------------------+

Parallel pipeline (infrastructure level):

  kube-audit log (every kubectl operation)
       |
       v
  AKS Diagnostic Settings
       |
       v
  Log Analytics (AzureDiagnostics table)
       |
       v
  Microsoft Defender for Containers
  (alerts on: kubectl exec, privilege escalation, suspicious activity)
```

### Log Analytics Queries for Each Security Event

```kusto
-- Brute Force
ContainerLog | where LogEntry contains "BRUTE_FORCE_DETECTED"
| project TimeGenerated, LogEntry | order by TimeGenerated desc

-- IDOR
ContainerLog | where LogEntry contains "IDOR_ATTEMPT_DETECTED"
| project TimeGenerated, LogEntry | order by TimeGenerated desc

-- Log Tampering
ContainerLog | where LogEntry contains "LOG_TAMPER_ATTEMPT"
| project TimeGenerated, LogEntry | order by TimeGenerated desc

-- Route Scanning
ContainerLog | where LogEntry contains "SCANNING_DETECTED"
| project TimeGenerated, LogEntry | order by TimeGenerated desc

-- All security events
ContainerLog
| where LogEntry contains "BRUTE_FORCE" or LogEntry contains "IDOR"
  or LogEntry contains "LOG_TAMPER" or LogEntry contains "SCANNING"
| project TimeGenerated, LogEntry | order by TimeGenerated desc
```

---

## 10. Secret Management Architecture

```
+------------------------------------------------------------------+
|                  SECRET MANAGEMENT FLOW                          |
|                                                                  |
|  Source of truth: Kubernetes Secrets (base64-encoded)            |
|                                                                  |
|  Secret: app-secret                                              |
|  +-------------------------------+                               |
|  | secret-key: <base64>          |                               |
|  +-------------------------------+                               |
|         |                                                        |
|         v (secretKeyRef in deployment spec)                      |
|  Container env var: SECRET_KEY=fairsplit-super-secret-key        |
|                                                                  |
|  Secret: smtp-secret                                             |
|  +-------------------------------+                               |
|  | smtp-host: <base64>           |                               |
|  | smtp-user: <base64>           |                               |
|  | smtp-pass: <base64>           |                               |
|  +-------------------------------+                               |
|         |                                                        |
|         v (secretKeyRef in deployment spec)                      |
|  Container env vars: SMTP_HOST, SMTP_USER, SMTP_PASS             |
|                                                                  |
|  Secrets NEVER in:                                               |
|  - Source code                                                   |
|  - Dockerfile                                                    |
|  - Git repository (.gitignore covers .env)                       |
|  - Docker image layers                                           |
|  - Log output                                                    |
|                                                                  |
|  ACR Authentication (zero-credential model):                     |
|  AKS Managed Identity --> Azure AD token --> AcrPull role        |
|  No username/password stored anywhere                            |
+------------------------------------------------------------------+
```

---

## 11. CI/CD and Deployment Architecture

### Infrastructure Provisioning (Terraform)

```
Developer runs:
terraform init
terraform plan
terraform apply
       |
       v
Terraform provisions in order:
1.  Resource Group (secure-aks-rg)
2.  Virtual Network + Subnets (frontend, backend)
3.  Network Security Groups (frontend-nsg, backend-nsg)
4.  NSG-Subnet associations
5.  Log Analytics Workspace
6.  Azure Container Registry (Standard)
7.  AKS Cluster (frontendpool + backendpool)
8.  AKS --> ACR role assignment (AcrPull)
9.  Azure Key Vault
10. Microsoft Defender for Containers
11. AKS Diagnostic Settings (kube-audit)
12. Azure Monitor Action Group (email)
13. Monitor Alert Rules x4

Total time: ~10-15 minutes
```

### Application Deployment (Kubernetes)

```
kubectl apply -f K8s/namespace.yaml         # Create fairsplit namespace
kubectl apply -f K8s/pvc.yaml              # Azure Disk PVC
kubectl apply -f K8s/secrets.yaml          # app-secret, smtp-secret
kubectl apply -f K8s/rbac.yaml             # ServiceAccount + Role + RoleBinding
kubectl apply -f K8s/network-policy.yaml   # NetworkPolicy
kubectl apply -f K8s/nginx-configmap.yaml  # NGINX config
kubectl apply -f K8s/backend-deployment.yaml
kubectl apply -f K8s/backend-service.yaml
kubectl apply -f K8s/frontend-deployment.yaml
kubectl apply -f K8s/frontend-service.yaml
kubectl apply -f K8s/ingress.yaml          # Ingress + TLS
kubectl apply -f K8s/cluster-issuer.yaml   # Let's Encrypt ClusterIssuer
```

### Image Update Flow

```
Code change made
       |
       v
docker build -t fairsplitacrq0w0x3.azurecr.io/fairsplit:latest .
       |
       v
az acr login --name fairsplitacrq0w0x3  (OAuth, no password)
       |
       v
docker push fairsplitacrq0w0x3.azurecr.io/fairsplit:latest
       |
       v
kubectl rollout restart deployment/backend -n fairsplit
       |
       v
Kubernetes pulls new image from ACR via Managed Identity
Old pod terminated, new pod starts (zero-downtime rolling update)
```

---

## 12. Component Inventory

### Azure Resources

| Resource | Name | SKU/Tier | Purpose |
|---|---|---|---|
| Resource Group | `secure-aks-rg` | - | Logical container |
| Virtual Network | `10.0.0.0/16` | - | Network isolation |
| Subnet (frontend) | `10.0.1.0/24` | - | Public-facing nodes |
| Subnet (backend) | `10.0.2.0/24` | - | Private nodes |
| NSG | `frontend-nsg` | - | Allow 80, 443 from internet |
| NSG | `backend-nsg` | - | Allow 5000 from VNet only |
| AKS Cluster | `secure-aks-cluster` | Standard | Kubernetes orchestration |
| Node Pool | `frontendpool` | Standard_DS2_v2 | Public workloads |
| Node Pool | `backendpool` | Standard_DS2_v2 | Private workloads |
| Container Registry | `fairsplitacrq0w0x3` | Standard | Image storage + scanning |
| Key Vault | `fairsplit-kv-q0w0x3` | Standard | Secret storage |
| Log Analytics | `aks-log-workspace` | PerGB2018 | Centralized logging |
| Defender | Defender for Containers | - | Runtime threat detection |
| Monitor Action Group | `fairsplit-security-alerts` | - | Email notifications |
| Monitor Alert x4 | brute-force, scanning, idor, log-tamper | Severity 0 | Automated alerting |

### Kubernetes Resources

| Kind | Name | Namespace | Purpose |
|---|---|---|---|
| Namespace | `fairsplit` | cluster | Isolation boundary |
| ServiceAccount | `backend-sa` | fairsplit | Pod identity |
| Role | `backend-role` | fairsplit | Read Secrets only |
| RoleBinding | `backend-binding` | fairsplit | SA to Role |
| Secret | `app-secret` | fairsplit | SECRET_KEY |
| Secret | `smtp-secret` | fairsplit | SMTP credentials |
| Secret | `fairsplit-tls` | fairsplit | TLS certificate |
| PVC | `fairsplit-db-pvc` | fairsplit | Azure Disk (1Gi) |
| ConfigMap | `nginx-config` | fairsplit | NGINX proxy config |
| NetworkPolicy | `backend-policy` | fairsplit | Pod traffic rules |
| Deployment | `backend` | fairsplit | Flask app |
| Deployment | `frontend` | fairsplit | NGINX proxy |
| Service | `backend` | fairsplit | ClusterIP :5000 |
| Service | `frontend` | fairsplit | ClusterIP :80 |
| Ingress | `fairsplit-ingress` | fairsplit | TLS + routing |
| ClusterIssuer | `letsencrypt-prod` | cluster | Let's Encrypt CA |
| Deployment | `ingress-nginx-controller` | ingress-nginx | External traffic entry |
| Deployment | `cert-manager` | cert-manager | Certificate lifecycle |

### Application Files

| File | Purpose |
|---|---|
| `Spiltwise/app.py` | Flask routes, database models, business logic |
| `Spiltwise/security.py` | Threat detection middleware, security event logging |
| `Spiltwise/templates/` | Jinja2 HTML templates (11 pages) |
| `Dockerfile` | Container image build instructions |
| `.dockerignore` | Files excluded from Docker build context |
| `main.tf` | Terraform — all Azure infrastructure |
| `K8s/*.yaml` | Kubernetes manifests (14 files) |
| `nginx.conf` | NGINX reverse proxy configuration |
| `.env.example` | Environment variable reference (no secrets) |
