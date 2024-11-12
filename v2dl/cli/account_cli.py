# cli interface of _password.py
import getpass
import logging
import os
import platform
import sys
from collections import OrderedDict
from typing import Any

import questionary
from nacl.public import PrivateKey, PublicKey

from ..utils.security import AccountManager, KeyManager


def display_menu() -> Any:
    choices = [
        {"name": "Create Account", "value": "create"},
        {"name": "Read Account", "value": "read"},
        {"name": "Update Account", "value": "update"},
        {"name": "Delete Account", "value": "delete"},
        {"name": "Password Test", "value": "password"},
        {"name": "List All Accounts", "value": "list"},
        {"name": "Quit", "value": "quit"},
    ]

    answer = questionary.select("Please choose an action:", choices=choices).ask()
    return answer


def clean_terminal() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def create_account(am: AccountManager, public_key: PublicKey) -> None:
    clean_terminal()
    print("Create Account")
    username = input("Please enter the username: ")
    if username == "":
        return
    password = get_pass("Please enter the password: ")
    am.create(username, password, public_key)


def read_account(am: AccountManager) -> None:
    clean_terminal()
    print("Read Account")
    username = input("Please enter the username: ")
    account = am.read(username)
    if account:
        ordered_dict = OrderedDict()
        ordered_dict["username"] = username
        ordered_dict["encrypted_password"] = account["encrypted_password"]
        for key, value in account.items():
            if key not in ["username", "encrypted_password"]:
                ordered_dict[key] = value

        # Output OrderedDict
        for key, value in ordered_dict.items():
            print(f"{key}: {value}")
    else:
        print("Account not found.")


def update_account(am: AccountManager, public_key: PublicKey, private_key: PrivateKey) -> None:
    clean_terminal()
    print("Update Account")
    old_username = input("Please enter the old username: ")
    password = get_pass("Please enter the password: ")
    if not am.verify_password(old_username, password, private_key):
        return
    new_username = input("Please enter the new username (leave blank to not update): ")
    password = get_pass("Please enter the new password (leave blank to not update): ")
    am.edit(public_key, old_username, new_username, password)


def delete_account(am: AccountManager, private_key: PrivateKey) -> None:
    clean_terminal()
    print("Delete Account")
    username = input("Please enter the username: ")
    if username in am.accounts:
        password = get_pass("Please enter the password: ")
        if not am.verify_password(username, password, private_key):
            return

        confirm_delete = questionary.select(
            f"Are you sure you want to delete the account {username}?",
            choices=[
                "Confirm",
                "Cancel",
            ],
        ).ask()

        if confirm_delete == "Confirm":
            am.delete(username)
        else:
            print("Operation canceled.")
    else:
        print("Account not found.")


def password_test(am: AccountManager, private_key: PrivateKey) -> None:
    clean_terminal()
    print("Password Test")
    username = input("Please enter the username: ")
    account = am.read(username)
    if account:
        password = get_pass("Enter password: ")
        am.verify_password(username, password, private_key)
    else:
        print("Account not found.")


def list_accounts(am: AccountManager) -> None:
    clean_terminal()
    print("Account List")
    accounts = am.accounts
    if accounts:
        for username, info in accounts.items():
            print(
                f"Account: {username}, Exceed quota: {info['exceed_quota'] or 'Null'}, Exceed time: {info['exceed_time'] or 'Null'}, Created At: {info['created_at']}"
            )
    else:
        print("No accounts available.")


def get_pass(prompt="Password: "):
    if platform.system() == "Windows":
        return input(prompt)
    else:
        return getpass.getpass(prompt)


def cli() -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    clean_terminal()
    encryptor = KeyManager(logger)
    am = AccountManager(encryptor, logger)
    key_pair = encryptor.load_keys()
    private_key, public_key = key_pair.private_key, key_pair.public_key

    def execute_action(choice: str) -> bool:
        if choice == "create":
            create_account(am, public_key)
        elif choice == "read":
            read_account(am)
        elif choice == "update":
            update_account(am, public_key, private_key)
        elif choice == "delete":
            delete_account(am, private_key)
        elif choice == "password":
            password_test(am, private_key)
        elif choice == "list":
            list_accounts(am)
        elif choice == "quit":
            clean_terminal()
            print("Exiting the account management of v2dl.")
            return True
        else:
            print("Invalid choice, please try again.")
        return False

    while True:
        choice = display_menu()
        if execute_action(choice):
            break

    sys.exit(0)


if __name__ == "__main__":
    cli()
