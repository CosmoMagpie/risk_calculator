"""
sign_exe.py - 用自签名证书给打包好的 exe 签名

用法：
    python sign_exe.py                  签名 dist/风控测算系统/风控测算系统.exe
    python sign_exe.py --create-cert    仅生成证书（不签名）

生成的文件：
    cert/risk_calculator.pfx    - 自签名证书（密码: risk123）
    cert/risk_calculator.cer    - 公钥证书（可发给 IT 加入企业信任）
"""

import subprocess
import sys
import os
import datetime
from pathlib import Path

# ---------- 配置 ----------
CERT_DIR = Path(__file__).parent / "cert"
CERT_NAME = "risk_calculator"
PFX_FILE = CERT_DIR / f"{CERT_NAME}.pfx"
CER_FILE = CERT_DIR / f"{CERT_NAME}.cer"
CERT_PASSWORD = "risk123"
CERT_SUBJECT = "CN=Risk Calculator, O=Dept, OU=Dev"

APP_NAME = "风控测算系统"
EXE_PATH = Path(__file__).parent / "dist" / APP_NAME / f"{APP_NAME}.exe"

SIGNTOOL = r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22000.0\x64\signtool.exe"


def generate_certificate():
    """使用 cryptography 生成自签名代码签名证书"""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    CERT_DIR.mkdir(exist_ok=True)

    print(f"[证书] 生成自签名证书...")

    # 生成密钥对
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # 证书主题
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Risk Calculator"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Dept"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Dev"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)

    # 增强型密钥用法：代码签名 (1.3.6.1.5.5.7.3.3)
    eku = x509.ExtendedKeyUsage([x509.ObjectIdentifier("1.3.6.1.5.5.7.3.3")])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 5))  # 5 年有效
        .add_extension(eku, critical=True)
        .sign(private_key, hashes.SHA256())
    )

    # 导出 .pfx（含私钥）
    from cryptography.hazmat.primitives.serialization import pkcs12 as p12_mod
    pfx_data = p12_mod.serialize_key_and_certificates(
        name=CERT_NAME.encode(),
        key=private_key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(CERT_PASSWORD.encode()),
    )
    PFX_FILE.write_bytes(pfx_data)
    print(f"[证书] 已生成: {PFX_FILE}")

    # 导出 .cer（公钥证书）
    cer_data = cert.public_bytes(serialization.Encoding.DER)
    CER_FILE.write_bytes(cer_data)
    print(f"[证书] 已导出公钥: {CER_FILE}")

    return str(PFX_FILE)


def sign_exe():
    """使用 signtool 签名 exe"""
    if not PFX_FILE.exists():
        print("[签名] 证书不存在，先生成证书...")
        generate_certificate()

    if not EXE_PATH.exists():
        print(f"[签名] 错误: 未找到 exe 文件 {EXE_PATH}")
        print("  请先运行 python build_exe.py 打包")
        return False

    if not os.path.exists(SIGNTOOL):
        print(f"[签名] 错误: 未找到 signtool.exe")
        print(f"  预期路径: {SIGNTOOL}")
        return False

    print(f"[签名] 正在签名: {EXE_PATH}")

    cmd = [
        SIGNTOOL,
        "sign",
        "/fd", "SHA256",
        "/f", str(PFX_FILE),
        "/p", CERT_PASSWORD,
        "/tr", "http://timestamp.digicert.com",
        "/td", "SHA256",
        str(EXE_PATH),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode == 0:
        print(f"\n[签名] 签名成功！")
        print(f"  已签名文件: {EXE_PATH}")
        print(f"\n  提示：如果是公司电脑首次使用，还需 IT 将证书加入信任列表：")
        print(f"    cer 文件路径: {CER_FILE}")
        print(f"    操作: certmgr.msc → 受信任的发布者 → 导入 {CER_FILE.name}")
        return True
    else:
        # 尝试无时间戳签名（某些环境时间戳服务器不可达）
        print("[签名] 时间戳签名失败，尝试无时间戳签名...")
        cmd2 = [
            SIGNTOOL, "sign",
            "/fd", "SHA256",
            "/f", str(PFX_FILE),
            "/p", CERT_PASSWORD,
            str(EXE_PATH),
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        print(result2.stdout)
        if result2.stderr:
            print(result2.stderr)
        if result2.returncode == 0:
            print(f"\n[签名] 签名成功（无时间戳）！")
            print(f"  已签名文件: {EXE_PATH}")
            return True
        else:
            print("[签名] 签名失败")
            return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="自签名 exe")
    parser.add_argument("--create-cert", action="store_true", help="仅生成证书")
    args = parser.parse_args()

    if args.create_cert:
        generate_certificate()
    else:
        sign_exe()
