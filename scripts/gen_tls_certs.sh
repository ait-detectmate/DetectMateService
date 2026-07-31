#!/bin/bash
# Generates a throwaway CA + server certificate for docker-compose.tls.yml.
# For development only
# Safe to re-run any time; each run replaces the previous certs.
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/container/certs"
mkdir -p "$CERT_DIR"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# CA — only used to sign the server cert below, key is discarded afterward.
openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
  -keyout "$WORK_DIR/ca-key.pem" -out "$CERT_DIR/ca.pem" \
  -subj "/CN=DetectMate demo CA" 2>/dev/null

# Server key + cert, signed by the CA. CN must be "detector" — it has to
# match the `detector` service name so parser_settings_tls.yaml's
# tls_output.server_name (SNI/hostname check) succeeds.
openssl req -newkey rsa:4096 -sha256 -nodes \
  -keyout "$WORK_DIR/server-key.pem" -out "$WORK_DIR/server-csr.pem" \
  -subj "/CN=detector" 2>/dev/null

openssl x509 -req -in "$WORK_DIR/server-csr.pem" \
  -CA "$CERT_DIR/ca.pem" -CAkey "$WORK_DIR/ca-key.pem" -CAcreateserial \
  -days 3650 -sha256 -out "$WORK_DIR/server-cert.pem" 2>/dev/null

# TlsInputConfig.cert_key_file expects cert + key combined in one PEM.
cat "$WORK_DIR/server-cert.pem" "$WORK_DIR/server-key.pem" > "$CERT_DIR/server.pem"

echo "Generated $CERT_DIR/ca.pem and $CERT_DIR/server.pem"
