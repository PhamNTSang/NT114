variable "project_name" {
  description = "Ten du an"
  type        = string
}

variable "environment" {
  description = "Moi truong trien khai (dev, staging, prod)"
  type        = string
}

variable "vpc_id" {
  description = "ID cua VPC (nhan tu module vpc)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block cua VPC, dung cho ingress rules"
  type        = string
}
