import atexit
import base64
import os
import random
import secrets
import sys
import threading
from datetime import datetime, timedelta

import yaml
from dotenv import load_dotenv, set_key
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.pwhash import scrypt
from nacl.secret import SecretBox
from nacl.utils import random as nacl_random

from ..config import ConfigManager
from ..error import SecurityError


class Encryptor:
    KEY_BYTES = 32
    SALT_BYTES = 32
    NONCE_BYTES = 24
    SCRYPT_OPS_LIMIT = 2**20
    SCRYPT_MEM_LIMIT = 2**26

    def __init__(self, logger) -> None:
        self.logger = logger
        self.config = self._initialize_config()
        self.file_handler = SecureFileHandler()
        self.custom_env_path = os.path.join(ConfigManager.get_system_config_dir(), ".env")
        self.__ensure_secure_folder()
        self._generate_keypair()

    def _initialize_config(self) -> dict:
        """Initialize configuration settings."""
        base_dir = ConfigManager.get_system_config_dir()
        self.logger.debug("Initializing config with base directory: %s", base_dir)
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

        self.logger.debug("Derived encryption key with salt: %s", salt.hex())
        box = SecretBox(derived_key)
        nonce = nacl_random(self.NONCE_BYTES)
        encrypted_master_key = box.encrypt(master_key, nonce)

        # Clean sensitive data
        derived_key = bytearray(len(derived_key))
        self.logger.info("Master key encryption successful")

        return encrypted_master_key, salt, encryption_key

    def decrypt_master_key(
        self, encrypted_master_key: bytes, salt: bytes, encryption_key: bytes
    ) -> bytes:
        """Decrypt the master key using scrypt."""
        # Derive the decryption key using scrypt
        derived_key = scrypt.kdf(
            self.KEY_BYTES,
            encryption_key,
            salt,
            opslimit=self.SCRYPT_OPS_LIMIT,
            memlimit=self.SCRYPT_MEM_LIMIT,
        )

        box = SecretBox(derived_key)
        master_key = box.decrypt(encrypted_master_key)

        # Clean sensitive data
        derived_key = bytearray(len(derived_key))
        self.logger.info("Master key decryption successful")

        return master_key

    def encrypt_password(self, password: str, public_key: PublicKey) -> str:
        """Encrypt a password using the public key."""
        sealed_box = SealedBox(public_key)
        encrypted = sealed_box.encrypt(password.encode())
        self.logger.info("Password encryption successful")

        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt_password(self, encrypted_password: str, private_key: PrivateKey) -> str:
        """Decrypt a password using the private key."""
        encrypted = base64.b64decode(encrypted_password)
        sealed_box = SealedBox(private_key)
        decrypted = sealed_box.decrypt(encrypted)
        return decrypted.decode()

    def _generate_keypair(self) -> None:
        """Generate and store a new keypair with the master key."""
        if os.path.exists(self.config["private_key_file"]) and os.path.exists(
            self.config["public_key_file"]
        ):
            self.logger.info("Key pair already exists.")
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
            self.logger.info("Key pair has been successfully generated and stored.")

        except Exception as e:
            self.logger.error("Key generation failed: %s", str(e))
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
        self.logger.debug("Storing keys securely.")
        self.file_handler.write_secure_file(self.config["master_key_file"], encrypted_master_key)
        self.file_handler.write_secure_file(self.config["private_key_file"], encrypted_private_key)
        self.file_handler.write_secure_file(
            self.config["public_key_file"], public_key.encode(), 0o644
        )

    def _store_encryption_params(self, salt: bytes, encryption_key: bytes) -> None:
        """Store encryption parameters in the environment file."""
        self.logger.debug("Storing encryption parameters.")
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
            self.logger.debug("Loading and validating keys.")
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
            self.logger.info("Keys loaded and validated successfully.")

            return private_key, public_key

        except Exception as e:
            self.logger.error("Key loading failed: %s", str(e))
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
    MAX_QUOTA = 16
    ACCOUNT_FILE_PATH = os.path.join(ConfigManager.get_system_config_dir(), "accounts.yaml")

    def __init__(self, encryptor, logger):
        self.encryptor = encryptor
        self.lock = threading.RLock()
        self.accounts = self.load_yaml()
        self.check_accounts()
        self.logger = logger
        atexit.register(self.save_yaml)

    def check_accounts(self):
        """檢查所有帳號的 exceed_time 是否超過 24 小時，若超過則清除 exceed_time 並將重置 exceed_quota."""
        now = datetime.now()
        update = False

        for _, account in self.accounts.items():
            exceed_time = account.get("exceed_time")
            if exceed_time and exceed_time != "Null":
                exceed_time_time = datetime.strptime(exceed_time, "%Y-%m-%dT%H:%M:%S")
                if now - exceed_time_time > timedelta(hours=24):
                    account["exceed_time"] = "Null"
                    account["exceed_quota"] = False
                    update = True

        if update:
            self.save_yaml()

    def create_account(self, username: str, password: str, public_key: PublicKey):
        with self.lock:
            encrypted_password = self.encryptor.encrypt_password(password, public_key)
            self.accounts[username] = {
                "encrypted_password": encrypted_password,
                "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "exceed_quota": False,
                "exceed_time": "Null",
            }
        self.logger.info("Account %s has been created.", username)
        self.save_yaml()

    def verify_password(self, username: str, password: str, private_key: PrivateKey) -> bool:
        account = self.accounts.get(username)
        if not account:
            self.logger.error("Account does not exist.")
            return False

        encrypted_password = account.get("encrypted_password")
        decrypted_password = self.encryptor.decrypt_password(encrypted_password, private_key)
        if decrypted_password == password:
            print("Password is correct.")
            return True
        else:
            print("Incorrect password.")
            return False

    def read_account(self, username: str) -> dict:
        return self.accounts.get(username, {})

    def edit_account(
        self,
        public_key: PublicKey,
        old_username: str,
        new_username: str = "",
        new_password: str = "",
    ):
        with self.lock:
            if old_username in self.accounts:
                if new_username:
                    self.accounts[new_username] = self.accounts.pop(old_username)
                if new_password:
                    encrypted_password = self.encryptor.encrypt_password(new_password, public_key)
                    self.accounts[new_username or old_username]["encrypted_password"] = (
                        encrypted_password
                    )
                self.logger.info("Account %s has been updated.", old_username)
            else:
                self.logger.error("Account not found.")

    def delete_account(self, username: str):
        with self.lock:
            if username in self.accounts:
                del self.accounts[username]
                self.logger.info("Account %s has been deleted.", username)
            else:
                self.logger.error("Account %s not found.", username)
            self.save_yaml()

    def save_yaml(self):
        with self.lock:
            with open(self.ACCOUNT_FILE_PATH, "w") as file:
                yaml.dump(self.accounts, file, default_flow_style=False)
        # self.logger.info("Successfully update accounts information.")

    def load_yaml(self) -> dict:
        try:
            with open(self.ACCOUNT_FILE_PATH) as file:
                return yaml.safe_load(file) or {}
        except FileNotFoundError:
            return {}

    def get_account(self, private_key: PrivateKey) -> tuple[str, str]:
        eligible_accounts = {k: v for k, v in self.accounts.items() if not v["exceed_quota"]}

        if not eligible_accounts:
            self.logger.error("All accounts have exhausted their reading quota.")
            sys.exit(1)

        username, account = random.choice(list(eligible_accounts.items()))
        enc_pw = account["encrypted_password"]
        dec_pw = self.encryptor.decrypt_password(enc_pw, private_key)

        return username, dec_pw

    def update(self, username: str, field: str, new_value):
        with self.lock:
            account = self.accounts.get(username)
            if account:
                if field in account:
                    account[field] = new_value
                    self.logger.info("Updated %s for account %s.", field, username)
                    self.save_yaml()
                else:
                    self.logger.error("Field '%s' does not exist in the account.", field)
            else:
                self.logger.error("Account %s not found.", username)


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
