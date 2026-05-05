# Cau hinh chung 
aws_region   = "ap-southeast-1"
project_name = "nt114-dacn"
environment  = "dev"

# Cau hinh VPC
vpc_cidr             = "10.0.0.0/16"
availability_zones   = ["ap-southeast-1a", "ap-southeast-1b"]
private_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
public_subnet_cidrs  = ["10.0.101.0/24", "10.0.102.0/24"]

# Cau hinh EKS
eks_node_instance_type = "c7i-flex.large"
eks_node_desired_size = 3
eks_node_min_size     = 3
eks_node_max_size     = 4
