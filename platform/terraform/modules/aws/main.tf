terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "project_name" {
  type = string
}

variable "region" {
  type = string
}

variable "enable_expensive_resources" {
  type    = bool
  default = false
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "db_username" {
  type    = string
  default = "ideas"
}

variable "db_password" {
  type      = string
  sensitive = true
  nullable  = true
  default   = null
}

provider "aws" {
  region = var.region
}

locals {
  azs = ["${var.region}a", "${var.region}b"]
}

resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${var.project_name}-frontend"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = var.project_name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.project_name}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${var.project_name}-private-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = var.enable_expensive_resources ? 1 : 0
  domain = "vpc"
}

resource "aws_nat_gateway" "main" {
  count         = var.enable_expensive_resources ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "private" {
  count  = var.enable_expensive_resources ? 1 : 0
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }
}

resource "aws_route_table_association" "private" {
  count          = var.enable_expensive_resources ? 2 : 0
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

resource "aws_iam_role" "eks" {
  count = var.enable_expensive_resources ? 1 : 0
  name  = "${var.project_name}-eks-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  count      = var.enable_expensive_resources ? 1 : 0
  role       = aws_iam_role.eks[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "main" {
  count    = var.enable_expensive_resources ? 1 : 0
  name     = var.project_name
  role_arn = aws_iam_role.eks[0].arn
  vpc_config {
    subnet_ids              = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
    endpoint_private_access = true
    endpoint_public_access  = true
  }
  depends_on = [aws_iam_role_policy_attachment.eks_cluster]
}

resource "aws_iam_role" "nodes" {
  count = var.enable_expensive_resources ? 1 : 0
  name  = "${var.project_name}-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "nodes_worker" {
  count      = var.enable_expensive_resources ? 1 : 0
  role       = aws_iam_role.nodes[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "nodes_registry" {
  count      = var.enable_expensive_resources ? 1 : 0
  role       = aws_iam_role.nodes[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "nodes_cni" {
  count      = var.enable_expensive_resources ? 1 : 0
  role       = aws_iam_role.nodes[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_eks_node_group" "main" {
  count           = var.enable_expensive_resources ? 1 : 0
  cluster_name    = aws_eks_cluster.main[0].name
  node_group_name = "${var.project_name}-nodes"
  node_role_arn   = aws_iam_role.nodes[0].arn
  subnet_ids      = aws_subnet.private[*].id
  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 4
  }
  instance_types = ["t3.small"]
  depends_on = [
    aws_iam_role_policy_attachment.nodes_worker,
    aws_iam_role_policy_attachment.nodes_registry,
    aws_iam_role_policy_attachment.nodes_cni,
  ]
}

resource "aws_security_group" "rds" {
  count  = var.enable_expensive_resources ? 1 : 0
  name   = "${var.project_name}-rds"
  vpc_id = aws_vpc.main.id
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [aws_security_group.eks_nodes[0].id]
  }
}

resource "aws_security_group" "eks_nodes" {
  count  = var.enable_expensive_resources ? 1 : 0
  name   = "${var.project_name}-nodes"
  vpc_id = aws_vpc.main.id
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "main" {
  count      = var.enable_expensive_resources ? 1 : 0
  name       = "${var.project_name}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  count                  = var.enable_expensive_resources ? 1 : 0
  identifier             = var.project_name
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  storage_encrypted      = true
  db_name                = "ideas"
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main[0].name
  vpc_security_group_ids = [aws_security_group.rds[0].id]
  publicly_accessible    = false
  skip_final_snapshot    = true
  deletion_protection    = false
  lifecycle {
    precondition {
      condition     = var.db_password != null
      error_message = "db_password must be supplied when AWS managed resources are enabled."
    }
  }
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "backend_registry" {
  value = aws_ecr_repository.backend.repository_url
}

output "frontend_registry" {
  value = aws_ecr_repository.frontend.repository_url
}

output "eks_name" {
  value = var.enable_expensive_resources ? aws_eks_cluster.main[0].name : null
}

output "database_endpoint" {
  value     = var.enable_expensive_resources ? aws_db_instance.main[0].address : null
  sensitive = true
}
