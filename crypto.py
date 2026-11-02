"""Cifrado de API Keys en reposo."""

from cryptography.fernet import Fernet, InvalidToken


class KeyCipher:
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise ValueError("No se pudo descifrar la credencial almacenada") from exc
