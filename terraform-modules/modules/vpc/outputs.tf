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

output "nat_gateway_id" {
  description = "ID cua NAT Gateway"
  value       = aws_nat_gateway.main.id
}
