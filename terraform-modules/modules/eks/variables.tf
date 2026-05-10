variable "project_name" {
  description = "Ten du an"
  type        = string
}

variable "environment" {
  description = "Moi truong trien khai (dev, staging, prod)"
  type        = string
}

variable "eks_cluster_version" {
  description = "Phien ban Kubernetes cho EKS cluster"
  type        = string
}

variable "eks_node_instance_type" {
  description = "Loai EC2 instance cho EKS worker nodes"
  type        = string
}

variable "eks_node_desired_size" {
  description = "So luong worker nodes mong muon"
  type        = number
}

variable "eks_node_min_size" {
  description = "So luong worker nodes toi thieu"
  type        = number
}

variable "eks_node_max_size" {
  description = "So luong worker nodes toi da"
  type        = number
}

# --- Inputs tu cac module khac ---

variable "private_subnet_ids" {
  description = "Danh sach ID private subnets (nhan tu module vpc)"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Danh sach ID public subnets (nhan tu module vpc)"
  type        = list(string)
}

variable "eks_cluster_sg_id" {
  description = "ID Security Group cho EKS control plane (nhan tu module security-groups)"
  type        = string
}
