#!/usr/bin/env bash
# Step 40: this machine's own lab certificate authority.
#
# The lab services speak HTTPS with a certificate from a private CA, and every
# tool in the lab trusts that CA, so no lesson ever tells a student to pass -k
# or --insecure.  The hosted course has one CA for its shared node.  A Local
# Lab makes its own, here, and its private key never leaves this machine.
#
# The CA is made once.  The service certificate is renewed when it is within a
# month of expiring, which a re-run of the installer takes care of.
#
# Author: Tim Rice
# shellcheck source=lib.sh
. "$HR_ROOT/scripts/lib.sh"

step "Creating the lab certificate authority"

CA_DIR="$HR_ETC/ca"
install -d -m 700 "$CA_DIR"
install -d -m 755 "$LABTLS"

if [ ! -s "$CA_DIR/lab-ca.key" ] || [ ! -s "$CA_DIR/lab-ca.crt" ]; then
    # Name constraints: this CA can vouch only for the lab's own names and for
    # private addresses, never for a real website.  A student is asked to trust
    # it on their own computer (see the README), so even a stolen copy of its
    # key could not be used to impersonate their bank or their email.
    host="$(hostname -s | tr 'A-Z' 'a-z')"
    case "$host" in *[!a-z0-9-]*|'') host=localhost ;; esac
    printf '%s\n' "$host" > "$CA_DIR/permitted-host"
    nc="critical,permitted;DNS:lab,permitted;DNS:localhost,permitted;DNS:devsecops-k8s-01,permitted;DNS:$host"
    for r in 10.0.0.0/255.0.0.0 172.16.0.0/255.240.0.0 192.168.0.0/255.255.0.0 100.64.0.0/255.192.0.0 \
             127.0.0.0/255.0.0.0 169.254.0.0/255.255.0.0; do
        nc="$nc,permitted;IP:$r"
    done
    quiet openssl req -x509 -newkey rsa:4096 -sha256 -nodes -days 3650 \
        -keyout "$CA_DIR/lab-ca.key" -out "$CA_DIR/lab-ca.crt" \
        -subj "/C=US/O=Hackrange Labs/CN=Hackrange Local Lab CA ($(hostname -s))" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        -addext "nameConstraints=$nc" || die "Could not create the lab CA."
    chmod 600 "$CA_DIR/lab-ca.key"
    rm -f "$LABTLS/lab-services.crt"          # a new CA needs a new certificate
    say "new CA created"
fi

cert="$LABTLS/lab-services.crt"
if [ ! -s "$cert" ] || ! openssl x509 -checkend $((30 * 86400)) -noout -in "$cert" >/dev/null 2>&1 ||
   ! openssl verify -CAfile "$CA_DIR/lab-ca.crt" "$cert" >/dev/null 2>&1; then
    tmp="$(mktemp -d)"
    cat > "$tmp/ext.cnf" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:labgit.lab,DNS:labrepo.lab,DNS:devsecops-k8s-01,IP:${HR_SERVICES_IP}
EOF
    quiet openssl req -newkey rsa:2048 -nodes -keyout "$LABTLS/lab-services.key" \
        -out "$tmp/req.csr" -subj "/O=Hackrange Labs/CN=labrepo.lab" || die "Could not create the service key."
    quiet openssl x509 -req -in "$tmp/req.csr" -CA "$CA_DIR/lab-ca.crt" -CAkey "$CA_DIR/lab-ca.key" \
        -CAcreateserial -CAserial "$CA_DIR/lab-ca.srl" -days 825 -sha256 \
        -extfile "$tmp/ext.cnf" -out "$cert" || die "Could not sign the service certificate."
    rm -rf "$tmp"
    chmod 600 "$LABTLS/lab-services.key"
    say "service certificate issued for labgit.lab, labrepo.lab and $HR_SERVICES_IP"
fi

# Every place that needs the public CA certificate.  The key stays in $CA_DIR.
install -m 644 "$CA_DIR/lab-ca.crt" "$LABTLS/lab-ca.crt"
install -d -m 755 /etc/forgejo-runner
install -m 644 "$CA_DIR/lab-ca.crt" /etc/forgejo-runner/lab-ca.crt
install -m 644 "$CA_DIR/lab-ca.crt" /usr/local/share/ca-certificates/hackrange-lab-ca.crt
quiet update-ca-certificates
# The workstation image bakes it in at build time.
install -d -m 755 "$HR_ROOT/images/devsecops-lab/ca"
install -m 644 "$CA_DIR/lab-ca.crt" "$HR_ROOT/images/devsecops-lab/ca/lab-ca.crt"

ok "lab CA $(openssl x509 -noout -fingerprint -sha256 -in "$CA_DIR/lab-ca.crt" | cut -d= -f2 | cut -c1-23)..."
