# Cau hinh IAM Role cho EKS cluster control plane
resource "aws_iam_role" "eks_cluster" {
  name = "${var.project_name}-${var.environment}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-eks-cluster-role"
  })
}
# Gan policy AmazonEKSClusterPolicy cho IAM role cua EKS cluster control plane
resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

# Cau hinh IAM Role cho EKS worker nodes
resource "aws_iam_role" "eks_nodes" {
  name = "${var.project_name}-${var.environment}-eks-nodes-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-eks-nodes-role"
  })
}
# Gan policy AmazonEKSWorkerNodePolicy, AmazonEKS_CNI_Policy va AmazonEC2ContainerRegistryReadOnly cho IAM role cua EKS worker nodes
resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_container_registry_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

# Cau hinh EKS cluster
resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-${var.environment}"
  version  = var.eks_cluster_version
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids = concat(
      aws_subnet.private[*].id,
      aws_subnet.public[*].id
    )
    security_group_ids      = [aws_security_group.eks_cluster.id]
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-eks-cluster"
  })

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy
  ]
}
# Cau hinh EKS node group
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project_name}-${var.environment}-node-group"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = [var.eks_node_instance_type]

  ami_type        = "AL2_x86_64"

  scaling_config {
    desired_size = var.eks_node_desired_size
    min_size     = var.eks_node_min_size
    max_size     = var.eks_node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-eks-node-group"
  })

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_container_registry_policy
  ]
}
