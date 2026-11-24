"""Creates/updates .env for local use: random SECRET_KEY and VAPID keys if missing.
Run automatically by run.bat. Safe to run many times (never overwrites existing values)."""
import base64
import secrets
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV, EXAMPLE = ROOT / '.env', ROOT / '.env.example'
PLACEHOLDERS = {'', 'your-secret-key-here-change-in-production'}


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def vapid_pair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    priv = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return b64(pub), b64(priv)


def main():
    if not ENV.exists():
        shutil.copy(EXAMPLE, ENV)
    lines = ENV.read_text(encoding='utf-8').splitlines()
    values = {}
    for ln in lines:
        if '=' in ln and not ln.lstrip().startswith('#'):
            k, v = ln.split('=', 1)
            values[k.strip()] = v.strip()

    updates = {}
    if values.get('SECRET_KEY', '') in PLACEHOLDERS:
        updates['SECRET_KEY'] = secrets.token_urlsafe(50)
    if not values.get('VAPID_PUBLIC_KEY') or not values.get('VAPID_PRIVATE_KEY'):
        updates['VAPID_PUBLIC_KEY'], updates['VAPID_PRIVATE_KEY'] = vapid_pair()

    out, seen = [], set()
    for ln in lines:
        k = ln.split('=', 1)[0].strip() if '=' in ln and not ln.lstrip().startswith('#') else None
        if k in updates:
            out.append(f'{k}={updates[k]}'); seen.add(k)
        else:
            out.append(ln)
    for k, v in updates.items():
        if k not in seen:
            out.append(f'{k}={v}')
    ENV.write_text('\n'.join(out) + '\n', encoding='utf-8')
    print('  .env ready' + (' (generated: ' + ', '.join(sorted(updates)) + ')' if updates else ' (unchanged)'))


if __name__ == '__main__':
    main()
