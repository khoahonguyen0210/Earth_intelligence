# ECR repositories for the two images Task 10.1 builds (backend/Dockerfile,
# frontend/Dockerfile) -- docs/cloud-deployment.md "Kubernetes".

resource "aws_ecr_repository" "this" {
  for_each = toset(var.repository_names)

  name = each.key

  # A tag, once pushed, always means the same image (Trivy AWS-0031), so
  # a deployed tag can never be silently replaced. Task 12.4 therefore
  # tags each push uniquely (the git commit SHA), never a reused "latest".
  image_tag_mutability = "IMMUTABLE"

  # Same teardown reasoning as modules/database: destroy must not fail on
  # a repository that still holds images.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Every push adds an image; keep only the most recent ones.
resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last ${var.images_to_keep} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.images_to_keep
      }
      action = {
        type = "expire"
      }
    }]
  })
}
