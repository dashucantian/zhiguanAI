#!/usr/bin/env python3
"""
生成本地自签 TLS 证书（HTTPS 服务用，2026-09-06 建，2026-09-12 补 SAN）。

为什么需要 HTTPS：WebXR 规范规定 navigator.xr 仅在「安全上下文」
（HTTPS 或 localhost）下暴露。Pico 头显经局域网 HTTP 访问本机控制台时
拿不到 WebXR 能力，无法进入 VR；改用 HTTPS（自签证书即可）解决。

═══ 2026-09-12 修正：原证书无 SAN 扩展 ═══
原实现只写 CN=zhiguan-local，**没有 SubjectAlternativeName**。
自 Chrome 58 起证书主机名校验只认 SAN、忽略 CN，故用局域网 IP 访问时
浏览器判定「主机名不匹配」——这比「自签 CA 不受信任」更严的一层错误，
某些情况下连「继续访问」入口都不给。

后果（针对 PWA）：Service Worker 注册要求安全上下文，证书主机名不匹配时
注册会被拒 → manifest 无效 → **装不到 Pico 应用库**。
（此前 verify_pwa.py 用了 --ignore-certificate-errors 跑通，掩盖了这层真实校验。）

修正：SAN 纳入 localhost / 127.0.0.1 / 本机全部局域网 IPv4；
并在每次启动时检查现有证书 SAN 是否仍覆盖当前 IP（本机 IP 会变：
实测 192.168.43.6 → 192.168.188.105），不覆盖则自动重签。
重签后 Pico 需重新信任一次证书（点「继续访问」）。

证书落点：项目根 vr_assets/tls/（cert.pem + key.pem），有效期 825 天。
"""
import datetime
import os
import socket
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TLS_DIR = os.path.join(SCRIPT_DIR, "vr_assets", "tls")
CERT_PATH = os.path.join(TLS_DIR, "cert.pem")
KEY_PATH = os.path.join(TLS_DIR, "key.pem")


def local_ips():
    """本机局域网 IPv4 集合（不含 127.0.0.1）。

    ⚠️ 不出网：UDP socket 的 connect() 对无连接协议**不发送任何数据包**，
    仅让内核据路由表选定出口地址，随后 getsockname() 读出该地址。
    getaddrinfo(本机主机名) 亦为本地解析。两者均不产生对外流量，
    符合项目「原始EEG与学员数据绝不出网」的数据边界纪律。
    """
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 53))       # 不发包，仅查路由
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    ips.discard("127.0.0.1")
    return ips


def _load_cert(path):
    from cryptography import x509
    with open(path, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def cert_covers(cert_path, ips):
    """现有证书的 SAN 是否已覆盖给定 IP 集合（含 127.0.0.1）。"""
    try:
        from cryptography import x509
        cert = _load_cert(cert_path)
        try:
            ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName)
        except x509.ExtensionNotFound:
            return False                      # 无 SAN → 视为不覆盖（须重签）
        have = {str(v) for v in ext.value.get_values_for_type(x509.IPAddress)}
        return set(ips) <= have
    except Exception:
        return False


def cert_summary(cert_path):
    """证书要点摘要（供启动日志与实测核对）。"""
    try:
        from cryptography import x509
        cert = _load_cert(cert_path)
        try:
            ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName)
            dns = [str(v) for v in ext.value.get_values_for_type(x509.DNSName)]
            ips = [str(v) for v in ext.value.get_values_for_type(x509.IPAddress)]
        except x509.ExtensionNotFound:
            dns, ips = [], []
        return {"subject": cert.subject.rfc4514_string(),
                "not_before": str(cert.not_valid_before_utc.date()),
                "not_after": str(cert.not_valid_after_utc.date()),
                "san_dns": dns, "san_ip": ips}
    except Exception as ex:
        return {"error": str(ex)}


def _build_cert(common_name):
    import ipaddress
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ZhiguanAI Local"),
    ])

    # SAN：localhost + 127.0.0.1 + 本机全部局域网 IPv4
    san = [x509.DNSName("localhost"),
           x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
    ips = sorted(local_ips())
    for ip in ips:
        try:
            san.append(x509.IPAddress(ipaddress.IPv4Address(ip)))
        except ValueError:
            continue                          # 跳过 IPv6 或非法值

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
        # SAN 必须非关键（critical=False），否则部分客户端解析异常
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()))
    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return ips


def ensure_cert(common_name="zhiguan-local", force=False):
    """确保自签证书存在且 SAN 覆盖当前本机 IP；返回 (cert_path, key_path)。

    幂等：证书已存在且 SAN 覆盖当前全部局域网 IP 时直接返回，不重签
    （避免每次重启都让 Pico 重新信任一次）。
    IP 变化或旧证书无 SAN 时自动重签。
    ⚠️ 重签为**直接覆盖**：自签本地证书无长期保留价值，且复制私钥会
    增加泄露面，故不做备份副本。
    """
    os.makedirs(TLS_DIR, exist_ok=True)
    ips = local_ips() | {"127.0.0.1"}
    if not force and os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        if cert_covers(CERT_PATH, ips):
            return CERT_PATH, KEY_PATH
        print(f"[TLS] 现有证书 SAN 未覆盖当前 IP {sorted(ips)}，重新签发"
              f"（Pico 需重新信任一次）")
    _build_cert(common_name)
    return CERT_PATH, KEY_PATH


if __name__ == "__main__":
    try:
        force = "--force" in sys.argv
        c, k = ensure_cert(force=force)
        print("CERT:", c)
        print("KEY :", k)
        s = cert_summary(c)
        print("摘要:", s)
    except Exception as ex:
        print("证书生成失败:", ex, file=sys.stderr)
        sys.exit(1)
