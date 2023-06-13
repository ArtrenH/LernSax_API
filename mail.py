import json
import os
import requests
import logging
from tqdm import tqdm
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

from auth import LoginClient


class MailLinkNotFoundError(Exception):
    ...


class Mail:
    def __init__(self, **kwargs):
        self.author_name = kwargs.get("author_name")
        self.author_address = kwargs.get("author_address")
        self.recipient_name = kwargs.get("recipient_name")
        self.recipient_address = kwargs.get("recipient_address")
        self.subject = kwargs.get("subject")
        self.date = kwargs.get("date")
        self.content = kwargs.get("content")
        self.attachments = kwargs.get("attachments", [])
        self.read_status = kwargs.get("read_status")
        self.read_link = kwargs.get("read_link")
        self.size = kwargs.get("size")
        self.number = kwargs.get("number")

    def __str__(self):
        if self.recipient_name:
            return f"<Mail {self.subject!r} to {self.recipient_name} at date {self.date}>"
        return f"<Mail {self.subject!r} by {self.author_name} at date {self.date}>"

    def __repr__(self):
        return self.__str__()

    def add_info(self, **kwargs):
        self.content = kwargs.get("content")
        self.attachments = kwargs.get("attachments", [])

    def to_json(self) -> dict:
        return {
            "author_name": self.author_name,
            "author_address": self.author_address,
            "subject": self.subject,
            "date": self.date,
            "content": self.content,
            "attachments": self.attachments,
            "read_status": self.read_status,
            "size": self.size,
            "number": self.number
        }


def render_mail_list(mails: list[Mail]):
    return [mail.to_json() for mail in mails]


class WebMailClient:
    def __init__(self, auth_client: LoginClient):
        self.auth_client: LoginClient = auth_client
        self._logger = logging.getLogger(self.__class__.__name__)
        self.session: requests.Session = self.auth_client.session
        self.initial_mail_link: str = ""
        self.mail_links: list[str] = []
        self.mail_pages: list[str] = []
        self.mails: list[Mail] = []
        self.folders: dict = {}

        self.os_folder = f"{self.auth_client.downloads_folder}/mail/inbox"
        self.attachments_folder = f"{self.os_folder}/attachments"
        os.makedirs(self.attachments_folder, exist_ok=True)

    # loading mails from file
    def load_mails_from_json(self):
        self._logger.info(" -> loading mails from json...")

        with open(f"{self.auth_client.downloads_folder}/mails.json", "r") as f:
            mail_json = json.load(f)
        self.mails = [Mail(**elem) for elem in mail_json]

    # INITIALISING
    def get_mail_link(self):
        self._logger.info(" -> extracting link to mail page")

        soup = BeautifulSoup(self.auth_client.logged_in_page.text, features="html.parser")
        links = [link for link in soup.find_all("a") if link.text.strip() == "Mail service"]
        if not links:
            raise MailLinkNotFoundError("The link to the mail overview can't be found.")
        self.initial_mail_link = "https://www.lernsax.de/wws/" + links[0]["href"]

    def get_initial_page(self):
        self._logger.info(" -> visiting mail page")

        r = self.session.get(self.initial_mail_link)
        self.mail_pages = [r.text]
        self.mails = []

    def get_refresh_link(self):
        self._logger.info(" -> extracting refresh link")

        soup = BeautifulSoup(self.mail_pages[0], features="html.parser")
        link = soup.find("a", {"class": "q_105592_1025 block_link_intent_refresh"}).get("href")
        if not link:
            raise MailLinkNotFoundError("Refresh link could not be found.")
        self.initial_mail_link = "https://www.lernsax.de" + link

    def refresh(self):
        self._logger.info(" -> refreshing mail page")

        self.get_refresh_link()
        self.get_initial_page()

    # links to other mail pages in current folder
    def find_other_mail_pages(self):
        self._logger.info("-> extracting links to further mails")

        soup = BeautifulSoup(self.mail_pages[0], features="html.parser")
        c = soup.find("p", {"class": "pages"})
        if not c:
            self.mail_links = []
            return self.mail_links
        c = c.find_all("a")
        self.mail_links = [[x["href"], x.text.strip()] for x in c if x.text.strip()]
        return self.mail_links

    # crawl html of other mail pages
    def get_all_mail_pages(self):
        self._logger.info(" -> visiting all mail pages")
        self.find_other_mail_pages()
        for page in self.mail_links:
            self.mail_pages.append(self.session.get("https://www.lernsax.de" + page[0]).text)
        return self.mail_pages

    # get a mail html by url
    def get_mail(self, mail: Mail):
        r = self.session.get("https://www.lernsax.de/wws/" + mail.read_link)
        return r.text

    # HTML PARSING
    def parse_all_mail_pages(self):
        self._logger.info(" -> parsing all mail pages")

        for page in self.mail_pages:
            self.parse_mail_page(mail_page_text=page)

    def parse_mail_page(self, mail_page_text: str):
        soup = BeautifulSoup(mail_page_text, features="html.parser")
        c = soup.find("div", {"class": "jail_table"})
        if not c:
            return self.mails
        mails_html = c.find("tbody").find_all("tr")
        for mail in mails_html:
            # structure: [flagged_status, answered_status, read_status]
            read_status = {
                "../pics/mail_0.svg": [False, False, False],
                "../pics/mail_1.svg": [False, False, True],
                "../pics/mail_2.svg": [False, True, False],
                "../pics/mail_3.svg": [False, True, True],
                "../pics/mail_4.svg": [True, False, False],
                "../pics/mail_5.svg": [True, False, True],
                "../pics/mail_6.svg": [True, True, False],
                "../pics/mail_7.svg": [True, True, True]
            }.get(mail.find("td", {"class": "c_env"}).find("img")["src"], ["unidentified"]*3)
            author_part = mail.find("td", {"class": "c_from"})
            recipient_part = mail.find("td", {"class": "c_to"})
            self.mails.append(Mail(**{
                "read_status": read_status,
                "read_link": mail.find("td", {"class": "c_subj"}).find("a")["data-popup"],
                "subject": mail.find("td", {"class": "c_subj"}).find("a").text.strip(),
                "author_name": author_part.find("span").text.strip() if author_part else "",
                "author_address": author_part.find("span")["title"] if author_part else "",
                "recipient_name": recipient_part.find("span").text.strip() if recipient_part else "",
                "recipient_address": recipient_part.find("span")["title"] if recipient_part else "",
                "size": mail.find("td", {"class": "c_size"}).text.strip(),
                "date": mail.find("td", {"class": "c_date"}).text.strip(),
                "number": mail.find("td", {"class": "c_cb"}).find("input")["name"].split("[")[1].split("]")[0],
                "content": None,
            }))
        return self.mails

    def parse_all_mails(self):
        self._logger.info(" -> downloading all mails")

        for mail in tqdm(self.mails):
            self.parse_mail(mail)

    def parse_mail(self, mail: Mail):
        mail_txt = self.get_mail(mail)
        soup = BeautifulSoup(mail_txt, features="html.parser")
        metadata_table = soup.find("table", {"class": "table_lr"})
        tr = metadata_table.find_all("tr")
        mail_data = {
            "date": tr[1].find("td", {"class": "data"}).text.strip(),
            "sender": tr[0].find("span")["title"],
            "recipient": [span["title"] for span in tr[2].find_all("span")],
            "subject": tr[3].find("td", {"class", "data"}).text.strip(),
            "eml_link": tr[-1].find("a")["href"],
            "content": str(soup.find("p", {"class": "panel"})).replace("<br/>", "\n"),
            "attachments": [],
        }
        if len(tr) != 5:
            mail_data["attachments"] = [
                att.find("a")["href"] for att in tr[-2].find_all("div")[:-1]
            ]
            mail_data["attachments"] = [
                parse_qs(urlparse(url).query).get("path")[0] for url in mail_data["attachments"] if url != "#"
            ]
        mail.add_info(**mail_data)

    # DOWNLOAD HANDLING
    def download_attachment(self, path: str):
        r = self.session.get(f"https://d.lernsax.de/download.php?path={path}")
        # first number in path is random and useless for storage
        path = f"{self.attachments_folder}/{'/'.join(path.split('/', 2)[2:])}"
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(r.content)

    def dump_mails(self):
        mails = render_mail_list(self.mails)
        with open(f"{self.os_folder}/mails.json", "w+") as f:
            json.dump(mails, f, indent=4, ensure_ascii=False)
        for mail in tqdm(self.mails):
            for attachment in mail.attachments:
                self.download_attachment(attachment)

    # SEND HANDLING
    def send_mail(self, receiver: list[str], cc: list[str] = None, bcc: list[str] = None, **kwargs):
        cc = cc if cc else []
        bcc = bcc if bcc else []
        subject = kwargs.get("subject", f"Mail to {receiver}")
        body = kwargs.get("body", f"Hello {receiver}")
        self.get_initial_page()
        c = BeautifulSoup(self.mail_pages[0], features="html.parser")
        links = c.find_all("a", {"class": "q_105592_1026"})
        c = self.session.get("https://www.lernsax.de/wws/" + links[0]["data-popup"])
        refresh_link = c.text.split("var refresh_url=")[1].split(";")[0][1:-1]
        payload = {
            "call_no": "1",
            "reply": "",
            "reply_all": "",
            "forward": "",
            "mail_id": "",
            "mail_folder": "",
            "file_ids": "",
            "confirm_loose_form_changes": "1",
            "lock_to": "",
            "lock_subject": "",
            "in_reply_to": "",
            "to": " ".join(receiver),
            "cc": " ".join(cc),
            "bcc": " ".join(bcc),
            "subject": subject,
            "body": body,
            "file[]": "(binary)",
            "send_mail": "Send e-mail",
        }
        self.session.post("https://www.lernsax.de" + refresh_link, data=payload)

    # FOLDER HANDLING
    def find_mail_folders(self):
        self._logger.info(" -> finding mail folders")
        self.get_initial_page()
        mail_soup = BeautifulSoup(self.mail_pages[0], features="html.parser")
        folder_dropdown = mail_soup.find("select", {"name": "select_folder"})
        folder_options = folder_dropdown.find_all("option")
        self.folders = {
            folder.get("id", "").replace("option_", ""): {
                "description": folder.text.strip(),
                "url": "https://www.lernsax.de" + folder.get("value")
            } for folder in folder_options
        }

    def switch_mail_folder(self, folder: str):
        self._logger.info(f" -> switching to mail folder {folder!r}")

        self.initial_mail_link = self.folders[folder]["url"]
        self.get_initial_page()

        self.os_folder = f"{self.auth_client.downloads_folder}/mail/{folder}"
        self.attachments_folder = f"{self.os_folder}/attachments"
        os.makedirs(self.attachments_folder, exist_ok=True)

    # download EVERYTHING
    def download_everything(self):
        self._logger.info(" -> downloading EVERYTHING")
        self.get_mail_link()
        self.get_initial_page()
        self.find_mail_folders()
        for cur_folder in self.folders:
            self._logger.info(f" -> downloading folder {cur_folder}")
            self.switch_mail_folder(cur_folder)
            self.get_all_mail_pages()
            self.parse_all_mail_pages()
            self.parse_all_mails()
            self.dump_mails()


if __name__ == "__main__":
    logging.basicConfig(level="INFO")

    auth = LoginClient.from_creds("zas")
    auth.login()
    self = WebMailClient(auth)
    self.download_everything()

    # client.send_mail(receiver="", subject=f"test", body="test")
