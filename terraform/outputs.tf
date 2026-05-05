# VPC ouputs

output "vpc_id" {
  description = "ID cua VPC"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "Danh sach ID cua private subnets"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "Danh sach ID cua public subnets"
  value       = aws_subnet.public[*].id
}

# EKS outputs
output "eks_cluster_name" {
  description = "Ten cua EKS cluster"
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "Endpoint cua EKS cluster API server"
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_certificate_authority" {
  description = "Certificate authority data cua EKS cluster"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "eks_node_group_name" {
  description = "Ten cua EKS node group"
  value       = aws_eks_node_group.main.node_group_name
}
