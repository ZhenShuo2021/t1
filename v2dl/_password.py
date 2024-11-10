import base64
import getpass
import os
import secrets
from datetime import datetime

import questionary
import yaml
from dotenv import load_dotenv, set_key
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.pwhash import scrypt
from nacl.secret import SecretBox
from nacl.utils import random as nacl_random

from .config import ConfigManager


class SecurityError(Exception):
    pass


class KeyManager:
    KEY_BYTES = 32
    SALT_BYTES = 32
    NONCE_BYTES = 24
    KEY_FOLDER = os.path.join(ConfigManager.get_system_config_dir(), ".keys")
    custom_env_path = os.path.join(ConfigManager.get_system_config_dir(), ".env")
    MASTER_KEY_FILE = os.path.join(KEY_FOLDER, "master_key.enc")

    def __init__(self) -> None:
        self.__ensure_secure_folder()

    def __ensure_secure_folder(self) -> None:
        """確保密鑰資料夾存在並設置正確的權限."""
        if not os.path.exists(self.KEY_FOLDER):
            os.makedirs(self.KEY_FOLDER, mode=0o700)
        else:
            os.chmod(self.KEY_FOLDER, 0o700)

    def __secure_random_bytes(self, size: int) -> bytes:
        """生成安全的隨機位元組."""
        return secrets.token_bytes(size)

    def start_up(self) -> None:
        private_key_path = os.path.join(self.KEY_FOLDER, "private_key.pem")
        public_key_path = os.path.join(self.KEY_FOLDER, "public_key.pem")
        if not os.path.exists(private_key_path) or not os.path.exists(public_key_path):
            self.generate_keypair()

    def encrypt_master_key(self, master_key: bytes) -> None:
        """加密主金鑰並存儲到檔案中，使用 scrypt 產生加密金鑰和 salt."""
        salt = self.__secure_random_bytes(self.SALT_BYTES)
        encryption_key = self.__secure_random_bytes(self.KEY_BYTES)

        # 使用 scrypt 將 encryption_key 和 salt 轉換為主金鑰加密金鑰
        derived_key = scrypt.kdf(
            self.KEY_BYTES, encryption_key, salt, opslimit=2**20, memlimit=2**26
        )
        box = SecretBox(derived_key)
        nonce = nacl_random(self.NONCE_BYTES)
        encrypted_master_key = box.encrypt(master_key, nonce)

        # 儲存加密後的主金鑰到檔案
        with open(self.MASTER_KEY_FILE, "wb") as f:
            f.write(encrypted_master_key)
        os.chmod(self.MASTER_KEY_FILE, 0o400)

        # 將 salt 和 encryption_key 存入 .env
        load_dotenv(self.custom_env_path)
        salt_base64 = base64.b64encode(salt).decode("utf-8")
        encryption_key_base64 = base64.b64encode(encryption_key).decode("utf-8")
        set_key(self.custom_env_path, "SALT", salt_base64)
        set_key(self.custom_env_path, "ENCRYPTION_KEY", encryption_key_base64)

        # 清理敏感數據
        master_key = bytearray(len(master_key))
        encryption_key = bytearray(len(encryption_key))
        derived_key = bytearray(len(derived_key))

    def decrypt_master_key(self) -> bytes:
        """從檔案中載入並解密主金鑰."""
        # 從 .env 中載入 salt 和 encryption_key
        load_dotenv(self.custom_env_path)
        salt_base64 = os.getenv("SALT")
        encryption_key_base64 = os.getenv("ENCRYPTION_KEY")

        if not salt_base64 or not encryption_key_base64:
            raise SecurityError("Either SALT in .env or ENCRYPTION_KEY not found")

        salt = base64.b64decode(salt_base64)
        encryption_key = base64.b64decode(encryption_key_base64)

        # 使用 scrypt 還原 derived_key
        derived_key = scrypt.kdf(
            self.KEY_BYTES, encryption_key, salt, opslimit=2**20, memlimit=2**26
        )

        # 載入並解密主金鑰
        with open(self.MASTER_KEY_FILE, "rb") as f:
            encrypted_master_key = f.read()

        box = SecretBox(derived_key)
        master_key = box.decrypt(encrypted_master_key)

        # 清理敏感數據
        encryption_key = bytearray(len(encryption_key))
        derived_key = bytearray(len(derived_key))

        return master_key

    def generate_keypair(self) -> None:
        try:
            self.__ensure_secure_folder()

            # 生成金鑰對
            private_key = PrivateKey.generate()
            public_key = private_key.public_key

            # 生成主金鑰並加密
            master_key = self.__secure_random_bytes(self.KEY_BYTES)
            self.encrypt_master_key(master_key)

            # 加密私鑰
            box = SecretBox(master_key)
            nonce = nacl_random(self.NONCE_BYTES)
            encrypted_private_key = box.encrypt(private_key.encode(), nonce)

            # 分開儲存各個組件
            private_key_path = os.path.join(self.KEY_FOLDER, "private_key.pem")
            public_key_path = os.path.join(self.KEY_FOLDER, "public_key.pem")

            # 儲存加密後的私鑰
            with open(private_key_path, "wb") as f:
                f.write(encrypted_private_key)
            os.chmod(private_key_path, 0o400)

            # 儲存公鑰
            with open(public_key_path, "wb") as f:
                f.write(public_key.encode())
            os.chmod(public_key_path, 0o644)

            print("Key pair has been successfully generated and stored.")

        except Exception as e:
            raise SecurityError(f"Key generation failed: {e!s}") from e

    def load_keys(self) -> tuple[PrivateKey, PublicKey]:
        try:
            private_key_path = os.path.join(self.KEY_FOLDER, "private_key.pem")
            public_key_path = os.path.join(self.KEY_FOLDER, "public_key.pem")

            # 檢查所有必要檔案是否存在
            for path in [private_key_path, public_key_path, self.MASTER_KEY_FILE]:
                if not os.path.exists(path):
                    raise SecurityError(f"Required key file not found: {path}")

            # 從檔案載入並解密主金鑰
            master_key = self.decrypt_master_key()

            # 載入加密的私鑰
            with open(private_key_path, "rb") as f:
                encrypted_private_key = f.read()

            # 載入公鑰
            with open(public_key_path, "rb") as f:
                public_key_bytes = f.read()

            # 解密私鑰
            box = SecretBox(master_key)
            private_key_bytes = box.decrypt(encrypted_private_key)

            private_key = PrivateKey(private_key_bytes)
            public_key = PublicKey(public_key_bytes)

            # 清理敏感數據
            master_key = bytearray(len(master_key))
            private_key_bytes = bytearray(len(private_key_bytes))

            # 驗證金鑰對是否匹配
            test_data = b"test"
            sealed_box = SealedBox(public_key)
            sealed_box_priv = SealedBox(private_key)

            encrypted = sealed_box.encrypt(test_data)
            decrypted = sealed_box_priv.decrypt(encrypted)

            if decrypted != test_data:
                raise SecurityError("Key pair validation failed.")

            return private_key, public_key

        except Exception as e:
            raise SecurityError(f"Key loading failed: {e!s}") from e

    def encrypt_password(self, public_key: PublicKey, password: str) -> str:
        sealed_box = SealedBox(public_key)
        encrypted = sealed_box.encrypt(password.encode())
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt_password(self, private_key: PrivateKey, encrypted_password: str) -> str:
        encrypted = base64.b64decode(encrypted_password)
        sealed_box = SealedBox(private_key)
        decrypted = sealed_box.decrypt(encrypted)
        return decrypted.decode()


class AccountManager:
    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager

    def create_account(self, username: str, password: str, public_key: PublicKey) -> dict:
        accounts = self.load_yaml()

        # 使用 SealedBox 加密密碼
        encrypted_password = self.key_manager.encrypt_password(public_key, password)

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
        decrypted_password = self.key_manager.decrypt_password(private_key, encrypted_password)
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
            print("Account not found1.")
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
                encrypted_password = self.key_manager.encrypt_password(public_key, new_password)
                accounts[new_username or old_username]["encrypted_password"] = encrypted_password

            self.save_yaml(accounts)
            print(f"Account {old_username} has been updated.")
        else:
            print(f"{old_username in accounts}")
            print(f"{old_username, accounts.keys()}")
            print("Account not found2.")
        return accounts

    def delete_account(self, private_key: PrivateKey, username: str) -> dict:
        accounts = self.load_yaml()

        if username in accounts:
            password = getpass.getpass("Please enter the password: ")
            if not self.verify_password(username, password, private_key):
                return accounts

            confirm_delete = questionary.select(
                f"Are you sure you want to delete the account {username}?",
                choices=[
                    "Cancel",
                    "Confirm",
                ],
            ).ask()

            if confirm_delete == "Confirm":
                del accounts[username]
                self.save_yaml(accounts)
                print(f"Account {username} has been deleted.")
            else:
                print("Operation canceled.")
        else:
            print("Account not found3.")

        return accounts

    def save_yaml(self, data: dict) -> None:
        filename = os.path.join(ConfigManager.get_system_config_dir(), "accounts.yaml")
        with open(filename, "w") as file:
            yaml.dump(data, file, default_flow_style=False)

    def load_yaml(self) -> dict:
        filename = os.path.join(ConfigManager.get_system_config_dir(), "accounts.yaml")
        try:
            with open(filename) as file:
                return yaml.load(file, Loader=yaml.FullLoader) or {}
        except FileNotFoundError:
            return {}
