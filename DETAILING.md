# Spiltwise — Project Detailing

## Overview

Spiltwise is a web-based expense splitting and payment tracking application built with Flask. It allows multiple users to share expenses, track who owes whom, settle debts, and manage a personal wallet. The app uses graph-based debt simplification to minimize the number of transactions needed to settle all balances within a group.

---

## Tech Stack

| Layer        | Technology                                          |
|--------------|-----------------------------------------------------|
| Backend      | Python, Flask 3.0                                   |
| Database     | SQLite (local) / Azure PostgreSQL Flexible Server   |
| ORM          | Flask-SQLAlchemy 3.1                                |
| Auth         | Flask-Bcrypt (password hashing), Flask sessions     |
| Frontend     | Jinja2 templates, HTML, CSS, vanilla JavaScript     |
| Config       | python-dotenv (.env file)                           |
| Container    | Docker (python:3.11-slim, non-root user)            |
| Orchestration| Azure Kubernetes Service (AKS)                      |
| Registry     | Azure Container Registry (ACR)                      |
| IaC          | Terraform (azurerm provider ~> 3.80)                |
| Monitoring   | Azure Log Analytics + Microsoft Defender            |
| Alerting     | Azure Monitor Scheduled Query Alerts + Action Group |
| Secrets      | Azure Key Vault                                     |

---

## Database Schema

### User
| Column       | Type    | Description                          |
|--------------|---------|--------------------------------------|
| id           | Integer | Primary key                          |
| name         | String  | Display name                         |
| email        | String  | Unique login email                   |
| password     | String  | Bcrypt hashed password               |
| avatar_color | String  | Hex color auto-assigned from email   |
| created_at   | DateTime| Account creation timestamp           |

### Expense
| Column      | Type    | Description                          |
|-------------|---------|--------------------------------------|
| id          | Integer | Primary key                          |
| description | String  | What the expense was for             |
| amount      | Float   | Total expense amount                 |
| category    | String  | Food, Travel, Rent, etc.             |
| split_type  | String  | equal or custom                      |
| paid_by     | FK      | User who paid upfront                |
| created_at  | DateTime| When expense was created             |

### ExpenseSplit
| Column     | Type    | Description                           |
|------------|---------|---------------------------------------|
| id         | Integer | Primary key                           |
| expense_id | FK      | Related expense                       |
| user_id    | FK      | User this split belongs to            |
| amount     | Float   | Amount this user owes for the expense |

### Payment
| Column     | Type    | Description                           |
|------------|---------|---------------------------------------|
| id         | Integer | Primary key                           |
| from_user  | FK      | Sender (null for wallet top-ups)      |
| to_user    | FK      | Receiver                              |
| amount     | Float   | Payment amount                        |
| note       | String  | Optional payment note                 |
| status     | String  | completed                             |
| created_at | DateTime| When payment was made                 |

### Wallet
| Column  | Type    | Description                            |
|---------|---------|----------------------------------------|
| id      | Integer | Primary key                            |
| user_id | FK      | One-to-one with User                   |
| balance | Float   | Current wallet balance                 |

### Junction Tables
- **expense_members** — many-to-many between Expense and User (who is part of the expense)
- **expense_settled** — many-to-many between Expense and User (who has settled their share)

---

## Features

### 1. Authentication
- User signup with name, email, and password
- Passwords hashed with Bcrypt before storage
- Session-based login/logout
- All routes protected with a custom `@login_required` decorator
- Auto-assigned avatar color based on email hash

### 2. Dashboard
- Financial snapshot showing:
  - Total amount owed to you
  - Total amount you owe others
  - Net balance (positive or negative)
  - Wallet balance
- Monthly spending bar chart (last 6 months)
- Spending breakdown by category
- 5 most recent expenses
- Top 3 spending partners
- Quick balance summary with all group members

### 3. Expense Management
- Add an expense with description, amount, category, paid-by, and members
- Two split modes:
  - **Equal split** — amount divided equally among all members
  - **Custom split** — manually enter each person's share
- Live member search by name or email (via `/api/users/search`)
- Expense list showing all expenses you are part of, sorted by date
- One-click settle button per expense (marks your share as settled)

### 4. Balances
- **Raw balances** — net amount owed between you and each person, factoring in all expenses and payments
- **Simplified Debts** — graph-optimized view showing the minimum transactions needed to settle everything (see algorithm below)

### 5. Payments
- Send a payment to any user directly from the Balances page
- Payment modal pre-fills the amount you owe
- Payment history showing all sent and received transactions
- Type shown as: Sent, Received, or Top-up
- Wallet balance is automatically updated on each payment

### 6. Wallet
- Each user has a wallet with a balance
- Top up wallet with preset amounts ($100, $200, $500, $1000) or custom amount
- Full transaction history with date, type, and counterparty
- Wallet balance deducted/credited automatically when payments are made

---

## Workflow

### New User Flow
1. User visits `/` → sees landing page
2. Signs up at `/signup` → account + wallet created
3. Redirected to `/dashboard`

### Adding an Expense
1. Click "Add Expense" from Dashboard or Expenses page
2. Enter description, amount, category
3. Select who paid
4. Search and add members
5. Choose equal or custom split
6. Submit → expense saved, splits recorded per member

### Settling a Debt
**Option A — Settle individual expense:**
- Go to Expenses page
- Click "Settle" on an expense row
- Your share is marked as settled for that expense

**Option B — Send a direct payment:**
- Go to Balances page
- Click "Pay Now" next to a person you owe
- Enter amount and note in the modal
- Submit → payment recorded, wallet balances updated

### Viewing Balances
1. Go to `/balances`
2. See Simplified Debts (graph-optimized, minimum transactions)
3. See All Balances table (raw net per person)
4. Use "Pay Now" or "Request" buttons inline

---

## Graph-Based Debt Simplification Algorithm

### Problem
In a group of N people, naive debt tracking leads to O(N^2) transactions. The goal is to reduce this to the minimum number of transactions.

### Example
```
Without simplification:
  A owes B $10
  B owes C $10
  = 2 transactions

With simplification:
  A pays C $10 directly
  B is automatically cleared
  = 1 transaction
```

### Algorithm (Greedy Min/Max Heap)
1. Compute the **net balance** for every user globally across all expenses and payments
2. Separate users into:
   - **Debtors** (net balance < 0) — pushed into a min-heap
   - **Creditors** (net balance > 0) — pushed into a max-heap
3. Repeatedly:
   - Pop the largest debtor and largest creditor
   - The debtor pays the creditor `min(debt, credit)`
   - Push back any remaining balance
4. Stop when all balances are settled
5. Filter the resulting transactions to show only those involving the current user

### Complexity
- Time: O(N log N) — heap operations
- Space: O(N) — one entry per user

This is the classic **"Optimal Account Balancing"** problem, a well-known graph/greedy algorithm used in real-world fintech applications.

---

## API Endpoints

| Method | Route                          | Description                        |
|--------|--------------------------------|------------------------------------|
| GET    | `/`                            | Landing page or redirect to dashboard |
| GET/POST | `/signup`                   | User registration                  |
| GET/POST | `/login`                    | User login                         |
| GET    | `/logout`                      | Clear session and logout           |
| GET    | `/dashboard`                   | Main dashboard                     |
| GET    | `/expenses`                    | List all expenses                  |
| GET/POST | `/expenses/add`             | Add a new expense                  |
| POST   | `/expenses/<id>/settle`        | Settle your share of an expense    |
| GET    | `/balances`                    | View balances and simplified debts |
| GET    | `/payments`                    | Payment history                    |
| POST   | `/payments/send`               | Send a payment to a user           |
| GET    | `/wallet`                      | Wallet page with transaction history |
| POST   | `/wallet/topup`                | Add money to wallet                |
| GET    | `/api/users/search?q=`         | Search users by name or email      |

---

## Configuration (.env)

```
SECRET_KEY=your_secret_key_here

# Local development (SQLite)
DATABASE_URL=sqlite:///spiltwise.db

# Azure production (PostgreSQL Flexible Server)
# DATABASE_URL=postgresql://splitwiseadmin:<password>@<postgresql_host>:5432/spiltwise
```

---

## Running the Project

### Local
```bash
cd spiltwise
pip install -r requirements.txt
python app.py
```
App runs at `http://localhost:5000`. The SQLite database file (`spiltwise.db`) is created automatically on first run.

### Azure Deployment
- Set `DATABASE_URL` environment variable to your Azure PostgreSQL Flexible Server connection string
- Use Gunicorn as the WSGI server instead of Flask's dev server
- No code changes required — SQLAlchemy handles both SQLite and PostgreSQL

---

## Architecture — Monolith with Microservice Boundaries

Spiltwise is currently built as a **monolithic Flask application**. All logic lives in `app.py` and shares a single SQLite/PostgreSQL database. However, the codebase is logically structured around clear service boundaries that map directly to independent microservices if the app were to be decomposed for scale.

### Current Architecture
```
Client (Browser)
      |
   Flask App (app.py)
      |
   SQLite / Azure PostgreSQL Flexible Server (single DB)
```

### Logical Service Boundaries (Potential Microservices)

| Service              | Responsibility                                                                 | Current location in code                                      |
|----------------------|--------------------------------------------------------------------------------|---------------------------------------------------------------|
| **Auth Service**     | Signup, login, logout, session management, password hashing                    | `signup`, `login`, `logout` routes + `User` model            |
| **User Service**     | User profile, avatar color assignment, user search API                         | `User` model + `/api/users/search`                            |
| **Expense Service**  | Create expenses, manage splits (equal/custom), settle individual shares        | `Expense`, `ExpenseSplit` models + `add_expense`, `settle_expense` routes |
| **Balance Service**  | Compute per-user balances, global net balances, graph-based debt simplification | `_compute_balances`, `_compute_global_balances`, `_simplify_debts` |
| **Payment Service**  | Send payments between users, payment history, wallet credit/debit on payment   | `Payment` model + `send_payment`, `payments` routes           |
| **Wallet Service**   | Wallet balance management, top-up, transaction history                         | `Wallet` model + `wallet`, `topup_wallet` routes              |
| **Analytics Service**| Monthly spending trends, category breakdown, top spending partners             | `_monthly_spending`, `_category_breakdown`, `_top_partners`   |

### How Microservice Decomposition Would Work

```
Client (Browser / Mobile)
           |
       API Gateway
    /    |    \    \      \        \
 Auth  Expense Balance Payment  Wallet  Analytics
  DB     DB      DB      DB       DB       DB
```

- Each service owns its own database table(s)
- Services communicate via REST APIs or a message queue
- The Balance Service subscribes to events from Expense and Payment services to recompute balances
- Auth Service issues JWT tokens; all other services validate them independently

---

## Azure Infrastructure (Terraform — main.tf)

### Resource Overview

| Terraform Resource | Azure Service | Purpose |
|---|---|---|
| `azurerm_resource_group` | Resource Group | Container for all resources |
| `azurerm_virtual_network` | VNet | Isolated network (VPC equivalent) |
| `azurerm_subnet` (x2) | Subnets | frontend-subnet (public), backend-subnet (private) |
| `azurerm_network_security_group` (x2) | NSGs | frontend allows HTTP/HTTPS; backend allows VNet only |
| `azurerm_subnet_network_security_group_association` (x2) | NSG-Subnet link | Attach NSGs to subnets |
| `azurerm_log_analytics_workspace` | Log Analytics | Central log store (CloudWatch equivalent) |
| `azurerm_container_registry` | ACR | Docker image registry (ECR equivalent) |
| `azurerm_kubernetes_cluster` | AKS | Kubernetes cluster with frontend node pool |
| `azurerm_kubernetes_cluster_node_pool` | AKS Node Pool | Backend node pool in private subnet |
| `azurerm_role_assignment` (AcrPull) | RBAC | AKS kubelet identity can pull images from ACR |
| `azurerm_key_vault` | Key Vault | Secrets storage (Secrets Manager equivalent) |
| `azurerm_postgresql_flexible_server` | Azure PostgreSQL | Managed relational DB (RDS equivalent) |
| `azurerm_postgresql_flexible_server_firewall_rule` | DB Firewall | Allow AKS VNet to reach PostgreSQL |
| `azurerm_security_center_subscription_pricing` | Microsoft Defender | Container threat detection (GuardDuty equivalent) |
| `azurerm_monitor_diagnostic_setting` | Diagnostic Settings | Stream kube-audit logs to Log Analytics (CloudTrail equivalent) |
| `azurerm_monitor_action_group` | Action Group | Email alert target (SNS Topic equivalent) |
| `azurerm_monitor_scheduled_query_rules_alert_v2` (x2) | Monitor Alerts | Brute force + scanning detection (CloudWatch Alarms equivalent) |

### AKS Cluster Configuration

```
AKS Cluster: secure-aks-cluster
├── Identity: SystemAssigned (Managed Identity)
├── RBAC: enabled
├── Network plugin: azure (Azure CNI)
├── Load balancer SKU: standard
├── Kubernetes version: 1.29
├── OMS agent → Log Analytics (container log forwarding)
├── Microsoft Defender → Log Analytics (threat detection)
├── frontend node pool → frontend-subnet (public)
└── backend node pool  → backend-subnet (private)
```

### Network Security Design

```
Internet
   |
frontend-subnet (10.0.1.0/24)
   │  NSG: Allow HTTP:80, HTTPS:443 inbound
   │  AKS Frontend Node Pool + Azure Load Balancer
   |
backend-subnet (10.0.2.0/24)
   │  NSG: Allow VNet (10.0.0.0/16) only — Deny Internet
   │  AKS Backend Node Pool
   |
Azure PostgreSQL Flexible Server
   └── Firewall: Allow 10.0.0.0–10.0.255.255 only
```

### AWS → Azure Service Mapping

| AWS Service | Azure Equivalent | Where in main.tf |
|---|---|---|
| VPC | Azure Virtual Network | `azurerm_virtual_network` |
| Security Groups / NACLs | Network Security Groups | `azurerm_network_security_group` |
| EKS | Azure Kubernetes Service | `azurerm_kubernetes_cluster` |
| ECR | Azure Container Registry | `azurerm_container_registry` |
| RDS PostgreSQL | PostgreSQL Flexible Server | `azurerm_postgresql_flexible_server` |
| Secrets Manager | Azure Key Vault | `azurerm_key_vault` |
| IRSA | AKS Kubelet Managed Identity + AcrPull role | `azurerm_role_assignment` |
| CloudWatch Logs | Log Analytics Workspace | `azurerm_log_analytics_workspace` |
| CloudTrail | AKS Diagnostic Settings (kube-audit) | `azurerm_monitor_diagnostic_setting` |
| GuardDuty | Microsoft Defender for Containers | `azurerm_security_center_subscription_pricing` |
| SNS Topic | Azure Monitor Action Group | `azurerm_monitor_action_group` |
| CloudWatch Alarms | Scheduled Query Alert Rules | `azurerm_monitor_scheduled_query_rules_alert_v2` |

---

## Azure Deployment Steps

### Prerequisites
```bash
az --version        # Azure CLI
terraform --version # Terraform >= 1.5
docker --version    # Docker
kubectl version     # kubectl

az login
az account set --subscription "<your-subscription-id>"
```

### Step 1 — Terraform Init & Apply
```bash
cd splitwise
terraform init

export TF_VAR_db_password="YourStrongP@ssword123!"
terraform plan
terraform apply
```

### Step 2 — Build & Push Docker Image

`Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
```

```bash
ACR_SERVER=$(terraform output -raw acr_login_server)
az acr login --name $ACR_SERVER
docker build -t $ACR_SERVER/splitwise:latest .
docker push $ACR_SERVER/splitwise:latest
```

### Step 3 — Connect kubectl to AKS
```bash
AKS_NAME=$(terraform output -raw aks_cluster_name)
az aks get-credentials --resource-group secure-aks-rg --name $AKS_NAME
kubectl get nodes
```

### Step 4 — Store Secrets in Key Vault
```bash
az keyvault secret set --vault-name splitwise-kv-<suffix> \
  --name db-password --value "YourStrongP@ssword123!"

az keyvault secret set --vault-name splitwise-kv-<suffix> \
  --name secret-key --value "your_flask_secret_key_here"
```

### Step 5 — Deploy to Kubernetes

`k8s-deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: splitwise
spec:
  replicas: 2
  selector:
    matchLabels:
      app: splitwise
  template:
    metadata:
      labels:
        app: splitwise
    spec:
      containers:
      - name: splitwise
        image: <acr_login_server>/splitwise:latest
        ports:
        - containerPort: 5000
        env:
        - name: DATABASE_URL
          value: "postgresql://splitwiseadmin:<password>@<postgresql_host>:5432/spiltwise"
        - name: SECRET_KEY
          value: "<your_secret_key>"
        securityContext:
          runAsNonRoot: true
          allowPrivilegeEscalation: false
---
apiVersion: v1
kind: Service
metadata:
  name: splitwise-svc
spec:
  type: LoadBalancer
  selector:
    app: splitwise
  ports:
  - port: 80
    targetPort: 5000
```

```bash
kubectl apply -f k8s-deployment.yaml
kubectl get svc splitwise-svc   # wait ~2 min for EXTERNAL-IP
```

### Step 6 — Create the PostgreSQL Database
```bash
DB_HOST=$(terraform output -raw postgresql_host)

psql "host=$DB_HOST port=5432 dbname=postgres \
  user=splitwiseadmin password=<password> sslmode=require"

# Inside psql:
CREATE DATABASE spiltwise;
\q
# SQLAlchemy creates all tables on first app startup
```

### Step 7 — Verify Monitoring
```bash
# Query Log Analytics for container logs
az monitor log-analytics query \
  --workspace <workspace-id> \
  --analytics-query "ContainerLog | take 10"

# Microsoft Defender — Azure Portal:
# Defender for Cloud → Workload Protections → Containers
```

---

## CS581 Signature Project — Phase Mapping (Azure)

| Phase | Requirement | AWS (original) | Azure (implemented) |
|-------|-------------|----------------|---------------------|
| Phase 1 | Architecture Design (network + cluster + load balancer) | VPC + EKS + ELB | VNet + AKS + Azure Standard Load Balancer |
| Phase 2 | Cluster Deployment (IaC) | eksctl / Terraform | Terraform `azurerm_kubernetes_cluster` |
| Phase 3 | Multi-tier app (Frontend + Backend + DB) | Flask + RDS PostgreSQL | Flask on AKS + Azure PostgreSQL Flexible Server |
| Phase 4 | IAM roles, RBAC, IRSA | IAM + EKS RBAC + IRSA | AKS SystemAssigned Managed Identity + AcrPull RBAC role |
| Phase 5 | Network Security (SGs, NACLs, Network Policies) | VPC SGs + NACLs | NSGs on frontend/backend subnets, DB firewall rule |
| Phase 6 | Data Security (encryption, secrets) | RDS encryption + Secrets Manager | PostgreSQL (encrypted at rest by default) + Azure Key Vault |
| Phase 7 | Container Security (non-root, minimal image, registry scan) | ECR + Trivy scan | ACR Standard (built-in vulnerability scanning) + non-root Dockerfile |
| Phase 8 | Monitoring & Logging | CloudWatch + GuardDuty | Log Analytics + Microsoft Defender for Containers + kube-audit diagnostic settings |
| Phase 9 | Threat Simulation & Mitigation | CloudWatch Alarms + EventBridge + SNS | Azure Monitor Scheduled Query Alerts + Action Group (email) |

---

## Security Implementation

### File: `security.py`

All application-level security detection logic lives in `security.py`.

| Function | Purpose |
|---|---|
| `log_security_event()` | Logs structured JSON to stdout → captured by AKS OMS agent → flows to Log Analytics → triggers Azure Monitor alerts |
| `record_failed_login(ip, email)` | Tracks failed logins per IP. Triggers `BRUTE_FORCE_DETECTED` after 5 failures in 5 minutes |
| `is_ip_blocked(ip)` | Returns True if IP has exceeded login failure threshold |
| `clear_failed_logins(ip)` | Resets failed login count on successful login |
| `record_unauthorized_access(ip, route, method)` | Logs unauthorized route access. Triggers `SCANNING_DETECTED` after 10 hits in 1 minute |
| `check_suspicious_payment(user_id, amount, to_user)` | Blocks and logs payments exceeding $5,000 |

### Key Change from AWS Version
The original `security.py` used `boto3` (AWS SDK) to call SNS directly from the app. In the Azure version:
- `boto3` and SNS calls have been **removed**
- The app logs structured JSON to **stdout only**
- AKS picks up stdout via the **OMS agent** and ships it to **Log Analytics**
- **Azure Monitor Scheduled Query Alert rules** (defined in `main.tf`) query Log Analytics every 1–5 minutes and fire email alerts via the Action Group when `BRUTE_FORCE_DETECTED` or `SCANNING_DETECTED` appears

This is cleaner: the app has zero cloud-SDK dependency; alerting is entirely infrastructure-managed.

### Integration Points in `app.py`

| Route / Function | Security Check Added |
|---|---|
| `login_required` decorator | Calls `record_unauthorized_access()` on every unauthenticated request |
| `login()` route | Calls `is_ip_blocked()` before processing, `record_failed_login()` on failure, `clear_failed_logins()` on success |
| `send_payment()` route | Calls `check_suspicious_payment()` before processing the transaction |

### Environment Variables Required

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing key |
| `DATABASE_URL` | Azure PostgreSQL connection string |

> SNS_TOPIC_ARN and AWS_DEFAULT_REGION are no longer required — alerting is handled entirely by Azure Monitor.

### Log Format (JSON)

Every security event is logged as structured JSON to stdout:
```json
{
  "timestamp": "2025-04-12T10:30:00Z",
  "service": "spiltwise",
  "event_type": "BRUTE_FORCE_DETECTED",
  "severity": "CRITICAL",
  "details": {
    "ip": "203.0.113.45",
    "email": "victim@example.com",
    "attempts_in_window": 6,
    "action": "IP blocked from further login attempts"
  }
}
```

---

## Security Breach Scenarios (Phase 9)

### Scenario 1 — Brute Force Attack on Login

**What it is:** An attacker repeatedly tries different passwords on the `/login` endpoint to gain unauthorized account access.

**How it is simulated:**
- Script sends 5+ failed login requests to `/login` from the same IP in under 5 minutes

**How it is detected:**
- Flask security middleware tracks failed login attempts per IP
- After 5 failures within 5 minutes, threshold is exceeded

**What happens (Azure):**
- Event `BRUTE_FORCE_DETECTED` logged as structured JSON → stdout → Log Analytics
- Azure Monitor Scheduled Query Alert (`brute-force-detection` rule, 5-min window) fires
- Action Group sends email alert to configured address

**Log entry example:**
```json
{
  "timestamp": "2025-04-12T10:30:00Z",
  "service": "spiltwise",
  "event_type": "BRUTE_FORCE_DETECTED",
  "severity": "CRITICAL",
  "details": {
    "ip": "203.0.113.45",
    "email": "victim@example.com",
    "attempts_in_window": 6
  }
}
```

---

### Scenario 2 — Unauthorized Access Attempt

**What it is:** An unauthenticated user or bot tries to directly access protected routes like `/dashboard`, `/wallet`, `/expenses` without logging in.

**How it is simulated:**
- Send HTTP requests to protected routes without a valid session cookie

**How it is detected:**
- Flask `@login_required` decorator intercepts the request
- Security middleware logs the attempt with IP and route
- If the same IP hits 10+ protected routes within a minute, route scanning is flagged

**What happens (Azure):**
- Event `UNAUTHORIZED_ACCESS` logged to Log Analytics
- If scanning threshold hit, `SCANNING_DETECTED` fires
- Azure Monitor Scheduled Query Alert (`scanning-detection` rule, 1-min window) fires email via Action Group

**Log entry example:**
```json
{
  "timestamp": "2025-04-12T10:31:00Z",
  "service": "spiltwise",
  "event_type": "UNAUTHORIZED_ACCESS",
  "severity": "WARNING",
  "details": {
    "ip": "203.0.113.45",
    "route": "/wallet",
    "method": "GET"
  }
}
```

---

### Scenario 3 — Log Deletion / Audit Tampering (Azure-Level)

**What it is:** An attacker with stolen credentials attempts to delete Log Analytics data or disable diagnostic settings to cover their tracks.

**How it is simulated:**
```bash
# Disable AKS diagnostic settings via Azure CLI
az monitor diagnostic-settings delete \
  --name aks-diagnostics \
  --resource <aks-resource-id>

# Attempt to delete Log Analytics workspace
az monitor log-analytics workspace delete \
  --resource-group secure-aks-rg \
  --workspace-name aks-log-workspace
```

**How it is detected:**
- **Microsoft Defender for Cloud** raises an alert for suspicious management-plane activity
- **Azure Activity Log** records every ARM API call permanently (equivalent to CloudTrail)
- Azure Monitor can be configured to alert on `microsoft.operationalinsights/workspaces/delete` events

**Azure Defender Alerts triggered:**

| Alert | Trigger |
|-------|---------|
| `Suspicious management activity` | Diagnostic settings deleted |
| `Privileged container detected` | Unauthorized kubectl exec into privileged pod |
| `Unusual deletion activity` | Log workspace or diagnostic setting removed |

**Why this is powerful:** The Azure Activity Log is immutable from within the subscription — deleting it requires elevated portal access. With Azure Policy + Resource Locks (`CanNotDelete`) on the Log Analytics workspace, deletion is blocked entirely.

---

### Scenario 4 — Azure Monitor + Action Group Alert Pipeline (Infrastructure-Level)

**What it is:** Any suspicious app-level event captured in Log Analytics automatically triggers an email alert via Azure Monitor — completely independent of the Flask app. Works even if the app is down or compromised.

**How it works:**
```
App logs JSON to stdout
       |
  AKS OMS Agent
       |
  Log Analytics Workspace
       |
  Azure Monitor Scheduled Query Alert
  (queries ContainerLog every 1–5 min)
       |
  Action Group
      / \
  Email  (extensible to SMS, webhook, Teams)
```

**Alert rules wired in main.tf:**

| Rule | Query | Window | Severity |
|---|---|---|---|
| `brute-force-detection` | `ContainerLog \| where LogEntry contains "BRUTE_FORCE_DETECTED"` | PT5M | 0 (Critical) |
| `scanning-detection` | `ContainerLog \| where LogEntry contains "SCANNING_DETECTED"` | PT1M | 0 (Critical) |

**Suspicious events covered:**

| Event | Trigger Condition |
|-------|-------------------|
| `BRUTE_FORCE_DETECTED` | 5+ failed logins from same IP within 5 minutes |
| `SCANNING_DETECTED` | 10+ unauthorized route hits from same IP in 1 minute |
| `SUSPICIOUS_TRANSACTION` | Payment amount exceeds $5,000 |

---

## Security Notification Flow (Azure)

```
Security Event Occurs (app or Azure level)
               |
  Flask middleware / Microsoft Defender detects it
               |
    Structured JSON log written to stdout
               |
       AKS OMS Agent ships to Log Analytics
               |
    Azure Monitor Scheduled Query Alert
    (matches CRITICAL events every 1–5 min)
               |
         Action Group fires
          /              \
    Email Alert        (extensible: SMS, Teams, Webhook)
```

---

## Deployment Status & Next Steps

### What's Done

| Item | Status |
|---|---|
| `app.py` — Flask application | Complete |
| `security.py` — Azure-native security middleware (boto3/SNS removed) | Complete |
| `main.tf` — Full Azure Terraform infrastructure | Complete |
| `DETAILING.md` — Documentation with Azure phase mapping | Complete |
| HTML templates | Complete |

### What's Missing (Blocking Deployment)

Three files do not exist yet and are required before anything can deploy:

| File | Status | Why it's blocking |
|---|---|---|
| `Dockerfile` | Missing | Can't build/push image to ACR without it |
| `k8s-deployment.yaml` | Missing | Can't deploy to AKS without it |
| `requirements.txt` | Incomplete — missing `gunicorn`, `psycopg2-binary` | Docker build will fail — no WSGI server, no PostgreSQL driver |

---

### Ordered Next Steps

#### Step 1 — Fix `requirements.txt`
Add `gunicorn` and `psycopg2-binary`. Without these the Docker image can't run on AKS or connect to Azure PostgreSQL.

#### Step 2 — Create `Dockerfile`
Non-root user, slim image, Gunicorn entrypoint. Covers **Phase 7** (container security).

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
```

#### Step 3 — Create `k8s-deployment.yaml`
Deployment + Service manifest for AKS. Covers **Phase 1** (load balancer) and **Phase 3** (multi-tier).

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: splitwise
spec:
  replicas: 2
  selector:
    matchLabels:
      app: splitwise
  template:
    metadata:
      labels:
        app: splitwise
    spec:
      containers:
      - name: splitwise
        image: <acr_login_server>/splitwise:latest
        ports:
        - containerPort: 5000
        env:
        - name: DATABASE_URL
          value: "postgresql://splitwiseadmin:<password>@<postgresql_host>:5432/spiltwise"
        - name: SECRET_KEY
          value: "<your_secret_key>"
        securityContext:
          runAsNonRoot: true
          allowPrivilegeEscalation: false
---
apiVersion: v1
kind: Service
metadata:
  name: splitwise-svc
spec:
  type: LoadBalancer
  selector:
    app: splitwise
  ports:
  - port: 80
    targetPort: 5000
```

#### Step 4 — Run Terraform
Provisions everything: AKS, ACR, PostgreSQL, Key Vault, Log Analytics, Defender, Monitor alerts.

```bash
az login
terraform init
export TF_VAR_db_password="YourStrongP@ssword123!"
terraform plan
terraform apply
```

#### Step 5 — Build & Push Docker Image to ACR

```bash
ACR_SERVER=$(terraform output -raw acr_login_server)
az acr login --name $ACR_SERVER
docker build -t $ACR_SERVER/splitwise:latest .
docker push $ACR_SERVER/splitwise:latest
```

#### Step 6 — Create PostgreSQL Database

```bash
psql "host=$(terraform output -raw postgresql_host) port=5432 \
  dbname=postgres user=splitwiseadmin password=<pw> sslmode=require"

# Inside psql:
CREATE DATABASE spiltwise;
\q
# SQLAlchemy creates all tables automatically on first app startup
```

#### Step 7 — Deploy to AKS

```bash
az aks get-credentials --resource-group secure-aks-rg \
  --name $(terraform output -raw aks_cluster_name)

kubectl apply -f k8s-deployment.yaml
kubectl get svc splitwise-svc   # wait ~2 min for EXTERNAL-IP
```

#### Step 8 — Demo Security Scenarios (Phase 9)
Once the app is live, run these to trigger and verify alerts:

| Scenario | How to trigger | What to check |
|---|---|---|
| Brute force | Hit `/login` 5+ times with wrong password | Log Analytics: `BRUTE_FORCE_DETECTED` + email alert fires |
| Route scanning | Hit `/dashboard`, `/wallet`, `/expenses` 10+ times without a session cookie | Log Analytics: `SCANNING_DETECTED` log appears |
| Suspicious transaction | Send a payment > $5,000 via the app | Log Analytics: `SUSPICIOUS_TRANSACTION` log appears |

#### Step 9 — Verify Monitoring Pipeline (Phase 8)

```bash
# Confirm logs are flowing to Log Analytics
az monitor log-analytics query \
  --workspace <workspace-id> \
  --analytics-query "ContainerLog | where LogEntry contains 'spiltwise' | take 10"
```

Azure Portal checks:
- **Defender for Cloud** → Workload Protections → Containers → verify cluster is protected
- **Monitor** → Alerts → confirm `brute-force-detection` and `scanning-detection` rules are active

---

## Project Structure

```
spiltwise/
├── app.py                  # Main Flask application
├── security.py             # Security middleware (Azure-native logging)
├── main.tf                 # Terraform — full Azure infrastructure
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (not committed)
├── .env.example            # Example env config
├── DETAILING.md            # This file
├── templates/
│   ├── base.html           # Base layout with nav
│   ├── landing.html        # Public landing page
│   ├── login.html          # Login form
│   ├── signup.html         # Signup form
│   ├── dashboard.html      # Main dashboard
│   ├── expenses.html       # Expense list
│   ├── add_expense.html    # Add expense form
│   ├── balances.html       # Balances and debt simplification
│   ├── payments.html       # Payment history
│   └── wallet.html         # Wallet management
└── static/
    ├── css/                # Stylesheets
    └── js/                 # JavaScript files
```


Added a new "Deployment Status & Next Steps" section to DETAILING.md right before the Project Structure section. It includes:

  - What's Done table — current completed items                                                                                                                                                                                                 - What's Missing table — the 3 blocking files (Dockerfile, k8s-deployment.yaml, incomplete requirements.txt)
  - Steps 1–9 in order — each with the exact commands, covering file creation → Terraform → Docker → AKS deploy → Phase 9 demo → Phase 8 monitoring verification 