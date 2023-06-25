import logging
import requests
from webdav3.client import Client

from auth import LoginClient


class WebDAVClient:
    def __init__(self, auth_client: LoginClient):
        self.auth_client = auth_client
        options = {
            "webdav_hostname": "https://www.lernsax.de/webdav.php",
            "webdav_login": self.auth_client.email,
            "webdav_password": self.auth_client.password,
        }
        self.client = Client(options)

    def list(self, directory: str = "/"):
        i = self.client.list(directory)
        print(i)

    def map_dirs(self):
        ...


if __name__ == "__main__":
    logging.basicConfig(level="INFO")

    auth = LoginClient.from_creds("zas")
    auth.login()

    client = WebDAVClient(auth)
    client.list()
