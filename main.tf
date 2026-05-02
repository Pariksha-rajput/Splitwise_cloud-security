terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

# ── Random suffix for globally unique names ────────────────────────────────────
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# ── Variables ──────────────────────────────────────────────────────────────────

# ── Resource Group ─────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "rg" {
  name     = "secure-aks-rg"
  location = "Norway East"
}

# ── VNet (VPC equivalent) ──────────────────────────────────────────────────────
resource "azurerm_virtual_network" "vnet" {
  name                = "secure-vnet"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.0.0.0/16"]
}

# ── Subnets ────────────────────────────────────────────────────────────────────
resource "azurerm_subnet" "public_subnet" {
  name                 = "frontend-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_subnet" "private_subnet" {
  name                 = "backend-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.2.0/24"]
}

# ── NSG 1: Frontend — allows HTTP inbound (Phase 5) ───────────────────────────
resource "azurerm_network_security_group" "public_nsg" {
  name                = "frontend-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  security_rule {
    name                       = "Allow-HTTP"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = "*"
    destination_port_range     = "80"
    destination_address_prefix = "*"
    source_port_range          = "*"
  }

  security_rule {
    name                       = "Allow-HTTPS"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = "*"
    destination_port_range     = "443"
    destination_address_prefix = "*"
    source_port_range          = "*"
  }
}

# ── NSG 2: Backend — private, VNet-only (Phase 5) ─────────────────────────────
resource "azurerm_network_security_group" "private_nsg" {
  name                = "backend-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  security_rule {
    name                       = "Allow-VNet"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_address_prefix      = "10.0.0.0/16"
    destination_port_range     = "*"
    destination_address_prefix = "*"
    source_port_range          = "*"
  }

  security_rule {
    name                       = "Deny-Internet"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_address_prefix      = "*"
    destination_port_range     = "*"
    destination_address_prefix = "*"
    source_port_range          = "*"
  }
}

# ── Attach NSGs to subnets ─────────────────────────────────────────────────────
resource "azurerm_subnet_network_security_group_association" "public_assoc" {
  subnet_id                 = azurerm_subnet.public_subnet.id
  network_security_group_id = azurerm_network_security_group.public_nsg.id
}

resource "azurerm_subnet_network_security_group_association" "private_assoc" {
  subnet_id                 = azurerm_subnet.private_subnet.id
  network_security_group_id = azurerm_network_security_group.private_nsg.id
}

# ── Log Analytics Workspace (Phase 8 — CloudWatch equivalent) ─────────────────
resource "azurerm_log_analytics_workspace" "log" {
  name                = "aks-log-workspace"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# ── Azure Container Registry (Phase 7 — ECR equivalent) ───────────────────────
resource "azurerm_container_registry" "acr" {
  name                = "fairsplitacr${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Standard"
  admin_enabled       = false
}

# ── AKS Cluster (Phase 1 & 2 — EKS equivalent) ────────────────────────────────
resource "azurerm_kubernetes_cluster" "aks" {
  name                = "secure-aks-cluster"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "secureaks"

  default_node_pool {
    name           = "frontendpool"
    node_count     = 1
    vm_size        = "Standard_D2s_v3"
    vnet_subnet_id = azurerm_subnet.public_subnet.id
  }

  identity {
    type = "SystemAssigned"
  }

  role_based_access_control_enabled = true
  oidc_issuer_enabled               = true

  network_profile {
    network_plugin    = "azure"
    load_balancer_sku = "standard"
    service_cidr      = "10.1.0.0/16"
    dns_service_ip    = "10.1.0.10"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.log.id
  }

  microsoft_defender {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.log.id
  }
}

# ── Backend Node Pool — private subnet (Phase 1) ───────────────────────────────
resource "azurerm_kubernetes_cluster_node_pool" "backend_pool" {
  name                  = "backendpool"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id
  vm_size               = "Standard_D2s_v3"
  node_count            = 1
  vnet_subnet_id        = azurerm_subnet.private_subnet.id
  mode                  = "User"
}

# ── ACR Pull role for AKS kubelet identity (Phase 4 — IRSA equivalent) ────────
resource "azurerm_role_assignment" "aks_acr_pull" {
  principal_id                     = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
  role_definition_name             = "AcrPull"
  scope                            = azurerm_container_registry.acr.id
  skip_service_principal_aad_check = true
}

# ── Azure Key Vault (Phase 6 — Secrets Manager equivalent) ────────────────────
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "kv" {
  name                = "fairsplit-kv-${random_string.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = azurerm_kubernetes_cluster.aks.identity[0].principal_id

    secret_permissions = ["Get", "List"]
  }

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "List", "Set", "Delete", "Purge"]
  }
}


# ── Microsoft Defender for Containers (Phase 8 — GuardDuty equivalent) ─────────
resource "azurerm_security_center_subscription_pricing" "defender_containers" {
  tier          = "Standard"
  resource_type = "Containers"
}

# ── AKS Diagnostic Settings → Log Analytics (Phase 8 — CloudTrail equivalent) ─
resource "azurerm_monitor_diagnostic_setting" "aks_diag" {
  name                       = "aks-diagnostics"
  target_resource_id         = azurerm_kubernetes_cluster.aks.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.log.id

  enabled_log {
    category = "kube-audit"
  }

  enabled_log {
    category = "kube-audit-admin"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}

# ── Azure Monitor Action Group (Phase 8 — SNS Topic equivalent) ───────────────
resource "azurerm_monitor_action_group" "security_alerts" {
  name                = "fairsplit-security-alerts"
  resource_group_name = azurerm_resource_group.rg.name
  short_name          = "sec-alerts"

  email_receiver {
    name          = "security-team"
    email_address = "pariksha.rajput2912@gmail.com"
  }
}

# ── Alert: Brute Force (Phase 9 — CloudWatch Alarm equivalent) ────────────────
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "brute_force_alert" {
  name                 = "brute-force-detection"
  resource_group_name  = azurerm_resource_group.rg.name
  location             = azurerm_resource_group.rg.location
  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"
  scopes               = [azurerm_log_analytics_workspace.log.id]
  severity             = 0

  criteria {
    query                   = <<-QUERY
      ContainerLog
      | where LogEntry contains "BRUTE_FORCE_DETECTED"
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

# ── Alert: Scanning Detected (Phase 9) ────────────────────────────────────────
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "scanning_alert" {
  name                 = "scanning-detection"
  resource_group_name  = azurerm_resource_group.rg.name
  location             = azurerm_resource_group.rg.location
  evaluation_frequency = "PT1M"
  window_duration      = "PT1M"
  scopes               = [azurerm_log_analytics_workspace.log.id]
  severity             = 0

  criteria {
    query                   = <<-QUERY
      ContainerLog
      | where LogEntry contains "SCANNING_DETECTED"
      | where TimeGenerated > ago(1m)
    QUERY
    time_aggregation_method = "Count"
    threshold               = 1
    operator                = "GreaterThanOrEqual"
  }

  action {
    action_groups = [azurerm_monitor_action_group.security_alerts.id]
  }
}

# ── Alert: IDOR Attempt (Scenario 2b — Unauthorized Expense Settlement) ───────
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "idor_alert" {
  name                 = "idor-attempt-detection"
  resource_group_name  = azurerm_resource_group.rg.name
  location             = azurerm_resource_group.rg.location
  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"
  scopes               = [azurerm_log_analytics_workspace.log.id]
  severity             = 0

  criteria {
    query                   = <<-QUERY
      ContainerLog
      | where LogEntry contains "IDOR_ATTEMPT_DETECTED"
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

# ── Outputs ────────────────────────────────────────────────────────────────────
output "acr_login_server" {
  value       = azurerm_container_registry.acr.login_server
  description = "ACR login server — use this to tag and push Docker images"
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.aks.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.kv.vault_uri
}
