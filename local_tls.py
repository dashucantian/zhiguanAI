#!/usr/bin/env python3
"""
生成本地自签 TLS 证书（HTTPS 服务用，2026-09-06）。

为什么需要 HTTPS：WebXR 规范规定 navigator.xr 仅在「安全上下文」
（HTTPS 或 localhost）下暴露。Pico 头显经局域网 HTTP 访问本机控制台时
拿不到 WebXR 能力，无法进入 VR；改用 HTTPS（自签证书即可）解决。

证书落点：项目根 vr_assets/tls/（cert.pem + key.pem），有效期 825 天。
已存在则跳过（幂等）。Pico 首次访问需在浏览器里信任一次自签证书。
"""
import os
import sys
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TLS_DIR = os.path.join(SCRIPT_DIR, "vr_assets", "tls")
CERT_PATH = os.path.join(TLS_DIR, "cert.pem")
KEY_PATH = os.path.join(TLS_DIR, "key.pem")


def ensure_cert(common_name="zhiguan-local"):
    """确保自签证书存在；返回 (cert_path, key_path)。"""
    os.makedirs(TLS_DIR, exist_ok=True)
    if os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        return CERT_PATH, KEY_PATH

    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ZhiguanAI Local"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()))
    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return CERT_PATH, KEY_PATH


if __name__ == "__main__":
    try:
        c, k = ensure_cert()
        print("CERT:", c)
        print("KEY:", k)
    except Exception as ex:
        print("证书生成失败:", ex, file=sys.stderr)
        sys.exit(1)
