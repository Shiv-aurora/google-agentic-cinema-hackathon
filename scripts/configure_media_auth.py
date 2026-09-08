"""Generate a private local admin key and a credential-hashed MediaMTX config."""
import json
import os
import secrets
import ipaddress
from pathlib import Path

import yaml

from services.media.credentials import password_hash


def main():
    data = Path(os.getenv("CLAPPY_DATA_DIR", "data"))
    data.mkdir(exist_ok=True)
    key_path = data/"media-admin.key"
    if not key_path.exists():
        descriptor = os.open(key_path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(secrets.token_urlsafe(32))
    key = key_path.read_text().strip()
    if len(key)<32:
        raise ValueError("Existing media admin key is too short")
    config = yaml.safe_load(Path("infra/mediamtx.yml").read_text())
    public_ip = os.getenv("CLAPPY_MEDIA_PUBLIC_IP")
    if public_ip:
        config["webrtcAdditionalHosts"] = [str(ipaddress.ip_address(public_ip))]
        config["webrtcAllowOrigins"] = [os.environ["CLAPPY_PUBLIC_ORIGIN"]]
        config["pathDefaults"]["maxReaders"] = 16
    config["authMethod"] = "internal"
    config["authInternalUsers"] = [{"user":"clappy-admin", "pass":password_hash(key), "permissions":[{"action":"api"}]}]
    output = data/"mediamtx-secure.json"
    encoded = json.dumps(config,indent=2)+"\n"
    # Avoid triggering a live config reload when bootstrap is already current.
    if not output.exists() or output.read_text() != encoded:
        output.write_text(encoded)
    output.chmod(0o600)
    print(json.dumps({"configured":True,"config_file":str(output),"private_key_file":str(key_path)}))


if __name__ == "__main__":
    main()
