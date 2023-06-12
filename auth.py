import requests
import json
from bs4 import BeautifulSoup
import logging
import re


class MissingUserInfoError(Exception):
    ...


class UnsuccessfulLoginError(Exception):
    ...


class NoIframeFoundError(Exception):
    ...


class LoginClient:
    def __init__(self, email: str, password: str):
        self.logged_in_page = None
        self._logger = logging.getLogger(self.__class__.__name__)
        if not email or not password:
            raise MissingUserInfoError("User not valid or found")
        self.session = requests.session()
        self.links = {
             "init_url": "https://www.lernsax.de",
         }

        self.email = email
        self.password = password

    @classmethod
    def from_creds(cls, identifier):
        with open("creds.json", "r") as f:
            creds = json.load(f)
        user = creds.get(identifier, {})
        return cls(user.get("username", ""), user.get("password", ""))

    def get_site_visit_redirect_url(self):
        self._logger.info(" -> Visiting https://www.lernsax.de/ and retrieving redirect url...")

        r = self.session.get("https://www.lernsax.de")

        return (
            "https://www.lernsax.de"
            + re.search(r"top\.location\.replace\('(?P<redirect_url>.*)'\)", r.text).group("redirect_url")
        )

    def resolve_php_redirect(self, url: str) -> str:
        self._logger.info(f" -> Resolving redirect url {url!r}...")

        r = self.session.get(url, allow_redirects=False)
        return "https://www.lernsax.de/wws/" + r.headers["Location"].split("#")[-1]

    def get_iframe_link(self, url: str) -> str:
        self._logger.info(f" -> Getting link of iframe...")

        r = self.session.get(url)
        soup = BeautifulSoup(r.text, features="html.parser")
        for link in soup.find_all("a"):
            if link.get("href", "").startswith("100001.php"):
                return "https://www.lernsax.de/wws/" + link["href"]

        raise NoIframeFoundError()

    def perform_login(self, login_url: str) -> requests.Response:
        self._logger.info(" -> Performing login...")

        payload = {
            "login_login": self.email,
            "login_password": self.password,
            "login_submit": "Login",
            "language": 1
        }
        r = self.session.post(login_url, data=payload)

        if "msgbox('The login data could not be found in the database.');" in r.text:
            raise UnsuccessfulLoginError("Login unsuccessful")

        self._logger.info(f" * Successfully logged in as {self.email!r}")

        self.logged_in_page = r
        return r

    def login(self) -> requests.Response:
        self._logger.info(f" * Initializing session for {self.email!r}...")

        redirect_url = self.get_site_visit_redirect_url()
        login_page_url = self.resolve_php_redirect(redirect_url)
        login_page_iframe_url = self.get_iframe_link(login_page_url)
        return self.perform_login(login_page_iframe_url)


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    #c = LoginClient(email="<your email>", password="<your password>")
    c = LoginClient.from_creds("zas")
    c.login()
