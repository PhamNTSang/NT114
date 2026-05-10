output "cluster_name" {
  description = "Ten cua EKS cluster"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "Endpoint cua EKS cluster API server"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_certificate_authority" {
  description = "Certificate authority data cua EKS cluster"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "node_group_name" {
  description = "Ten cua EKS node group"
  value       = aws_eks_node_group.main.node_group_name
}

output "cluster_iam_role_arn" {
  description = "ARN cua IAM Role cho EKS control plane"
  value       = aws_iam_role.eks_cluster.arn
}

output "nodes_iam_role_arn" {
  description = "ARN cua IAM Role cho EKS worker nodes"
  value       = aws_iam_role.eks_nodes.arn
}
