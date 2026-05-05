# Cau hinh chung cho cac resource
variable "aws_region" {
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  type        = string
  default     = "nt114-dacn"
}

variable "environment" {
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Gia tri environment phai la dev, staging hoac prod."
  }
}
# Cau hinh VPC
variable "vpc_cidr" {
  description = "CIDR block cho VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Danh sach Availability Zones su dung"
  type        = list(string)
  default     = ["ap-southeast-1a", "ap-southeast-1b"]
}

variable "private_subnet_cidrs" {
  description = "Danh sach CIDR blocks cho private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  description = "Danh sach CIDR blocks cho public subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}
# Cau hinh EKS 
variable "eks_cluster_version" {
  description = "Phien ban Kubernetes cho EKS cluster"
  type        = string
  default     = "1.31"
}

variable "eks_node_instance_type" {
  description = "Loai EC2 instance cho EKS worker nodes"
  type        = string
  default     = "t3.micro"
}

variable "eks_node_desired_size" {
  description = "So luong worker nodes mong muon"
  type        = number
  default     = 8
}

variable "eks_node_min_size" {
  description = "So luong worker nodes toi thieu"
  type        = number
  default     = 2
}

variable "eks_node_max_size" {
  description = "So luong worker nodes toi da"
  type        = number
  default     = 10
}
