# ============================================================
# Outputs tu module VPC
# ============================================================
output "vpc_id" {
  description = "ID cua VPC"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Danh sach ID cua private subnets"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Danh sach ID cua public subnets"
  value       = module.vpc.public_subnet_ids
}

# ============================================================
# Outputs tu module EKS
# ============================================================
output "eks_cluster_name" {
  description = "Ten cua EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Endpoint cua EKS cluster API server"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_certificate_authority" {
  description = "Certificate authority data cua EKS cluster"
  value       = module.eks.cluster_certificate_authority
}

output "eks_node_group_name" {
  description = "Ten cua EKS node group"
  value       = module.eks.node_group_name
}

# ============================================================
# Outputs tu module Security Groups
# ============================================================
output "eks_cluster_sg_id" {
  description = "ID cua Security Group cho EKS control plane"
  value       = module.security_groups.eks_cluster_sg_id
}

output "eks_nodes_sg_id" {
  description = "ID cua Security Group cho EKS worker nodes"
  value       = module.security_groups.eks_nodes_sg_id
}
