variable "project_name" {
  description = "Ten du an"
  type        = string
}

variable "environment" {
  description = "Moi truong trien khai (dev, staging, prod)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block cho VPC"
  type        = string
}

variable "availability_zones" {
  description = "Danh sach Availability Zones su dung"
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "Danh sach CIDR blocks cho private subnets"
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "Danh sach CIDR blocks cho public subnets"
  type        = list(string)
}
