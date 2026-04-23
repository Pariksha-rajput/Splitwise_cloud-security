provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "rg" {
  name     = "secure-aks-rg"
  location = "East US"
}

# VNET (VPC Equivalent)

resource "azurerm_virtual_network" "vnet" {
  name                = "secure-vnet"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.0.0.0/16"]
}

# Subnets

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

# Network Security Groups


# 1. Frontend NSG (Allow HTTP)
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
}

# 2. Backend NSG (Private)
resource "azurerm_network_security_group" "private_nsg" {
  name                = "backend-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  # Allow only internal traffic
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

  # Deny internet access
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

# Attach NSG to subnets
resource "azurerm_subnet_network_security_group_association" "public_assoc" {
  subnet_id                 = azurerm_subnet.public_subnet.id
  network_security_group_id = azurerm_network_security_group.public_nsg.id
}

resource "azurerm_subnet_network_security_group_association" "private_assoc" {
  subnet_id                 = azurerm_subnet.private_subnet.id
  network_security_group_id = azurerm_network_security_group.private_nsg.id
}

# Log Analytics (Monitoring)

resource "azurerm_log_analytics_workspace" "log" {
  name                = "aks-log-workspace"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
}

# AKS Cluster (Kubernetes)

resource "azurerm_kubernetes_cluster" "aks" {
  name                = "secure-aks-cluster"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "secureaks"

  # Frontend Node Pool (Public Subnet)
  default_node_pool {
    name           = "frontendpool"
    node_count     = 1
    vm_size        = "Standard_DS2_v2"
    vnet_subnet_id = azurerm_subnet.public_subnet.id
  }

  identity {
    type = "SystemAssigned"
  }

  role_based_access_control_enabled = true

  network_profile {
    network_plugin = "azure"
  }

  # Monitoring enabled
  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.log.id
  }
}

# Backend Node Pool (Private)

resource "azurerm_kubernetes_cluster_node_pool" "backend_pool" {
  name                  = "backendpool"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id
  vm_size               = "Standard_DS2_v2"
  node_count            = 1
  vnet_subnet_id        = azurerm_subnet.private_subnet.id
  mode                  = "User"
}

