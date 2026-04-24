#!/bin/bash
# Generate self-signed certificates for development/testing.
# For production, replace with Let's Encrypt / Certbot certificates.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSL_DIR="${SCRIPT_DIR}/ssl"

mkdir -p "${SSL_DIR}"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "${SSL_DIR}/privkey.pem" \
  -out "${SSL_DIR}/fullchain.pem" \
  -subj "/CN=biomed-news-app" \
  2>/dev/null

echo "Self-signed certificates generated in ${SSL_DIR}/"
echo "  - fullchain.pem (certificate)"
echo "  - privkey.pem (private key)"
echo ""
echo "For production, replace these files with real certificates and validate nginx:"
echo "  certbot certonly --standalone -d your-domain.com"
echo "  docker compose exec nginx nginx -t"
