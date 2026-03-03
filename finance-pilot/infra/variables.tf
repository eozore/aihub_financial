variable "project_id" {
  description = "The GCP Project ID"
  type        = string
  # Replace with your actual project ID or pass via -var="project_id=..."
  default     = "aifin-project" 
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}
