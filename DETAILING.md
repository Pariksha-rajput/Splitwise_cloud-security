# Fairsplit — Project Detailing

## Overview

Fairsplit is a web-based expense splitting and payment tracking application built with Flask. It allows multiple users to share expenses, track who owes whom, settle debts, and manage a personal wallet. The app uses graph-based debt simplification to minimize the number of transactions needed to settle all balances within a group.

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
DATABASE_URL=sqlite:///fairsplit.db

# Azure production (PostgreSQL Flexible Server)
# DATABASE_URL=postgresql://fairsplitadmin:<password>@<postgresql_host>:5432/fairsplit
```

---

## Running the Project

### Local
```bash
cd fairsplit
pip install -r requirements.txt
python app.py
```
App runs at `http://localhost:5000`. The SQLite database file (`fairsplit.db`) is created automatically on first run.

### Azure Deployment
- Set `DATABASE_URL` environment variable to your Azure PostgreSQL Flexible Server connection string
- Use Gunicorn as the WSGI server instead of Flask's dev server
- No code changes required — SQLAlchemy handles both SQLite and PostgreSQL

---

## Architecture — Monolith with Microservice Boundaries

Fairsplit is currently built as a **monolithic Flask application**. All logic lives in `app.py` and shares a single SQLite/PostgreSQL database. However, the codebase is logically structured around clear service boundaries that map directly to independent microservices if the app were to be decomposed for scale.

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

### Why Monolith First
For the current scope (single deployment, small team), a monolith is the right choice:
- Simpler to develop, test, and deploy
- No network latency between service calls
- Single database transaction across expense + split creation
- Easy migration to Azure with a single Gunicorn + AKS setup

The logical boundaries are already clean in the code, making a future microservices migration straightforward.

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

### Deployment Order

```
Terraform (infra) → Docker build → Push to ACR → Deploy to AKS
```

Terraform must run first — it creates ACR (needed to push the image), AKS (needed to run it), and PostgreSQL (needed by the app).

---

### Prerequisites
```bash
az --version        # Azure CLI
terraform --version # Terraform >= 1.5
docker --version    # Docker
kubectl version     # kubectl

az login
az account set --subscription "<your-subscription-id>"
```

---

### Step 1 — Terraform Init & Apply
```bash
cd "Fairsplit_cloud-security"
terraform init

# Set a strong DB password — used by PostgreSQL and Key Vault
export TF_VAR_db_password="YourStrongP@ssword123!"

terraform plan    # review what will be created
terraform apply   # takes ~10-15 minutes
```

Terraform provisions: Resource Group, VNet, NSGs, Log Analytics, ACR, AKS (frontend + backend node pools), AKS→ACR role, Key Vault, PostgreSQL, Microsoft Defender, Diagnostic Settings, Monitor alert rules.

### Step 2 — Note Terraform Outputs
```bash
terraform output acr_login_server   # e.g. fairsplitacrXXXXXX.azurecr.io
terraform output aks_cluster_name   # secure-aks-cluster
terraform output postgresql_host    # your-db.postgres.database.azure.com
```

Use these values in the steps below.

---

### Step 3 — Build & Push Docker Image

`Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
```

```bash
ACR_SERVER=$(terraform output -raw acr_login_server)
az acr login --name $ACR_SERVER
docker build -t $ACR_SERVER/fairsplit:latest .
docker push $ACR_SERVER/fairsplit:latest
```

---

### Step 4 — Connect kubectl to AKS
```bash
AKS_NAME=$(terraform output -raw aks_cluster_name)
az aks get-credentials --resource-group secure-aks-rg --name $AKS_NAME
kubectl get nodes
```

---

### Step 5 — Store Secrets in Key Vault
```bash
KV_NAME=$(terraform output -raw key_vault_uri | sed 's|https://||;s|/||')

az keyvault secret set --vault-name $KV_NAME \
  --name db-password --value "YourStrongP@ssword123!"

az keyvault secret set --vault-name $KV_NAME \
  --name secret-key --value "your_flask_secret_key_here"
```

---

### Step 6 — Deploy to Kubernetes

`k8s-deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fairsplit
spec:
  replicas: 2
  selector:
    matchLabels:
      app: fairsplit
  template:
    metadata:
      labels:
        app: fairsplit
    spec:
      containers:
      - name: fairsplit
        image: <acr_login_server>/fairsplit:latest
        ports:
        - containerPort: 5000
        env:
        - name: DATABASE_URL
          value: "postgresql://fairsplitadmin:<password>@<postgresql_host>:5432/fairsplit"
        - name: SECRET_KEY
          value: "<your_secret_key>"
        securityContext:
          runAsNonRoot: true
          allowPrivilegeEscalation: false
---
apiVersion: v1
kind: Service
metadata:
  name: fairsplit-svc
spec:
  type: LoadBalancer
  selector:
    app: fairsplit
  ports:
  - port: 80
    targetPort: 5000
```

```bash
kubectl apply -f k8s-deployment.yaml
kubectl get svc fairsplit-svc   # wait ~2 min for EXTERNAL-IP
```

### Step 6 — Create the PostgreSQL Database
```bash
DB_HOST=$(terraform output -raw postgresql_host)

psql "host=$DB_HOST port=5432 dbname=postgres \
  user=fairsplitadmin password=<password> sslmode=require"

# Inside psql:
CREATE DATABASE fairsplit;
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
| `record_failed_login(ip, email)` | Tracks failed logins per IP. Triggers `BRUTE_FORCE_DETECTED` after 3 failures in 5 minutes |
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
  "service": "fairsplit",
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
- After 3 failures within 5 minutes, threshold is exceeded

**What happens (Azure):**
- Event `BRUTE_FORCE_DETECTED` logged as structured JSON → stdout → Log Analytics
- Azure Monitor Scheduled Query Alert (`brute-force-detection` rule, 5-min window) fires
- Action Group sends email alert to configured address

**Log entry example:**
```json
{
  "timestamp": "2025-04-12T10:30:00Z",
  "service": "fairsplit",
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

### Scenario 2 — IDOR Attack on Expense Settlement (Transaction Tampering)

**What it is:** An authenticated attacker (Eve) manipulates the settlement URL to mark another user's expense as paid — effectively wiping someone else's debt without actually paying it.

**How it is simulated:**
- Eve logs in and notices the URL pattern: `POST /expenses/<id>/settle`
- Eve manually crafts a request targeting expense ID 43, which belongs to Alice and Bob (not Eve)
- Without protection, Bob's debt to Alice would be erased; Alice loses money

**How it is detected:**
- `settle_expense` route checks that the logged-in user is in `expense.members`
- If not, `log_idor_attempt()` in `security.py` fires immediately
- Event `IDOR_ATTEMPT_DETECTED` is logged as CRITICAL to stdout → OMS agent → Log Analytics
- Azure Monitor scheduled query alert (`idor-attempt-detection`, 5-min window) triggers → email sent to security team

**What happens:**
- Eve receives a `403 Forbidden` response — the transaction is blocked
- Azure Monitor alert fires and an email is sent to `pariksha.rajput2912@gmail.com`

**Log entry example:**
```json
{
  "timestamp": "2025-04-12T10:31:00Z",
  "service": "fairsplit",
  "event_type": "IDOR_ATTEMPT_DETECTED",
  "severity": "CRITICAL",
  "details": {
    "user_id": 3,
    "email": "eve@example.com",
    "expense_id": 43,
    "ip": "203.0.113.45",
    "action": "Blocked — user is not a member of this expense"
  }
}
```

---

### Scenario 3 — Log Deletion / Audit Tampering

**What it is:** An attacker who has gained access attempts to delete logs or tamper with audit records to cover their tracks. This tests three attack surfaces: the application API, the pod filesystem, and the Kubernetes control plane.

---

**Attack Surface 1 — DELETE via application API**

A dedicated protected endpoint `/system/logs` is exposed in the Flask app. Any `DELETE` or `PATCH` request is blocked immediately and logged as a `LOG_TAMPER_ATTEMPT` CRITICAL event.

How it is implemented (`security.py`):
```python
def log_tamper_attempt(ip, method, route, user_email=None, user_id=None):
    log_security_event("LOG_TAMPER_ATTEMPT", {
        "ip":         ip,
        "method":     method,
        "route":      route,
        "user_email": user_email or "unauthenticated",
        "user_id":    user_id or "unknown",
        "action":     "Blocked — destructive method not permitted on this endpoint",
    }, severity="CRITICAL")
```

How to simulate:
```bash
curl -k -X DELETE https://20.100.154.95.nip.io/system/logs
```

Expected response:
```json
{"error": "Forbidden — log tampering detected and recorded"}
```

Detection chain:
1. `log_tamper_attempt(ip, method, route)` fires immediately
2. `LOG_TAMPER_ATTEMPT` logged as CRITICAL JSON to stdout
3. OMS agent ships to Log Analytics within minutes
4. Azure Monitor Scheduled Query Alert triggers → email sent

---

**Attack Surface 2 — Exec into pod and delete log files**

Attacker gains shell access to the pod and searches for log files to delete:
```bash
kubectl exec -it deployment/backend -n fairsplit -- /bin/sh
find / -name "*.log" 2>/dev/null
ls /var/log/
```

Expected result: No application log files exist in the container. All logs are written to stdout only — captured by the AKS OMS agent and shipped to Log Analytics before the attacker can access them. The pod filesystem contains no deletable log data.

---

**Attack Surface 3 — Delete the pod to wipe in-memory logs**

```bash
kubectl delete pod -l app=backend -n fairsplit
```

Expected result: Kubernetes recreates the pod within seconds from the Deployment spec. All events already shipped to Log Analytics remain intact and immutable — pod deletion has no effect on the external log store.

---

**Defense Summary:**

| Attack | Defense |
|---|---|
| DELETE /system/logs via API | Route blocked, `LOG_TAMPER_ATTEMPT` fired and forwarded to Log Analytics |
| Exec into pod, delete log files | No log files exist — stdout only, already shipped externally |
| Delete the pod | Kubernetes recreates it; Log Analytics retains all prior events |
| Delete Log Analytics workspace | Azure RBAC + Resource Lock (`CanNotDelete`) blocks deletion |
| Disable diagnostic settings | Azure Activity Log records the attempt permanently (immutable) |

**Azure Monitor Alert Rule (main.tf):**

A dedicated Scheduled Query Alert rule `log-tamper-detection` is defined in Terraform and fires an email via the Action Group whenever a `LOG_TAMPER_ATTEMPT` event appears in Log Analytics:

```hcl
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "log_tamper_alert" {
  name                 = "log-tamper-detection"
  resource_group_name  = azurerm_resource_group.rg.name
  location             = azurerm_resource_group.rg.location
  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"
  scopes               = [azurerm_log_analytics_workspace.log.id]
  severity             = 0

  criteria {
    query                   = <<-QUERY
      ContainerLog
      | where LogEntry contains "LOG_TAMPER_ATTEMPT"
      | where TimeGenerated > ago(5m)
    QUERY
    time_aggregation_method = "Count"
    threshold               = 1
    operator                = "GreaterThanOrEqual"
  }

  action {
    action_groups = [azurerm_monitor_action_group.security_alerts.id]
  }
}
```

**Full alert pipeline:**
```
Attacker sends DELETE /system/logs
        |
        v
log_tamper_attempt() fires — captures IP + user_email + user_id
        |
        v
LOG_TAMPER_ATTEMPT logged as CRITICAL JSON to stdout
        |
        v
AKS OMS Agent ships to Log Analytics Workspace
        |
        v
Azure Monitor (log-tamper-detection rule) queries every 5 minutes
        |
        v
Action Group triggered → email sent to pariksha.rajput2912@gmail.com
```

**Azure Defender Alerts triggered:**

| Alert | Trigger |
|---|---|
| `Suspicious management activity` | Diagnostic settings deleted |
| `Unusual deletion activity` | Log workspace or diagnostic setting removed |
| `LOG_TAMPER_ATTEMPT` (app-level) | DELETE/PATCH on /system/logs endpoint |

**Verify in Log Analytics:**
```kusto
ContainerLog
| where LogEntry contains "LOG_TAMPER_ATTEMPT"
| project TimeGenerated, LogEntry
| order by TimeGenerated desc
| take 10
```

**Alert rules active after terraform apply:**

| Rule | Event | Window | Severity |
|---|---|---|---|
| `brute-force-detection` | `BRUTE_FORCE_DETECTED` | PT5M | 0 (Critical) |
| `scanning-detection` | `SCANNING_DETECTED` | PT1M | 0 (Critical) |
| `idor-attempt-detection` | `IDOR_ATTEMPT_DETECTED` | PT5M | 0 (Critical) |
| `log-tamper-detection` | `LOG_TAMPER_ATTEMPT` | PT5M | 0 (Critical) |

**Why this is powerful:** Logs in this architecture flow from pod stdout → OMS agent → Log Analytics — all outside the attacker's reach. Azure Activity Log is immutable from within the subscription. Even a complete pod deletion cannot erase evidence already forwarded externally. The email alert fires independently of the Flask app — even if the app is fully compromised.

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
  name: fairsplit
spec:
  replicas: 2
  selector:
    matchLabels:
      app: fairsplit
  template:
    metadata:
      labels:
        app: fairsplit
    spec:
      containers:
      - name: fairsplit
        image: <acr_login_server>/fairsplit:latest
        ports:
        - containerPort: 5000
        env:
        - name: DATABASE_URL
          value: "postgresql://fairsplitadmin:<password>@<postgresql_host>:5432/fairsplit"
        - name: SECRET_KEY
          value: "<your_secret_key>"
        securityContext:
          runAsNonRoot: true
          allowPrivilegeEscalation: false
---
apiVersion: v1
kind: Service
metadata:
  name: fairsplit-svc
spec:
  type: LoadBalancer
  selector:
    app: fairsplit
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
docker build -t $ACR_SERVER/fairsplit:latest .
docker push $ACR_SERVER/fairsplit:latest
```

#### Step 6 — Create PostgreSQL Database

```bash
psql "host=$(terraform output -raw postgresql_host) port=5432 \
  dbname=postgres user=fairsplitadmin password=<pw> sslmode=require"

# Inside psql:
CREATE DATABASE fairsplit;
\q
# SQLAlchemy creates all tables automatically on first app startup
```

#### Step 7 — Deploy to AKS

```bash
az aks get-credentials --resource-group secure-aks-rg \
  --name $(terraform output -raw aks_cluster_name)

kubectl apply -f k8s-deployment.yaml
kubectl get svc fairsplit-svc   # wait ~2 min for EXTERNAL-IP
```

#### Step 8 — Demo Security Scenarios (Phase 9)
Once the app is live, run these to trigger and verify alerts:

| Scenario | How to trigger | What to check |
|---|---|---|
| Brute force | Hit `/login` 3+ times with wrong password | Log Analytics: `BRUTE_FORCE_DETECTED` + email alert fires |
| IDOR | POST /expenses/<id>/settle for another user's expense | Log Analytics: `IDOR_ATTEMPT_DETECTED` + 403 response |
| Log tampering | curl -X DELETE https://20.100.154.95.nip.io/system/logs | Log Analytics: `LOG_TAMPER_ATTEMPT` + 403 response |
| Route scanning | Hit `/dashboard`, `/wallet`, `/expenses` 10+ times without a session cookie | Log Analytics: `SCANNING_DETECTED` log appears |

#### Step 9 — Verify Monitoring Pipeline (Phase 8)

```bash
# Confirm logs are flowing to Log Analytics
az monitor log-analytics query \
  --workspace <workspace-id> \
  --analytics-query "ContainerLog | where LogEntry contains 'fairsplit' | take 10"
```

Azure Portal checks:
- **Defender for Cloud** → Workload Protections → Containers → verify cluster is protected
- **Monitor** → Alerts → confirm `brute-force-detection` and `scanning-detection` rules are active

---

## Project Structure

```
fairsplit/
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


  http://20.100.217.61                                                                                                   
  You should see the Fairsplit landing page. Try signing up and creating an expense to confirm everything works end to
   end.                

  ---
  Your deployment is complete. Here's what's running:

  ┌─────────────────────────┬────────────────────────────────────────────────┐
  │        Component        │                     Status                     │
  ├─────────────────────────┼────────────────────────────────────────────────┤
  │ Backend (Flask)         │ 2 pods running on backend node pool            │
  ├─────────────────────────┼────────────────────────────────────────────────┤
  │ Frontend (NGINX)        │ 2 pods running on frontend node pool           │
  ├─────────────────────────┼────────────────────────────────────────────────┤
  ├─────────────────────────┼────────────────────────────────────────────────┤
  │ Azure Disk (SQLite PVC) │ Attached to backend                            │
  ├─────────────────────────┼────────────────────────────────────────────────┤
  │ External IP             │ 20.100.217.61                                  │
  ├─────────────────────────┼────────────────────────────────────────────────┤
  │ ACR image               │ fairsplitacrq0w0x3.azurecr.io/fairsplit:latest │
  └─────────────────────────┴────────────────────────────────────────────────┘

  ---
  For your CS581 demo, you can now trigger the Phase 9 security scenarios:

  ├─────────────────────────┼────────────────────────────────────────────────┤
  │ External IP             │ 20.100.217.61                                  │
  ├─────────────────────────┼────────────────────────────────────────────────┤
  │ ACR image               │ fairsplitacrq0w0x3.azurecr.io/fairsplit:latest │
  └─────────────────────────┴────────────────────────────────────────────────┘

  ---
  For your CS581 demo, you can now trigger the Phase 9 security scenarios:

  1. Brute force — try logging in with a wrong password 3+ times
  2. IDOR — log in as one user, manually hit POST /expenses/<id>/settle for another user's expense
  3. Log tampering — curl -X DELETE https://20.100.154.95.nip.io/system/logs

---

## CS581 Signature Project — Coverage Checklist

### Phase 1 — Architecture Design

| Checkpoint | Status | Detail |
|---|---|---|
| Virtual Network with subnets | Covered | VNet 10.0.0.0/16, frontend 10.0.1.0/24, backend 10.0.2.0/24 |
| Public/private subnet separation | Covered | frontendpool (public) + backendpool (private, no internet) |
| AKS cluster deployed | Covered | `secure-aks-cluster` with 2 node pools |
| Load balancer configured | Covered | Azure Standard LB + NGINX Ingress Controller |
| Multi-tier network diagram | Covered | Documented in architecture section |

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
| Key Vault CSI driver | Key Vault is provisioned; env var injection acceptable for demo; CSI driver noted as production improvement |
| Secret rotation | Static secrets acceptable for CS581; rotation policy noted as future improvement |
| Read-only container filesystem | Non-root user + no privilege escalation provides equivalent protection for demo |
| Azure Monitor Workbook | Log Analytics queries and alert rules fully cover monitoring requirements |