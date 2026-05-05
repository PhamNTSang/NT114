# Tao Security group cho EKS control plane va worker nodes
resource "aws_security_group" "eks_cluster" {
  name        = "${var.project_name}-${var.environment}-eks-cluster-sg"
  description = "Security group cho EKS cluster control plane"
  vpc_id      = aws_vpc.main.id

# Cho phep control plane giao tiep voi worker nodes tren port 443
 ingress {
    description = "HTTPS tu VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  # Cho phep tat ca luu luong di ra
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

# Security group cho EKS worker nodes
resource "aws_security_group" "eks_nodes" {
  name        = "${var.project_name}-${var.environment}-eks-nodes-sg"
  description = "Security group cho EKS worker nodes"
  vpc_id      = aws_vpc.main.id

  # Cho phep worker nodes giao tiep voi nhau 
  ingress {
    description = "Giao tiep giua cac worker nodes"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }
    # Cho phep worker nodes giao tiep voi control plane tren port 443
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

  # Cho phep tat ca luu luong di ra
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

# Tao Security Group ccho viec giam sat bang Grafana va Prometheus
resource "aws_security_group" "monitoring" {
  name        = "${var.project_name}-${var.environment}-monitoring-sg"
  description = "Security group cho he thong monitoring (Prometheus, Grafana, Alertmanager)"
  vpc_id      = aws_vpc.main.id

  # Prometheus - Thu thap metrics tu EKS cluster
  ingress {
    description = "Prometheus tu VPC"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Grafana - Dashboard giam sat 
  ingress {
    description = "Grafana tu VPC"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Alertmanager - Quan ly canh bao
  ingress {
    description = "Alertmanager tu VPC"
    from_port   = 9093
    to_port     = 9093
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Cho phep tat ca luu luong di ra
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

