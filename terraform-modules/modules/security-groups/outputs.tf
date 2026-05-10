output "eks_cluster_sg_id" {
  description = "ID cua Security Group cho EKS control plane"
  value       = aws_security_group.eks_cluster.id
}

output "eks_nodes_sg_id" {
  description = "ID cua Security Group cho EKS worker nodes"
  value       = aws_security_group.eks_nodes.id
}

output "monitoring_sg_id" {
  description = "ID cua Security Group cho he thong monitoring"
  value       = aws_security_group.monitoring.id
}
