"""MediaMTX-native, exact-path accounts. No master secret reaches the browser."""
import base64
import hashlib
import secrets


def password_hash(password):
    return "sha256:"+base64.b64encode(hashlib.sha256(password.encode()).digest()).decode()


def camera_credentials(take_id):
    readers, publishers, users = {}, {}, []
    for cam in "abc":
        for role, action, destination in (("r", "read", readers), ("p", "publish", publishers)):
            user, password = f"clappy-{role}-{take_id}-{cam}", secrets.token_urlsafe(24)
            destination[cam] = {"user": user, "pass": password}
            users.append({"user": user, "pass": password_hash(password),
                "permissions": [{"action": action, "path": f"{take_id}/{cam}"}]})
    return readers, publishers, users
