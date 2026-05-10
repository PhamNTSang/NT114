locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    Terraform   = "true"
  }
}

# ============================================================
# Security Group: EKS Control Plane
# ============================================================
resource "aws_security_group" "eks_cluster" {
  name        = "${var.project_name}-${var.environment}-eks-cluster-sg"
  description = "Security group cho EKS cluster control plane"
  vpc_id      = var.vpc_id

  # Cho phep control plane nhan ket noi HTTPS tu trong VPC
  ingress {
    description = "HTTPS tu VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Cho phep tat ca luu luong di ra"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-eks-cluster-sg"
  })
}

# ============================================================
# Security Group: EKS Worker Nodes
# ============================================================
resource "aws_security_group" "eks_nodes" {
  name        = "${var.project_name}-${var.environment}-eks-nodes-sg"
  description = "Security group cho EKS worker nodes"
  vpc_id      = var.vpc_id

  # Cho phep worker nodes giao tiep noi bo voi nhau
  ingress {
    description = "Giao tiep giua cac worker nodes"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  # Cho phep worker nodes nhan ket noi HTTPS tu control plane
  ingress {
    description     = "HTTPS tu EKS cluster control plane"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_cluster.id]
  }

  # Cho phep control plane giao tiep voi kubelet tren worker nodes
  ingress {
    description     = "Kubelet tu EKS cluster control plane"
    from_port       = 10250
    to_port         = 10250
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_cluster.id]
  }

  egress {
    description = "Cho phep tat ca luu luong di ra"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-eks-nodes-sg"
  })
}

# ============================================================
# Security Group: Monitoring (Prometheus, Grafana, Alertmanager)
# ============================================================
resource "aws_security_group" "monitoring" {
  name        = "${var.project_name}-${var.environment}-monitoring-sg"
  description = "Security group cho he thong monitoring (Prometheus, Grafana, Alertmanager)"
  vpc_id      = var.vpc_id

  ingress {
    description = "Prometheus tu VPC"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description = "Grafana tu VPC"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description = "Alertmanager tu VPC"
    from_port   = 9093
    to_port     = 9093
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Cho phep tat ca luu luong di ra"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-monitoring-sg"
  })
}
