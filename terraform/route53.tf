resource "aws_route53_zone" "main" {
  name = var.domain_name
  tags = { Name = local.name }
}

# api.example.com → NLB fronting the nginx ingress controller
# The NLB hostname is set by the nginx ingress Service of type LoadBalancer;
# update this once the controller is deployed and the LB is provisioned.
# For an automated approach, use the external-dns Helm chart which writes these
# records automatically from Ingress annotations.
resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "CNAME"
  ttl     = 60
  records = ["PLACEHOLDER_NLB_DNS_NAME"]

  lifecycle {
    ignore_changes = [records]
  }
}

# app.example.com → frontend SPA (same NLB, different path/vhost)
resource "aws_route53_record" "app" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "app.${var.domain_name}"
  type    = "CNAME"
  ttl     = 60
  records = ["PLACEHOLDER_NLB_DNS_NAME"]

  lifecycle {
    ignore_changes = [records]
  }
}

# media.example.com → S3 presigned URLs are served from the bucket directly;
# this record can point to a CloudFront distribution if CDN is added later.
resource "aws_route53_record" "media" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "media.${var.domain_name}"
  type    = "CNAME"
  ttl     = 60
  records = [aws_s3_bucket.media.bucket_regional_domain_name]
}
