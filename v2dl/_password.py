import base64
import os
import secrets
from datetime import datetime

import yaml
from dotenv import load_dotenv, set_key
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.pwhash import scrypt
from nacl.secret import SecretBox
from nacl.utils import random as nacl_random

from .config import ConfigManager


class Encryptor:
    KEY_BYTES = 32
    SALT_BYTES = 32
    NONCE_BYTES = 24
    SCRYPT_OPS_LIMIT = 2**20
    SCRYPT_MEM_LIMIT = 2**26

    def __init__(self) -> None:
        self.config = self._initialize_config()
        self.file_handler = SecureFileHandler()
        self.custom_env_path = os.path.join(ConfigManager.get_system_config_dir(), ".env")
        self.__ensure_secure_folder()

    def _initialize_config(self) -> dict:
        """Initialize configuration settings."""
        base_dir = ConfigManager.get_system_config_dir()
        return {
            "key_folder": os.path.join(base_dir, ".keys"),
            "env_path": os.path.join(base_dir, ".env"),
            "master_key_file": os.path.join(base_dir, ".keys", "master_key.enc"),
            "private_key_file": os.path.join(base_dir, ".keys", "private_key.pem"),
            "public_key_file": os.path.join(base_dir, ".keys", "public_key.pem"),
        }

    def encrypt_master_key(self, master_key: bytes) -> tuple[bytes, bytes, bytes]:
        """Encrypt the master key using scrypt."""
        salt = secrets.token_bytes(self.SALT_BYTES)
        encryption_key = secrets.token_bytes(self.KEY_BYTES)

        # Derive the encryption key using scrypt
        derived_key = scrypt.kdf(
            self.KEY_BYTES,
            encryption_key,
            salt,
            opslimit=self.SCRYPT_OPS_LIMIT,
            memlimit=self.SCRYPT_MEM_LIMIT,
        )

        box = SecretBox(derived_key)
        nonce = nacl_random(self.NONCE_BYTES)
        encrypted_master_key = box.encrypt(master_key, nonce)

        # Clean sensitive data
        derived_key = bytearray(len(derived_key))

        return encrypted_master_key, salt, encryption_key

    def decrypt_master_key(
        self, encrypted_master_key: bytes, salt: bytes, encryption_key: bytes
    ) -> bytes:
        """Decrypt the master key using scrypt."""
        # Derive the decryption key using scrypt
        derived_key = scrypt.kdf(
            self.KEY_BYTES, encryption_key, salt, opslimit=2**20, memlimit=2**26
        )

        box = SecretBox(derived_key)
        master_key = box.decrypt(encrypted_master_key)

        # Clean sensitive data
        derived_key = bytearray(len(derived_key))

        return master_key

    def encrypt_password(self, password: str, public_key: PublicKey) -> str:
        """Encrypt a password using the public key."""
        sealed_box = SealedBox(public_key)
        encrypted = sealed_box.encrypt(password.encode())
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt_password(self, encrypted_password: str, private_key: PrivateKey) -> str:
        """Decrypt a password using the private key."""
        encrypted = base64.b64decode(encrypted_password)
        sealed_box = SealedBox(private_key)
        decrypted = sealed_box.decrypt(encrypted)
        return decrypted.decode()

    def generate_keypair(self) -> None:
        """Generate and store a new keypair with the master key."""
        if os.path.exists(self.config["private_key_file"]) and os.path.exists(
            self.config["public_key_file"]
        ):
            return

        try:
            self.__ensure_secure_folder()

            # Generate keys
            private_key = PrivateKey.generate()
            public_key = private_key.public_key
            master_key = secrets.token_bytes(self.KEY_BYTES)

            # Encrypt master key and private key
            encrypted_master_key, salt, encryption_key = self.encrypt_master_key(master_key)
            encrypted_private_key = self._encrypt_private_key(private_key, master_key)

            # Store keys
            self._store_keys(encrypted_master_key, encrypted_private_key, public_key)
            self._store_encryption_params(salt, encryption_key)

            # Clean sensitive data
            self._secure_cleanup([master_key, encryption_key])

            print("Key pair has been successfully generated and stored.")

        except Exception as e:
            raise SecurityError("Key generation failed") from e

    def _encrypt_private_key(self, private_key: PrivateKey, master_key: bytes) -> bytes:
        """Encrypt the private key using the master key."""
        box = SecretBox(master_key)
        nonce = nacl_random(self.NONCE_BYTES)
        return box.encrypt(private_key.encode(), nonce)

    def _store_keys(
        self, encrypted_master_key: bytes, encrypted_private_key: bytes, public_key: PublicKey
    ) -> None:
        """Store all keys securely."""
        self.file_handler.write_secure_file(self.config["master_key_file"], encrypted_master_key)
        self.file_handler.write_secure_file(self.config["private_key_file"], encrypted_private_key)
        self.file_handler.write_secure_file(
            self.config["public_key_file"], public_key.encode(), 0o644
        )

    def _store_encryption_params(self, salt: bytes, encryption_key: bytes) -> None:
        """Store encryption parameters in the environment file."""
        load_dotenv(self.config["env_path"])
        salt_b64 = base64.b64encode(salt).decode("utf-8")
        enc_key_b64 = base64.b64encode(encryption_key).decode("utf-8")

        set_key(self.config["env_path"], "SALT", salt_b64)
        set_key(self.config["env_path"], "ENCRYPTION_KEY", enc_key_b64)

    @staticmethod
    def _secure_cleanup(sensitive_data: list[bytes]) -> None:
        """Securely clear sensitive data from memory."""
        for data in sensitive_data:
            data = bytearray(len(data))  # noqa: PLW2901

    def load_keys(self) -> tuple[PrivateKey, PublicKey]:
        """Load and validate the keypair."""
        try:
            # Load encrypted keys
            encrypted_master_key = self.file_handler.read_secure_file(
                self.config["master_key_file"]
            )
            encrypted_private_key = self.file_handler.read_secure_file(
                self.config["private_key_file"]
            )
            public_key_bytes = self.file_handler.read_secure_file(self.config["public_key_file"])

            # Decrypt keys
            master_key = self._decrypt_master_key(encrypted_master_key)
            private_key = self._decrypt_private_key(encrypted_private_key, master_key)
            public_key = PublicKey(public_key_bytes)

            # Validate keypair
            self._validate_keypair(private_key, public_key)

            # Clean sensitive data
            self._secure_cleanup([master_key])

            return private_key, public_key

        except Exception as e:
            raise SecurityError("Key loading failed") from e

    def load_and_validate_env(self) -> tuple[str, str]:
        load_dotenv(self.config["env_path"])

        required_vars = ["SALT", "ENCRYPTION_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            raise SecurityError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        salt_base64 = os.getenv("SALT", "")
        encryption_key_base64 = os.getenv("ENCRYPTION_KEY", "")

        return salt_base64, encryption_key_base64

    def _decrypt_master_key(self, encrypted_master_key: bytes) -> bytes:
        """Decrypt the master key."""
        salt_base64, encryption_key_base64 = self.load_and_validate_env()
        salt = base64.b64decode(salt_base64)
        encryption_key = base64.b64decode(encryption_key_base64)

        master_key = self.decrypt_master_key(encrypted_master_key, salt, encryption_key)

        self._secure_cleanup([encryption_key])
        return master_key

    def _decrypt_private_key(self, encrypted_private_key: bytes, master_key: bytes) -> PrivateKey:
        """Decrypt the private key using the master key."""
        box = SecretBox(master_key)
        private_key_bytes = box.decrypt(encrypted_private_key)
        private_key = PrivateKey(private_key_bytes)
        self._secure_cleanup([private_key_bytes])
        return private_key

    def _validate_keypair(self, private_key: PrivateKey, public_key: PublicKey) -> None:
        """Validate the keypair by performing a test encryption/decryption."""
        test_data = b"test"
        sealed_box = SealedBox(public_key)
        sealed_box_priv = SealedBox(private_key)

        encrypted = sealed_box.encrypt(test_data)
        decrypted = sealed_box_priv.decrypt(encrypted)

        if decrypted != test_data:
            raise SecurityError("Key pair validation failed")

    def __ensure_secure_folder(self) -> None:
        """Ensure the key folder exists with proper permissions."""
        if not os.path.exists(self.config["key_folder"]):
            os.makedirs(self.config["key_folder"], mode=0o700)
        else:
            os.chmod(self.config["key_folder"], 0o700)


class AccountManager:
    def __init__(self, encryptor: Encryptor):
        self.encryptor = encryptor

    def create_account(self, username: str, password: str, public_key: PublicKey) -> dict:
        accounts = self.load_yaml()

        # 使用 SealedBox 加密密碼
        encrypted_password = self.encryptor.encrypt_password(password, public_key)

        accounts[username] = {
            "encrypted_password": encrypted_password,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "quota": "Null",
            "last_download": "Null",
        }
        self.save_yaml(accounts)
        print(f"Account {username} has been created.")
        return accounts

    def verify_password(self, username: str, password: str, private_key: PrivateKey) -> bool:
        accounts = self.load_yaml()
        account = accounts.get(username)
        if not account:
            print("Account does not exist.")
            return False

        encrypted_password = account.get("encrypted_password")

        # 解密密碼
        decrypted_password = self.encryptor.decrypt_password(encrypted_password, private_key)
        if decrypted_password == password:
            print("Password is correct.")
            return True
        else:
            print("Incorrect password.")
            return False

    def read_account(self, username: str) -> dict:
        accounts = self.load_yaml()
        account = accounts.get(username)
        if account:
            return account
        else:
            print("Account not found.")
            return {}

    def update_account(
        self,
        public_key: PublicKey,
        old_username: str,
        new_username: str = "",
        new_password: str = "",
    ) -> dict:
        accounts = self.load_yaml()

        if old_username in accounts:
            if new_username:
                accounts[new_username] = accounts.pop(old_username)

            if new_password:
                encrypted_password = self.encryptor.encrypt_password(new_password, public_key)
                accounts[new_username or old_username]["encrypted_password"] = encrypted_password

            self.save_yaml(accounts)
            print(f"Account {old_username} has been updated.")
        else:
            print(f"{old_username in accounts}")
            print(f"{old_username, accounts.keys()}")
            print("Account not found.")
        return accounts

    def delete_account(self, accounts: dict, username: str) -> None:
        self.save_yaml(accounts)
        print(f"Account {username} has been deleted.")

    def save_yaml(self, data: dict) -> None:
        filename = os.path.join(ConfigManager.get_system_config_dir(), "accounts.yaml")
        with open(filename, "w") as file:
            yaml.dump(data, file, default_flow_style=False)

    def load_yaml(self) -> dict:
        filename = os.path.join(ConfigManager.get_system_config_dir(), "accounts.yaml")
        try:
            with open(filename) as file:
                return yaml.safe_load(file) or {}
        except FileNotFoundError:
            return {}


class SecureFileHandler:
    @staticmethod
    def write_secure_file(path: str, data: bytes, permissions: int = 0o400) -> None:
        """Securely write data to a file with specified permissions."""
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, permissions)

    @staticmethod
    def read_secure_file(path: str) -> bytes:
        """Securely read data from a file."""
        if not os.path.exists(path):
            raise SecurityError(f"Required file not found: {path}")
        with open(path, "rb") as f:
            return f.read()


class SecurityError(Exception):
    pass
