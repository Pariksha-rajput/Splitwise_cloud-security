# Fairsplit — CS581 Signature Project Overview

**Student:** Pariksha Rajput, JayaPriya
**Course:** CS581 — Cloud Security
**Live URL:** https://20.100.154.95.nip.io

---

## Table of Contents

1. [Project Introduction](#1-project-introduction)
2. [Application — Frontend](#2-application--frontend)
3. [Application — Backend](#3-application--backend)
4. [Database](#4-database)
5. [Containerization — Docker](#5-containerization--docker)
6. [Phase 1 — Architecture Design](#phase-1--architecture-design)
7. [Phase 2 — Cluster Deployment with Terraform (IaC)](#phase-2--cluster-deployment-with-terraform-iac)
8. [Phase 3 — Multi-Tier Application Deployment](#phase-3--multi-tier-application-deployment)
9. [Phase 4 — IAM, RBAC, and Least Privilege](#phase-4--iam-rbac-and-least-privilege)
10. [Phase 5 — Network Security](#phase-5--network-security)
11. [Phase 6 — Data Security](#phase-6--data-security)
12. [Phase 7 — Container Security](#phase-7--container-security)
13. [Phase 8 — Monitoring and Logging](#phase-8--monitoring-and-logging)
14. [Phase 9 — Threat Simulation and Mitigation](#phase-9--threat-simulation-and-mitigation)
15. [TLS / HTTPS](#tls--https)
16. [Complete Deployment Flow](#complete-deployment-flow)

---

## 1. Project Introduction

**Fairsplit** is a web-based expense-splitting and payment tracking application. It allows groups of users to:
- Share and split expenses equally or with custom amounts
- Track who owes whom across the group
- Settle debts using a built-in digital wallet
- Receive real-time in-app and email notifications for activity
- View optimized debt settlement paths using a graph algorithm

The application is deployed on **Microsoft Azure** using a fully automated, security-hardened infrastructure combining Terraform (IaC), Azure Kubernetes Service (AKS), Azure Container Registry (ACR), and Azure Monitor — covering all nine phases of the CS581 Signature Project.

---

## 2. Application — Frontend

### Technology
- **Jinja2 templates** rendered server-side by Flask
- **HTML5, CSS3, vanilla JavaScript** — no external frontend framework
- **Font Awesome** icons, **Google Fonts** (Syne + DM Sans)
- All styling is inline within templates — no separate static asset server required

### Pages
| Page | Route | Description |
|---|---|---|
| Landing | `/` | Public home page with feature overview and sign-up CTA |
| Sign Up | `/signup` | New user registration form |
| Login | `/login` | Email + password authentication |
| Dashboard | `/dashboard` | Financial snapshot, spending charts, recent activity |
| Expenses | `/expenses` | List of all expenses the user is part of |
| Add Expense | `/expenses/add` | Form to create a new shared expense |
| Balances | `/balances` | Simplified debt view + raw balance table |
| Payments | `/payments` | Full payment history (sent, received, top-ups) |
| Wallet | `/wallet` | Wallet balance, top-up, transaction history |
| Notifications | `/notifications` | In-app activity feed + email alert settings |

### NGINX Reverse Proxy (Frontend Pod)
The frontend tier runs **NGINX** in Kubernetes. It acts as a reverse proxy, forwarding all requests to the Flask backend on port 5000:

```nginx
server {
    listen 80;
    location / {
        proxy_pass         http://backend:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

This separates the web-facing layer from the application layer — a standard multi-tier pattern.

---

## 3. Application — Backend

### Technology
| Component | Detail |
|---|---|
| Language | Python 3.11 |
| Framework | Flask 3.0 |
| ORM | Flask-SQLAlchemy 3.1 |
| Password Hashing | Flask-Bcrypt |
| Session Management | Flask server-side sessions (signed cookie) |
| WSGI Server | Gunicorn (2 workers) |
| Email | smtplib via Gmail SMTP |

### Key Features

**Authentication**
- User registration with Bcrypt-hashed passwords
- Session-based login with a custom `@login_required` decorator protecting all routes
- Avatar color auto-assigned from email hash

**Expense Management**
- Create expenses with description, amount, category, paid-by, and members
- Two split modes: Equal (auto-divided) and Custom (manual per-person amounts)
- Live user search via `/api/users/search`
- One-click settle per expense

**Graph-Based Debt Simplification**
Uses a greedy min/max heap algorithm to reduce N debts to the minimum number of transactions:
```
Without simplification:  A→B $10, B→C $10  = 2 transactions
With simplification:     A→C $10            = 1 transaction
```
Complexity: O(N log N) time, O(N) space.

**Wallet System**
- Every user has a digital wallet
- Top-up with preset or custom amounts
- Wallet balance auto-debited/credited on payments

**Notification System**
- In-app activity feed (expense added, payment received, wallet top-up)
- Optional email alerts via Gmail SMTP
- Per-user toggle for email notifications
- Test email button to verify SMTP connectivity

**Security Middleware (`security.py`)**
All threat detection logic lives in a dedicated module:

| Function | Purpose |
|---|---|
| `record_failed_login(ip, email)` | Tracks failed logins per IP; triggers `BRUTE_FORCE_DETECTED` after 5 failures in 5 minutes |
| `is_ip_blocked(ip)` | Returns True if IP is currently blocked |
| `clear_failed_logins(ip)` | Resets counter on successful login |
| `record_unauthorized_access(ip, route, method)` | Logs unauthenticated route hits; triggers `SCANNING_DETECTED` after 10 hits in 1 minute |
| `log_idor_attempt(user_id, email, expense_id, ip)` | Logs IDOR attempts (unauthorized expense settlement) |
| `check_suspicious_payment(user_id, amount, to_user)` | Blocks and logs payments exceeding $5,000 |
| `log_security_event(event_type, details, severity)` | Emits structured JSON to stdout → OMS agent → Log Analytics |

---

## 4. Database

### Engine
**SQLite** stored on an **Azure Disk** (PersistentVolumeClaim) mounted at `/app/instance/fairsplit.db`. The disk persists independently of pod restarts and cluster stop/start.

### Schema

**User** — registered accounts
| Column | Type | Notes |
|---|---|---|
| id | Integer | Primary key |
| name | String | Display name |
| email | String | Unique, used for login |
| password | String | Bcrypt hash |
| avatar_color | String | Hex color from email hash |
| created_at | DateTime | Registration timestamp |

**Expense** — shared expense records
| Column | Type | Notes |
|---|---|---|
| id | Integer | Primary key |
| description | String | What the expense was for |
| amount | Float | Total amount |
| category | String | Food, Travel, Rent, etc. |
| split_type | String | equal or custom |
| paid_by | FK → User | Who paid upfront |
| created_at | DateTime | When created |

**ExpenseSplit** — per-user share of each expense
| Column | Type | Notes |
|---|---|---|
| expense_id | FK → Expense | |
| user_id | FK → User | |
| amount | Float | This user's share |

**Payment** — direct payments between users
| Column | Type | Notes |
|---|---|---|
| from_user | FK → User | Sender |
| to_user | FK → User | Receiver |
| amount | Float | Payment amount |
| note | String | Optional memo |
| status | String | completed |

**Wallet** — per-user balance
| Column | Type | Notes |
|---|---|---|
| user_id | FK → User | One-to-one |
| balance | Float | Current balance |

**Notification** — in-app activity events
| Column | Type | Notes |
|---|---|---|
| user_id | FK → User | Recipient |
| event_type | String | expense_added, payment_received, etc. |
| message | String | Human-readable description |
| is_read | Boolean | Read status |
| created_at | DateTime | When fired |

**NotificationSettings** — per-user email preferences
| Column | Type | Notes |
|---|---|---|
| user_id | FK → User | One-to-one |
| wallet_email_notifications | Boolean | Email alerts enabled |

**Junction Tables**
- `expense_members` — many-to-many: Expense ↔ User (who is in the expense)
- `expense_settled` — many-to-many: Expense ↔ User (who has settled their share)

### Table Creation
`db.create_all()` runs at module import time (outside `if __name__ == "__main__"`), so Gunicorn triggers it on startup — no manual migration step needed.

---

## 5. Containerization — Docker

### Dockerfile
```dockerfile
FROM python:3.11-slim          # minimal base image — no unnecessary OS packages

WORKDIR /app

COPY Spiltwise/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Spiltwise/app.py Spiltwise/security.py ./
COPY Spiltwise/templates/ templates/

RUN useradd -m appuser && chown -R appuser /app
USER appuser                   # non-root user (UID 1000)

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
```

### Security Choices
| Choice | Reason |
|---|---|
| `python:3.11-slim` | Minimal attack surface — no compiler, no shell utilities |
| `--no-cache-dir` | Smaller image, no pip cache left on disk |
| Non-root user `appuser` (UID 1000) | Container cannot write to host filesystem even if compromised |
| Gunicorn instead of Flask dev server | Production-grade WSGI; dev server disabled debug mode |

### Registry
Image is stored in **Azure Container Registry (ACR)**:
```
fairsplitacrq0w0x3.azurecr.io/fairsplit:latest
```
ACR Standard tier includes built-in vulnerability scanning.

---

## 6. Docker Images Built

### Custom Image

| Image | Registry | Tag | Approx Size |
|---|---|---|---|
| `fairsplit` | `fairsplitacrq0w0x3.azurecr.io` | `latest` | ~62 MB |

Built from `python:3.11-slim`, contains only: Python runtime, pip packages from `requirements.txt`, `app.py`, `security.py`, and `templates/`. No build tools, no shell utilities, no unnecessary OS packages.

### Public Images Pulled at Deploy Time

| Image | Pulled By | Purpose |
|---|---|---|
| `nginx:alpine` | Frontend Deployment | Reverse proxy in the frontend pod |
| `registry.k8s.io/ingress-nginx/controller:v1.x` | ingress-nginx Deployment | NGINX Ingress Controller |
| `quay.io/jetstack/cert-manager-controller` | cert-manager | Certificate lifecycle management |
| `quay.io/jetstack/cert-manager-cainjector` | cert-manager | CA certificate injection |
| `quay.io/jetstack/cert-manager-webhook` | cert-manager | Admission webhook for cert validation |

**Total: 6 images** (1 custom + 5 public). All public images are pulled once and cached on each node — they are not stored in ACR.

### How the Custom Image Was Built and Pushed

```bash
# 1. Authenticate Docker to ACR via Azure CLI (no password stored)
az acr login --name fairsplitacrq0w0x3

# 2. Build — Docker reads Dockerfile, layers are cached per RUN/COPY
docker build -t fairsplitacrq0w0x3.azurecr.io/fairsplit:latest .

# 3. Push to ACR
docker push fairsplitacrq0w0x3.azurecr.io/fairsplit:latest
```

---

## 7. Running Pods — Live Inventory

### Namespace: `fairsplit`

| Pod Name | Container Image | Node Pool | Replicas | Purpose |
|---|---|---|---|---|
| `backend-XXXX` | `fairsplitacrq0w0x3.azurecr.io/fairsplit:latest` | backendpool | 2 (HPA: 1-5) | Flask + Gunicorn app server |
| `frontend-XXXX` | `nginx:alpine` | frontendpool | 2 (HPA: 1-3) | NGINX reverse proxy |

### Namespace: `ingress-nginx`

| Pod Name | Node Pool | Purpose |
|---|---|---|
| `ingress-nginx-controller-XXXX` | frontendpool | Routes external HTTPS into cluster |
| `ingress-nginx-admission-create-XXXX` | any (completed Job) | One-time webhook cert creation |
| `ingress-nginx-admission-patch-XXXX` | any (completed Job) | One-time webhook cert patching |

### Namespace: `cert-manager`

| Pod Name | Purpose |
|---|---|
| `cert-manager-XXXX` | Core: manages Certificate and CertificateRequest objects |
| `cert-manager-cainjector-XXXX` | Injects CA bundles into webhook configs |
| `cert-manager-webhook-XXXX` | Validates cert-manager resource submissions |

**Total active pods: 8** (2 backend + 2 frontend + 1 ingress-nginx-controller + 3 cert-manager)

### Node Distribution

```
frontendpool (public subnet 10.0.1.0/24)
  - frontend pod x2        — nginx:alpine
  - ingress-nginx-controller — handles internet traffic + Let's Encrypt challenge

backendpool (private subnet 10.0.2.0/24, no direct internet)
  - backend pod x2         — flask/gunicorn + sqlite on Azure Disk
```

### Horizontal Pod Autoscaler

| Deployment | Min | Max | Scale Trigger |
|---|---|---|---|
| backend | 1 | 5 | CPU > 70% |
| frontend | 1 | 3 | CPU > 70% |

---

## 8. How Docker and Kubernetes Communicate

### Full Image Lifecycle

```
Developer machine
    |
    |- docker build  -->  creates layers  -->  local image
    |
    +- docker push   -->  sends layers to ACR (fairsplitacrq0w0x3.azurecr.io)
                                |
                                v  (pull on pod schedule)
                         AKS Node (kubelet)
                         |- contacts ACR using Managed Identity (no password)
                         |- pulls image layers via HTTPS
                         +- hands image to containerd runtime
                                |
                                v
                         Container (isolated Linux namespace)
                         running Flask/Gunicorn on port 5000
```

### Why No Credentials Are Needed

AKS nodes have a **SystemAssigned Managed Identity** that is granted the **AcrPull** role on the ACR resource. When `containerd` needs to pull an image, it requests an OAuth token from Azure AD using the node's identity — no username, no password, no secrets. This is configured in Terraform:

```hcl
resource "azurerm_role_assignment" "aks_acr_pull" {
  principal_id         = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  role_definition_name = "AcrPull"
  scope                = azurerm_container_registry.acr.id
}
```

### How Kubernetes Injects Configuration into Containers

Kubernetes does not modify the Docker image — it passes configuration at runtime:

| Mechanism | How | Example in This Project |
|---|---|---|
| Environment variables | `env:` in pod spec | `SECRET_KEY`, `DATABASE_URL` |
| Secrets | `secretKeyRef` mapped to env var | `app-secret`, `smtp-secret` |
| Volumes / PVC | Mounted as filesystem path | Azure Disk at `/app/instance/` |

The container image itself contains **no secrets** — a compromised image leaks no credentials.

### Pod-to-Pod Networking

```
Browser request
    |
    v
NGINX Ingress Controller Pod (port 443)
    |  (cluster-internal DNS)
    v
frontend Service (ClusterIP, port 80)
    |
    v
frontend Pod -- nginx:alpine (port 80)
    |  proxy_pass http://backend:5000
    v
backend Service (ClusterIP, port 5000)
    |
    v
backend Pod -- gunicorn (port 5000)
    |
    v
Azure Disk PVC (/app/instance/fairsplit.db)
```

Kubernetes **DNS** resolves service names (`backend`, `frontend`) within the `fairsplit` namespace automatically — no IP addresses hardcoded anywhere.

---

## 9. Ingress -- Deep Dive

### What Is an Ingress?

An **Ingress** is a Kubernetes resource that defines HTTP/HTTPS routing rules. By itself it does nothing — it requires an **Ingress Controller** to implement those rules.

In this project:
- **Ingress resource** (`K8s/ingress.yaml`) — defines the rules: host, path, TLS, backend service
- **Ingress Controller** (`ingress-nginx` Deployment) — reads the rules and configures NGINX accordingly

### The Ingress YAML Explained

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fairsplit-ingress
  namespace: fairsplit
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod     # auto-provision TLS cert
    nginx.ingress.kubernetes.io/ssl-redirect: "true"      # HTTP to HTTPS redirect
spec:
  ingressClassName: nginx       # use the nginx ingress controller
  tls:
  - hosts:
    - 20.100.154.95.nip.io
    secretName: fairsplit-tls   # cert-manager stores the cert here
  rules:
  - host: 20.100.154.95.nip.io
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend      # send all traffic to the frontend Service
            port:
              number: 80
```

### Full HTTPS Request Flow

```
1. Browser  --> https://20.100.154.95.nip.io
2. nip.io DNS resolves to 20.100.154.95 (Azure Load Balancer public IP)
3. Azure Load Balancer forwards :443 to ingress-nginx-controller pod
4. NGINX Ingress Controller:
   a. Terminates TLS (uses cert stored in fairsplit-tls Secret)
   b. Checks Host header: matches 20.100.154.95.nip.io
   c. Checks path: / matches prefix rule
   d. Forwards decrypted HTTP --> frontend Service :80
5. frontend Service (ClusterIP) load balances to a frontend pod
6. frontend pod (nginx:alpine) proxy_pass --> backend Service :5000
7. backend Service (ClusterIP) routes to a backend pod
8. backend pod (Flask/Gunicorn) reads/writes SQLite on Azure Disk
9. Response travels back the same chain, re-encrypted at step 4
```

### HTTP to HTTPS Redirect Flow

```
Browser --> http://20.100.154.95.nip.io  (port 80)
    |
    v
NGINX Ingress Controller (receives on port 80)
    |  ssl-redirect: "true" triggers 301
    v
301 Moved Permanently --> https://20.100.154.95.nip.io
    |
    v
Browser re-requests on port 443 --> full HTTPS flow above
```

### cert-manager and Let's Encrypt Lifecycle

```
1. ingress.yaml applied with cert-manager.io/cluster-issuer annotation
2. cert-manager reads ingress  --> creates Certificate object
3. cert-manager creates Order  --> sends ACME challenge request to Let's Encrypt
4. Let's Encrypt responds: "prove you control this domain"
5. cert-manager creates Challenge --> tells NGINX Ingress to serve
   token at: http://20.100.154.95.nip.io/.well-known/acme-challenge/<token>
6. Let's Encrypt HTTP GET --> NGINX serves the token --> challenge passes
7. Let's Encrypt issues signed certificate
8. cert-manager stores cert + key in Kubernetes Secret: fairsplit-tls
9. NGINX Ingress Controller reads the Secret --> serves HTTPS with valid cert
10. Browser shows padlock -- no "Not Secure" warning
```

### Why the Ingress Controller Must Run on frontendpool

The HTTP-01 challenge requires Let's Encrypt to reach the cluster on port 80. The `backendpool` subnet has no direct internet access (NSG: allow VNet only). When ingress-nginx was on `backendpool`, the challenge timed out. Pinning it to `frontendpool` with a `nodeSelector` fixed this:

```yaml
# K8s/ingress-nginx-patch.yaml
spec:
  template:
    spec:
      nodeSelector:
        agentpool: frontendpool
```

### nip.io -- Free Wildcard DNS

`nip.io` is a public DNS service that encodes the IP in the hostname:
```
20.100.154.95.nip.io  -->  A record  -->  20.100.154.95
```
This provides a real resolvable domain name without purchasing one — required because Let's Encrypt does not issue certificates for bare IP addresses.

---

## 10. Security Concepts -- End to End

### Defense in Depth (7 Layers)

```
Layer 1: Azure NSG (Network Security Group)
         - frontend-nsg: Allow TCP 80,443 from Internet; deny all else
         - backend-nsg:  Allow TCP 5000 from VNet only (10.0.0.0/16)

Layer 2: Kubernetes NetworkPolicy
         - backend: allow ingress :5000 from frontend pods only
         - frontend: allow ingress :80 from ingress-nginx namespace only

Layer 3: NGINX Ingress Controller
         - TLS termination (no plaintext outside cluster)
         - HTTP to HTTPS redirect
         - Host-based routing (only known hosts forwarded)

Layer 4: Frontend NGINX (proxy)
         - Forwards requests to backend only; backend port never exposed externally
         - Sets X-Real-IP, X-Forwarded-For headers (Flask gets real client IP)

Layer 5: Flask Authentication
         - @login_required decorator on every non-public route
         - Bcrypt password hashing (cost factor 12)
         - Signed session cookie (Flask SECRET_KEY)

Layer 6: security.py Middleware
         - Brute force: 5 failures / 5 min  --> IP blocked + alert fired
         - IDOR: expense ownership verified before settlement
         - Scanning: 10 unauthenticated hits / 1 min --> alert fired
         - Suspicious payment: amount > $5,000 --> blocked + alert fired

Layer 7: Azure Monitor + Defender
         - Log Analytics receives structured JSON from every pod
         - Scheduled Query Alert fires on BRUTE_FORCE_DETECTED / SCANNING_DETECTED
         - Microsoft Defender for Containers: runtime threat detection
```

### Secret Management -- Zero Plaintext Rule

```
Developer           Kubernetes Secret         Container
---------           -----------------         ---------
Raw value     -->   base64-encoded      -->   Env var
"my-smtp-pass"      "bXktc210cC1wYXNz"        $SMTP_PASS
              b64enc                   injected at pod start

NEVER in:
  - Source code (app.py, security.py)
  - Dockerfile
  - Git repository
  - Docker image layers
  - Log output

ONLY in:
  - Kubernetes Secret objects (etcd, AKS-managed encryption at rest)
  - Azure Key Vault (for production rotation)
  - .env file (local dev only, in .gitignore)
```

### Kubernetes RBAC -- Least Privilege

```yaml
# backend ServiceAccount: can only read Secrets in fairsplit namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: backend-role
  namespace: fairsplit
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get"]
```

If the Flask container is compromised, the attacker cannot use kubectl to escalate — the ServiceAccount token has read-only access to one namespace.

### Zero-Trust Principles Applied

| Principle | Implementation |
|---|---|
| Never trust, always verify | Every request validated by Flask `@login_required`; sessions checked per-request |
| Least privilege | RBAC: backend SA read-only; NSG: backend port only from VNet; NetworkPolicy: pod-to-pod only |
| Assume breach | security.py detects and logs attacks even from authenticated users (IDOR, suspicious payments) |
| Encrypt in transit | TLS everywhere: browser to ingress (Let's Encrypt cert), VNet traffic encrypted by Azure |
| Encrypt at rest | AKS etcd encrypted; Azure Disk (PVC) encrypted by Azure Disk Encryption |
| Audit everything | Structured JSON logs to Log Analytics; kube-audit logs to Diagnostic Settings |

### Container Isolation -- Linux Namespaces

| Namespace | What It Isolates |
|---|---|
| `pid` | Process IDs -- container processes cannot see host PIDs |
| `net` | Network interfaces -- container has its own virtual NIC |
| `mnt` | Filesystem mounts -- container sees only its own filesystem + mounted volumes |
| `user` | User IDs -- UID 1000 inside maps to unprivileged on host |
| `ipc` | IPC mechanisms -- containers cannot share memory with each other |

Combined with `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, and no `hostNetwork`, a compromised container cannot escape to the host node.

### The Two NGINXes Explained

| | NGINX Ingress Controller | Frontend Pod NGINX |
|---|---|---|
| **What it is** | Kubernetes infrastructure component | Application container |
| **Namespace** | `ingress-nginx` | `fairsplit` |
| **Node pool** | frontendpool (public) | frontendpool |
| **Image** | `ingress-nginx/controller` (specialized) | `nginx:alpine` (standard) |
| **Purpose** | Routes external traffic; terminates TLS | Proxies HTTP to Flask backend |
| **Config source** | Reads Ingress YAML resources automatically | `K8s/nginx-configmap.yaml` |
| **Listens on** | External IP :80, :443 | Internal ClusterIP :80 |
| **Talks to** | frontend Service | backend Service |

---

## Phase 1 — Architecture Design

### Network Architecture
```
Internet (HTTPS :443)
        |
  NGINX Ingress Controller (LoadBalancer IP: 20.100.154.95)
  TLS terminated here — cert-manager + Let's Encrypt certificate
        |
  frontend-subnet (10.0.1.0/24)   ← Azure NSG: Allow HTTP/HTTPS from Internet
  AKS Frontend Node Pool
  ┌─────────────────────┐
  │  NGINX Pod (x2)     │  ← Reverse proxy to backend
  └─────────────────────┘
        |
  backend-subnet (10.0.2.0/24)    ← Azure NSG: Allow VNet only (10.0.0.0/16)
  AKS Backend Node Pool
  ┌─────────────────────┐
  │  Flask/Gunicorn (x1)│  ← Reads/writes SQLite on Azure Disk
  └─────────────────────┘
        |
  Azure Disk (PVC: fairsplit-db-pvc, 1Gi)
```

### Azure Resources Overview
| Resource | Azure Service | Purpose |
|---|---|---|
| Resource Group | `secure-aks-rg` | Container for all resources |
| Virtual Network | `10.0.0.0/16` | Isolated network (VPC equivalent) |
| Frontend Subnet | `10.0.1.0/24` | Public-facing node pool |
| Backend Subnet | `10.0.2.0/24` | Private node pool |
| NSG (x2) | Network Security Groups | Traffic rules per subnet |
| AKS Cluster | `secure-aks-cluster` | Kubernetes orchestration |
| ACR | `fairsplitacrq0w0x3` | Docker image registry |
| Key Vault | `fairsplit-kv-q0w0x3` | Secrets storage |
| Log Analytics | `aks-log-workspace` | Centralized log store |
| Microsoft Defender | Defender for Containers | Threat detection |
| Monitor Alerts | Scheduled Query Rules | Brute force + scanning alerts |

### Load Balancing
- **NGINX Ingress Controller** — handles TLS termination, routes HTTPS traffic into the cluster
- **Frontend Service** — ClusterIP LoadBalancer exposes NGINX pods internally
- **Backend Service** — ClusterIP on port 5000, reachable only within the cluster

---

## Phase 2 — Cluster Deployment with Terraform (IaC)

All Azure infrastructure is defined in `main.tf` and provisioned with a single `terraform apply`.

### AKS Cluster Configuration
```
AKS Cluster: secure-aks-cluster
├── Identity: SystemAssigned Managed Identity
├── RBAC: Enabled
├── Network plugin: Azure CNI
├── Load balancer SKU: Standard
├── Kubernetes version: 1.29+
├── OMS Agent → Log Analytics (container log forwarding)
├── Microsoft Defender → Log Analytics (threat detection)
├── frontend node pool → frontend-subnet (10.0.1.0/24)
└── backend node pool  → backend-subnet  (10.0.2.0/24)
```

### Terraform Deployment Order
```
terraform init
export TF_VAR_db_password="YourStrongP@ssword123!"
terraform plan
terraform apply    # ~10-15 minutes
```

Provisions: Resource Group → VNet + Subnets + NSGs → Log Analytics → ACR → AKS (both node pools) → AKS→ACR role assignment → Key Vault → Microsoft Defender → Diagnostic Settings → Monitor alert rules.

### AWS → Azure Mapping
| AWS Service | Azure Equivalent |
|---|---|
| VPC | Azure Virtual Network |
| Security Groups / NACLs | Network Security Groups |
| EKS | Azure Kubernetes Service |
| ECR | Azure Container Registry |
| Secrets Manager | Azure Key Vault |
| CloudWatch Logs | Log Analytics Workspace |
| CloudTrail | AKS Diagnostic Settings (kube-audit) |
| GuardDuty | Microsoft Defender for Containers |
| SNS Topic | Azure Monitor Action Group |
| CloudWatch Alarms | Scheduled Query Alert Rules |

---

## Phase 3 — Multi-Tier Application Deployment

### Kubernetes Resources Applied
```
kubectl apply -f K8s/namespace.yaml          # fairsplit namespace
kubectl apply -f K8s/pvc.yaml               # Azure Disk for SQLite
kubectl apply -f K8s/secrets.yaml           # app-secret (SECRET_KEY)
kubectl apply -f K8s/rbac.yaml              # ServiceAccount + Role + RoleBinding
kubectl apply -f K8s/network-policy.yaml    # Pod-level traffic rules
kubectl apply -f K8s/nginx-configmap.yaml   # NGINX reverse proxy config
kubectl apply -f K8s/backend-deployment.yaml
kubectl apply -f K8s/backend-service.yaml
kubectl apply -f K8s/frontend-deployment.yaml
kubectl apply -f K8s/frontend-service.yaml
kubectl apply -f K8s/hpa.yaml               # Auto-scaling
kubectl apply -f K8s/ingress.yaml           # TLS ingress
kubectl apply -f K8s/cluster-issuer.yaml    # Let's Encrypt issuer
```

### Tier Breakdown
| Tier | Implementation | Replicas |
|---|---|---|
| Frontend | NGINX (nginx:alpine) reverse proxy | 2 pods on frontendpool |
| Backend | Flask + Gunicorn (fairsplitacrq0w0x3.azurecr.io/fairsplit:latest) | 1 pod on backendpool |
| Database | SQLite on Azure Disk PVC (1Gi, ReadWriteOnce) | Persistent across restarts |

### Horizontal Pod Autoscaler
```yaml
minReplicas: 2
maxReplicas: 5
target: CPU utilization 70%
```
Backend scales from 2 to 5 pods automatically under load. Note: ReadWriteOnce disk limits backend to 1 replica in practice — HPA applies to the frontend tier.

---

## Phase 4 — IAM, RBAC, and Least Privilege

### AKS Managed Identity (Cluster-Level)
- AKS cluster uses **SystemAssigned Managed Identity** — no static credentials
- Terraform assigns the **AcrPull** role to the kubelet identity:
  ```
  azurerm_role_assignment: AcrPull on ACR → AKS kubelet identity
  ```
  This allows AKS nodes to pull images from ACR without storing registry credentials anywhere.

### Kubernetes RBAC (Namespace-Level)
Defined in `K8s/rbac.yaml`:

```yaml
ServiceAccount: backend-sa       # identity for backend pods
Role: backend-role               # what that identity can do
  rules:
  - resources: ["pods"]
    verbs: ["get", "list"]       # read-only — cannot create, delete, or update pods
RoleBinding: backend-binding     # links backend-sa to backend-role
```

**Least privilege applied:** The backend pod can only read pod information within the `fairsplit` namespace. It cannot modify cluster state, access other namespaces, or perform destructive operations.

### Pod Security Context
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000          # appuser (non-root)
  allowPrivilegeEscalation: false
  fsGroup: 1000            # mounted volume owned by appuser
```

---

## Phase 5 — Network Security

### Azure NSG Rules (Subnet Level)
| Subnet | Inbound Rules | Outbound |
|---|---|---|
| frontend-subnet (10.0.1.0/24) | Allow TCP 80, 443 from Internet | Allow all |
| backend-subnet (10.0.2.0/24) | Allow VNet (10.0.0.0/16) only — Deny Internet | Allow all |

### Kubernetes Network Policy (Pod Level)
Defined in `K8s/network-policy.yaml`:
```yaml
podSelector: app=backend
policyTypes: [Ingress]
ingress:
  - from:
    - podSelector: app=frontend
```
**Effect:** Only pods labeled `app=frontend` can reach the backend pods on port 5000. Any other pod (including compromised pods in other namespaces) is blocked at the network layer.

### NGINX Ingress (Application Level)
- All HTTP traffic auto-redirected to HTTPS (`ssl-redirect: true`)
- TLS terminated at the ingress controller — backend never handles raw TLS
- Only routes defined in the ingress are exposed externally

### Defense in Depth
```
Internet
  → NSG (subnet level): only 80/443 allowed
  → NGINX Ingress (application level): TLS, routing
  → Kubernetes NetworkPolicy (pod level): frontend→backend only
  → Flask @login_required (app level): all routes require session
```

---

## Phase 6 — Data Security

### Secrets Management
All sensitive values are stored as **Kubernetes Secrets** (base64-encoded, etcd-encrypted at rest in AKS):

| Secret Name | Keys | Used By |
|---|---|---|
| `app-secret` | `secret-key` | Flask session signing |
| `smtp-secret` | `smtp-host`, `smtp-user`, `smtp-pass` | Email notifications |

Secrets are injected as environment variables — never hardcoded in code or Docker images.

**Azure Key Vault** is provisioned via Terraform for production-grade secret storage. Key Vault stores the database password and Flask secret key and is accessible only from within the AKS VNet.

### Encryption
| Data | Encryption |
|---|---|
| SQLite database file | Azure Disk encrypted at rest by default (AES-256, platform-managed key) |
| Traffic in transit | TLS 1.2/1.3 via Let's Encrypt certificate (HTTPS enforced) |
| Passwords in database | Bcrypt hashed (cost factor 12) — never stored in plaintext |
| K8s Secrets (etcd) | Encrypted at rest by AKS |

### PersistentVolumeClaim
```yaml
storageClassName: managed-csi   # Azure Disk (CSI driver)
accessModes: [ReadWriteOnce]
storage: 1Gi
```
The Azure Disk persists independently of pod lifecycle. Stopping or restarting the AKS cluster does not delete the database.

---

## Phase 7 — Container Security

### Dockerfile Security Measures
| Measure | Implementation |
|---|---|
| Minimal base image | `python:3.11-slim` — no compiler, debugger, or shell tools |
| No cache left on disk | `pip install --no-cache-dir` |
| Non-root user | `useradd -m appuser` + `USER appuser` (UID 1000) |
| No privilege escalation | `allowPrivilegeEscalation: false` in pod spec |
| Read-only root filesystem | Container writes only to `/app/instance` (mounted PVC) |

### ACR Vulnerability Scanning
Images pushed to **Azure Container Registry Standard tier** are automatically scanned for known CVEs using Microsoft Defender for Containers. Scan results are visible in:
```
Azure Portal → Defender for Cloud → Recommendations → Container images
```

### Image Pull Security
AKS pulls images from ACR using the **kubelet Managed Identity** with the **AcrPull** role — no registry credentials stored in the cluster, no `imagePullSecrets` needed.

---

## Phase 8 — Monitoring and Logging

### Log Flow Architecture
```
Flask app logs JSON to stdout
        |
   Gunicorn stdout
        |
   AKS OMS Agent (DaemonSet on every node)
        |
   Log Analytics Workspace (aks-log-workspace)
        |
   Azure Monitor Scheduled Query Alert Rules
        |
   Azure Monitor Action Group
        |
   Email alert → pariksha.rajput2912@gmail.com
```

### Security Event Log Format
Every security event is emitted as structured JSON:
```json
{
  "timestamp": "2026-04-27T05:18:07Z",
  "service": "fairsplit",
  "event_type": "BRUTE_FORCE_DETECTED",
  "severity": "CRITICAL",
  "details": {
    "ip": "10.0.2.27",
    "email": "attacker@example.com",
    "attempts_in_window": 5,
    "action": "IP blocked from further login attempts"
  }
}
```

### Azure Monitor Alert Rules (defined in main.tf)
| Rule Name | Query | Window | Severity |
|---|---|---|---|
| `brute-force-detection` | `ContainerLog \| where LogEntry contains "BRUTE_FORCE_DETECTED"` | PT5M | 0 (Critical) |
| `scanning-detection` | `ContainerLog \| where LogEntry contains "SCANNING_DETECTED"` | PT1M | 0 (Critical) |

### Kubernetes Audit Logging
AKS diagnostic settings (configured in Terraform) stream `kube-audit` logs to Log Analytics — equivalent to AWS CloudTrail. Every API call to the Kubernetes control plane is recorded permanently.

### Microsoft Defender for Containers
Enabled via Terraform (`azurerm_security_center_subscription_pricing`). Detects:
- Privileged container execution
- Suspicious kubectl exec activity
- Anomalous process behavior inside containers
- Cryptocurrency mining attempts

### Querying Logs
```
# Azure Portal → Log Analytics workspace → Logs

# View all security events
ContainerLog
| where LogEntry contains "fairsplit"
| where LogEntry contains "CRITICAL"
| order by TimeGenerated desc

# Brute force events only
ContainerLog
| where LogEntry contains "BRUTE_FORCE_DETECTED"

# Scanning events
ContainerLog
| where LogEntry contains "SCANNING_DETECTED"
```

---

## Phase 9 — Threat Simulation and Mitigation

### Scenario 1 — Brute Force Attack on Login

**What:** Attacker repeatedly tries wrong passwords to gain account access.

**Threshold:** 3 failed attempts from the same IP within 5 minutes.

**How to simulate:**
```bash
# Hit login endpoint 5+ times with wrong password
curl -X POST https://20.100.154.95.nip.io/login \
  -d "email=victim@example.com&password=wrongpassword" -k
# Repeat 5 times
```

**Detection chain:**
1. `record_failed_login(ip, email)` called on each failure
2. After 5th failure: `BRUTE_FORCE_DETECTED` logged as CRITICAL JSON to stdout
3. OMS agent ships log to Log Analytics
4. Azure Monitor alert fires → email sent to security team
5. `is_ip_blocked(ip)` returns True — subsequent login attempts rejected immediately

**App response to blocked IP:**
```
HTTP 403: Too many failed login attempts. Your IP has been temporarily blocked.
```

---

### Scenario 2 — IDOR Attack (Unauthorized Expense Settlement)

**What:** Authenticated attacker (Eve) manipulates the settlement URL to mark someone else's expense as paid — wiping another user's debt without paying it.

**How it works:**
```
Normal flow:
  Alice logs in → POST /expenses/42/settle
  → app checks: is Alice in expense 42's members? Yes → marks settled ✓

Attack:
  Eve logs in → POST /expenses/43/settle
  → expense 43 belongs to Alice & Bob, not Eve
  → WITHOUT protection: debt wiped → Bob thinks he paid → Alice loses money
  → WITH protection: app checks membership → 403 Forbidden → logs alert
```

**How to simulate:**
1. Log in as User A
2. Find an expense ID that belongs to a different user
3. Manually craft: `POST https://20.100.154.95.nip.io/expenses/<other_id>/settle`

**Detection:**
- `log_idor_attempt(user_id, email, expense_id, ip)` fires immediately
- `IDOR_ATTEMPT_DETECTED` logged as CRITICAL to stdout → Log Analytics
- Azure Monitor alert triggers → email notification sent

---

### Scenario 3 — Log Deletion / Audit Tampering

**What:** An attacker who has gained access attempts to delete logs or tamper with audit records to cover their tracks. This tests three attack surfaces: the application API, the pod filesystem, and the Kubernetes control plane.

**Attack Surface 1 — DELETE via application API**

A protected endpoint `/system/logs` is exposed. Any `DELETE` or `PATCH` request is blocked and logged as a `LOG_TAMPER_ATTEMPT` event. The logged-in user's email and ID are captured alongside the IP address.

How to simulate (logged-in user via browser console):
```javascript
fetch('/system/logs', {method: 'DELETE'}).then(r => r.json()).then(console.log)
```

How to simulate (unauthenticated via curl):
```bash
curl -k -X DELETE https://20.100.154.95.nip.io/system/logs
```

Expected response:
```json
{"error": "Forbidden — log tampering detected and recorded"}
```

Expected log event:
```json
{
  "event_type": "LOG_TAMPER_ATTEMPT",
  "severity": "CRITICAL",
  "details": {
    "ip": "x.x.x.x",
    "method": "DELETE",
    "route": "/system/logs",
    "user_email": "pariksha.rajput2912@gmail.com",
    "user_id": 1,
    "action": "Blocked — destructive method not permitted on this endpoint"
  }
}
```

Detection chain:
```
Attacker sends DELETE /system/logs
        |
        v
log_tamper_attempt() fires in security.py (captures IP + user identity)
        |
        v
LOG_TAMPER_ATTEMPT logged as CRITICAL JSON to stdout
        |
        v
AKS OMS Agent ships log to Log Analytics Workspace
        |
        v
Azure Monitor Scheduled Query Alert (log-tamper-detection)
queries ContainerLog every 5 minutes
        |
        v
Action Group triggered
        |
        v
Email alert sent to pariksha.rajput2912@gmail.com
```

Azure Monitor alert rule (`main.tf`):
```hcl
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "log_tamper_alert" {
  name                 = "log-tamper-detection"
  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"
  severity             = 0
  criteria {
    query = "ContainerLog | where LogEntry contains \"LOG_TAMPER_ATTEMPT\""
    time_aggregation_method = "Count"
    threshold               = 1
    operator                = "GreaterThanOrEqual"
  }
  action {
    action_groups = [azurerm_monitor_action_group.security_alerts.id]
  }
}
```

**Attack Surface 2 — Exec into pod and delete log files**

```bash
kubectl exec -it deployment/backend -n fairsplit -- /bin/sh
find / -name "*.log" 2>/dev/null
ls /var/log/
```

Expected result: No application log files exist. All logs go to stdout only — captured by the AKS OMS agent and shipped to Log Analytics before the attacker can access them. The pod filesystem contains no deletable log data.

**Attack Surface 3 — Delete the pod to wipe logs**

```bash
kubectl delete pod -l app=backend -n fairsplit
```

Expected result: Kubernetes recreates the pod within seconds. All events already shipped to Log Analytics remain intact and immutable.

**Defense Summary:**

| Attack | Defense |
|---|---|
| DELETE /system/logs | Route blocked, `LOG_TAMPER_ATTEMPT` fired with attacker identity, email alert sent |
| Exec into pod, delete log files | No log files exist — stdout only, already shipped externally |
| Delete the pod | Kubernetes recreates it; Log Analytics retains all prior events |
| Delete Log Analytics workspace | Azure RBAC + Resource Lock (`CanNotDelete`) blocks deletion |

**Verify in Log Analytics:**
```kusto
ContainerLog
| where LogEntry contains "LOG_TAMPER_ATTEMPT"
| project TimeGenerated, LogEntry
| order by TimeGenerated desc
| take 10
```

---

### Scenario 4 — Route Scanning (Unauthorized Access Probing)

**What:** Bot or attacker probes protected routes without a valid session, attempting to enumerate the application.

**Threshold:** 10 unauthorized route hits from same IP within 1 minute.

**How to simulate:**
```bash
# Hit protected routes without a session cookie 10+ times
for i in {1..12}; do
  curl -s https://20.100.154.95.nip.io/dashboard -k
  curl -s https://20.100.154.95.nip.io/wallet -k
  curl -s https://20.100.154.95.nip.io/expenses -k
done
```

**Detection:**
- Each hit calls `record_unauthorized_access(ip, route, method)`
- After 10 hits: `SCANNING_DETECTED` logged as CRITICAL
- Azure Monitor alert fires

---

### Security Event Summary

| Event | Trigger | Severity | Response |
|---|---|---|---|
| `FAILED_LOGIN` | Each wrong password | WARNING | Logged |
| `BRUTE_FORCE_DETECTED` | 3+ failures in 5 min | CRITICAL | IP blocked + email alert |
| `UNAUTHORIZED_ACCESS` | Unauthenticated route hit | WARNING | Logged |
| `SCANNING_DETECTED` | 10+ hits in 1 min | CRITICAL | Email alert |
| `IDOR_ATTEMPT_DETECTED` | Settling another user's expense | CRITICAL | 403 + email alert |
| `LOG_TAMPER_ATTEMPT` | DELETE/PATCH on /system/logs | CRITICAL | 403 + logged + email alert |

---

## TLS / HTTPS

### Components
| Component | Role |
|---|---|
| NGINX Ingress Controller | Handles TLS termination, routes HTTPS into cluster |
| cert-manager | Automatically provisions and renews TLS certificates |
| Let's Encrypt | Free, trusted CA (90-day certificates) |
| nip.io | Wildcard DNS service mapping `20.100.154.95.nip.io` → `20.100.154.95` |

### Certificate Lifecycle
```
cert-manager detects Ingress with cert-manager.io/cluster-issuer annotation
    |
Creates Certificate object → CertificateRequest → Order → Challenge
    |
Let's Encrypt sends HTTP-01 challenge to:
http://20.100.154.95.nip.io/.well-known/acme-challenge/<token>
    |
NGINX Ingress Controller (on frontendpool node) serves the challenge response
    |
Let's Encrypt validates → issues certificate → stored in Secret: fairsplit-tls
    |
NGINX Ingress Controller uses fairsplit-tls for HTTPS
    |
cert-manager auto-renews 30 days before expiry
```

### HTTPS Enforcement
```yaml
nginx.ingress.kubernetes.io/ssl-redirect: "true"
```
Any HTTP request is automatically redirected to HTTPS — no insecure access possible.

---

## Complete Deployment Flow

```
1. terraform apply
   → Creates: VNet, NSGs, Log Analytics, ACR, AKS, Key Vault,
              Defender, Monitor alerts

2. docker build -t fairsplitacrq0w0x3.azurecr.io/fairsplit:latest .
   → Packages Flask app into slim Python container

3. az acr login && docker push fairsplitacrq0w0x3.azurecr.io/fairsplit:latest
   → Uploads image to ACR

4. az aks get-credentials → kubectl apply -f K8s/
   → Deploys: namespace, PVC, secrets, RBAC, network policy,
              nginx configmap, backend, frontend, HPA, ingress

5. kubectl apply -f K8s/cluster-issuer.yaml
   → cert-manager requests TLS cert from Let's Encrypt

6. App live at https://20.100.154.95.nip.io
   → HTTPS enforced, non-root containers, encrypted disk,
              security middleware active, monitoring pipeline running
```

### Kubernetes Resources Summary
| Resource | Name | Purpose |
|---|---|---|
| Namespace | `fairsplit` | Isolation boundary |
| PersistentVolumeClaim | `fairsplit-db-pvc` | Azure Disk for SQLite (1Gi) |
| Secret | `app-secret` | Flask SECRET_KEY |
| Secret | `smtp-secret` | Gmail SMTP credentials |
| ServiceAccount | `backend-sa` | Pod identity |
| Role | `backend-role` | Read-only pod access |
| RoleBinding | `backend-binding` | Links SA to Role |
| NetworkPolicy | `backend-policy` | Frontend→Backend only |
| ConfigMap | `nginx-config` | NGINX reverse proxy config |
| Deployment | `backend` | Flask app (1 replica) |
| Deployment | `frontend` | NGINX proxy (2 replicas) |
| Service | `backend` | ClusterIP :5000 |
| Service | `frontend` | LoadBalancer :80 |
| HorizontalPodAutoscaler | `backend-hpa` | Scale 2–5 pods at 70% CPU |
| Ingress | `fairsplit-ingress` | TLS routing via NGINX Ingress |
| ClusterIssuer | `letsencrypt-prod` | Let's Encrypt certificate authority |

---

## CS581 Signature Project — Coverage Checklist

### Phase 1 — Architecture Design

| Checkpoint | Status | Detail |
|---|---|---|
| Virtual Network with subnets | Covered | VNet 10.0.0.0/16, frontend 10.0.1.0/24, backend 10.0.2.0/24 |
| Public/private subnet separation | Covered | frontendpool (public) + backendpool (private, no internet) |
| AKS cluster deployed | Covered | `secure-aks-cluster` with 2 node pools |
| Load balancer configured | Covered | Azure Standard LB + NGINX Ingress Controller |
| Multi-tier network diagram | Covered | Documented in Phase 1 section |

### Phase 2 — Cluster Deployment (IaC)

| Checkpoint | Status | Detail |
|---|---|---|
| Infrastructure as Code (Terraform) | Covered | Full `main.tf` provisions all Azure resources |
| AKS cluster via Terraform | Covered | `azurerm_kubernetes_cluster` with both node pools |
| ACR via Terraform | Covered | `azurerm_container_registry` Standard tier |
| Log Analytics via Terraform | Covered | `azurerm_log_analytics_workspace` |
| Microsoft Defender via Terraform | Covered | `azurerm_security_center_subscription_pricing` |
| Monitor alert rules via Terraform | Covered | 4 alert rules: brute-force, scanning, IDOR, log-tamper |

### Phase 3 — Multi-Tier Application Deployment

| Checkpoint | Status | Detail |
|---|---|---|
| Frontend tier | Covered | NGINX reverse proxy pod on frontendpool |
| Backend tier | Covered | Flask + Gunicorn pod on backendpool |
| Database tier | Partial | SQLite on Azure Disk PVC — not PostgreSQL as originally planned |
| Kubernetes Deployment manifests | Covered | backend-deployment.yaml, frontend-deployment.yaml |
| Kubernetes Services | Covered | ClusterIP for backend, LoadBalancer for frontend |
| Persistent storage | Covered | Azure Disk PVC (1Gi, managed-csi) |
| Microservices architecture | Not Covered | Monolith Flask app — justified as monolith-first approach |

### Phase 4 — IAM, RBAC, Least Privilege

| Checkpoint | Status | Detail |
|---|---|---|
| Managed Identity | Covered | SystemAssigned on AKS cluster |
| AcrPull role assignment | Covered | kubelet identity to ACR (no passwords) |
| Kubernetes ServiceAccount | Covered | `backend-sa` in fairsplit namespace |
| Kubernetes Role + RoleBinding | Covered | `backend-role` — read-only on Secrets |
| JWT Authentication | Not Covered | Using Flask session cookies instead of JWT tokens |

### Phase 5 — Network Security

| Checkpoint | Status | Detail |
|---|---|---|
| NSG on frontend subnet | Covered | Allow TCP 80, 443 from Internet only |
| NSG on backend subnet | Covered | Allow TCP 5000 from VNet only (10.0.0.0/16) |
| Kubernetes NetworkPolicy | Covered | backend allows only frontend pods on :5000 |
| TLS/HTTPS enforced | Covered | cert-manager + Let's Encrypt + HTTP to HTTPS redirect |
| NGINX Ingress with TLS termination | Covered | Valid certificate via nip.io domain |

### Phase 6 — Data Security

| Checkpoint | Status | Detail |
|---|---|---|
| Encryption at rest | Covered | Azure Disk encryption + AKS etcd encrypted |
| Encryption in transit | Covered | TLS end-to-end via NGINX Ingress |
| Kubernetes Secrets | Covered | `app-secret`, `smtp-secret` injected as env vars |
| Azure Key Vault provisioned | Covered | `fairsplit-kv-q0w0x3` in Terraform |
| Key Vault CSI driver integration | Not Covered | Secrets are env vars — noted as production improvement |
| Secret rotation | Not Covered | Secrets are static — noted as future improvement |
| Password hashing | Covered | Bcrypt with cost factor 12 |

### Phase 7 — Container Security

| Checkpoint | Status | Detail |
|---|---|---|
| Minimal base image | Covered | `python:3.11-slim` — no compiler or shell utilities |
| Non-root user | Covered | `appuser` UID 1000, `runAsNonRoot: true` |
| No privilege escalation | Covered | `allowPrivilegeEscalation: false` |
| Registry vulnerability scanning | Covered | ACR Standard tier — scans on every push |
| No secrets in image | Covered | All secrets injected at runtime via Kubernetes Secrets |
| Read-only container filesystem | Not Covered | Filesystem is writable — mitigated by non-root user |
| Pod Security Standards | Not Covered | No namespace-level securityContext policy |

### Phase 8 — Monitoring and Logging

| Checkpoint | Status | Detail |
|---|---|---|
| Centralized logging (Log Analytics) | Covered | OMS agent ships all pod logs |
| Structured JSON security events | Covered | `log_security_event()` in security.py |
| kube-audit logs | Covered | AKS Diagnostic Settings to Log Analytics |
| Microsoft Defender for Containers | Covered | Runtime threat detection + kubectl exec alerts |
| Azure Monitor alert rules | Covered | 4 Scheduled Query Alert rules |
| Email notifications via Action Group | Covered | pariksha.rajput2912@gmail.com |
| Azure Monitor Workbook / Dashboard | Not Covered | No custom workbook created |

### Phase 9 — Threat Simulation and Mitigation

| Checkpoint | Status | Detail |
|---|---|---|
| Scenario 1: Brute Force | Covered | 3 attempts, IP blocked, BRUTE_FORCE_DETECTED, email alert |
| Scenario 2: IDOR | Covered | 403 Forbidden, IDOR_ATTEMPT_DETECTED, email alert |
| Scenario 3: Log Deletion / Tampering | Covered | /system/logs DELETE blocked, attacker identity logged, email alert |
| Scenario 4: Route Scanning | Covered | 10 unauthenticated hits, SCANNING_DETECTED, email alert |
| Log Analytics queries for all scenarios | Covered | KQL queries documented for all 4 events |
| Azure Defender alert (kubectl exec) | Covered | Defender flags "Command in container" |

### Application Features

| Checkpoint | Status | Detail |
|---|---|---|
| User signup / login | Covered | Bcrypt hashing, session-based auth |
| Expense creation and splitting | Covered | Equal and custom split modes |
| Balance calculation | Covered | Per-user balance view |
| Payment / settlement system | Covered | Wallet debit/credit on settlement |
| Notification service | Covered | In-app feed + Gmail SMTP email alerts |
| Smart debt simplification | Covered | Greedy heap algorithm O(N log N) |
| Financial insights dashboard | Covered | Spending charts, category breakdown |
| Wallet system | Covered | Balance, top-up, transaction history |

---

### Overall Summary

| Phase | Covered | Not Covered | Total |
|---|---|---|---|
| Phase 1 — Architecture | 5 | 0 | 5 |
| Phase 2 — IaC | 6 | 0 | 6 |
| Phase 3 — App Deployment | 6 | 1 | 7 |
| Phase 4 — IAM / RBAC | 4 | 1 | 5 |
| Phase 5 — Network Security | 5 | 0 | 5 |
| Phase 6 — Data Security | 5 | 2 | 7 |
| Phase 7 — Container Security | 5 | 2 | 7 |
| Phase 8 — Monitoring | 6 | 1 | 7 |
| Phase 9 — Threat Simulation | 6 | 0 | 6 |
| Application Features | 8 | 0 | 8 |
| **Total** | **56** | **7** | **63** |

### The 7 Gaps and Justification

| Gap | Justification |
|---|---|
| PostgreSQL (using SQLite) | SQLite on PVC is sufficient for CS581 demo scale; monolith-first approach documented |
| Microservices architecture | Intentional monolith-first design; microservice split documented as future phase |
| JWT authentication | Flask sessions are a valid auth mechanism; JWT noted as production enhancement |
| Key Vault CSI driver | Key Vault is provisioned; env var injection is acceptable for demo; CSI driver noted as production improvement |
| Secret rotation | Static secrets acceptable for CS581; rotation policy noted as future improvement |
| Read-only container filesystem | Non-root user + no privilege escalation provides equivalent protection for demo |
| Azure Monitor Workbook | Log Analytics queries and alert rules fully cover monitoring requirements |
