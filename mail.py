import json
from tqdm import tqdm
from bs4 import BeautifulSoup
import logging

from auth import LoginClient


class MailLinkNotFoundError(Exception):
    ...


class Mail:
    def __init__(self, **kwargs):
        self.author_name = kwargs.get("author_name")
        self.author_address = kwargs.get("author_address")
        self.subject = kwargs.get("subject")
        self.date = kwargs.get("date")
        self.content = kwargs.get("content")
        self.attachments = kwargs.get("attachments")
        self.read_status = kwargs.get("read_status")
        self.read_link = kwargs.get("read_link")
        self.size = kwargs.get("size")
        self.number = kwargs.get("number")

    def __str__(self):
        return f"Mail {self.subject!r} from {self.author_name} at {self.date}"

    def add_info(self, **kwargs):
        self.content = kwargs.get("content")
        self.attachments = kwargs.get("attachments")

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


class LernSaxMailClient:
    def __init__(self, auth_client: LoginClient):
        self.auth_client = auth_client
        self.session = self.auth_client.session
        self.mail_link = None
        self.mails = []
        self.mail_page: str = ""

    # get link to mail page from base page
    def get_mail_link(self):
        print("obtaining link to mail page")

        soup = BeautifulSoup(self.auth_client.logged_in_page.text, features="html.parser")
        links = [link for link in soup.find_all("a") if link.text.strip() == "Mail service"]
        if not links:
            raise MailLinkNotFoundError("The link to the mail overview can't be found.")
        self.mail_link = "https://www.lernsax.de/wws/" + links[0]["href"]

    # crawl html from mail link
    def get_startpage(self):
        print(f"checking mail page")
        r = self.session.get(self.mail_link)
        self.mail_page = r.text
        print(f"checked mail for {self.auth_client.email}")

    # parse all mails from a mail page into the objects
    def parse_mail_page(self, mail_page_text: str):
        soup = BeautifulSoup(mail_page_text, features="html.parser")
        c = soup.find("div", {"class": "jail_table"})
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
            self.mails.append(Mail(**{
                "read_status": read_status,
                "read_link": mail.find("td", {"class": "c_subj"}).find("a")["data-popup"],
                "subject": mail.find("td", {"class": "c_subj"}).find("a").text.strip(),
                "author_name": mail.find("td", {"class": "c_from"}).find("span").text.strip(),
                "author_address": mail.find("td", {"class": "c_from"}).find("span")["title"],
                "size": mail.find("td", {"class": "c_size"}).text.strip(),
                "date": mail.find("td", {"class": "c_date"}).text.strip(),
                "number": mail.find("td", {"class": "c_cb"}).find("input")["name"].split("[")[1].split("]")[0],
                "content": None,
            }))
            # TIMESTAMPS; NUMBERS MISSING!!!
        return self.mails

    # links to other mail pages in current folder
    def find_other_mail_pages(self):
        soup = BeautifulSoup(self.mail_page, features="html.parser")
        c = soup.find("p", {"class": "pages"})
        c = c.find_all("a")
        mail_pages = [[x["href"], x.text.strip()] for x in c if x.text.strip()]
        self.other_links = mail_pages
        return mail_pages

    # crawl html of other mail pages
    def get_all_mail_pages(self):
        self.find_other_mail_pages()
        self.mail_page_data = [self.mail_page]
        for page in self.other_links:
            self.mail_page_data.append(self.session.get("https://www.lernsax.de" + page[0]).text)
        return self.mail_page_data

    def get_all_mails(self):
        self.get_all_mail_pages()
        for page in self.mail_page_data:
            self.parse_mail_page(mail_page_text=page)

    def parse_all_mails(self):
        for mail in tqdm(self.mails):
            self.parse_mail(mail)

    # get a mail html by url
    def get_mail(self, mail: Mail):
        r = self.session.get("https://www.lernsax.de/wws/" + mail.read_link)
        return r.text

    # parse a mail by link into the Mail object
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
            "content": str(soup.find("p", {"class": "panel"})).replace("<br/>", "\n")
        }
        if len(tr) != 5:
            mail_data["attachments"] = [
                [att.find("a")["href"], att.find_all("a")[-1].text.strip()] for att in tr[-2].find_all("div")[:-1]
            ]
        mail.add_info(**mail_data)

    # send a mail
    def send_mail(self, receiver: list[str], cc: list[str] = None, bcc: list[str] = None, **kwargs):
        cc = cc if cc else []
        bcc = bcc if bcc else []
        subject = kwargs.get("subject", f"Mail to {receiver}")
        body = kwargs.get("body", f"Hello {receiver}")
        self.get_startpage()
        c = BeautifulSoup(self.mail_page, features="html.parser")
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
    # MASSIV REFACTORING NEEDED
    def find_mail_folders(self):
        print(f"finding mail folders for {self.auth_client.email}")
        self.get_startpage()
        mail_soup = BeautifulSoup(self.mail_page, features="html.parser")
        folder_dropdown = mail_soup.find("select", {"name": "select_folder"})
        folder_options = folder_dropdown.find_all("option")
        # print(folder_options)
        folders = [{folder.get("id"), folder.text.strip(), folder.get("value")} for folder in folder_options]
        print(f"found {len(folders)} folders for {self.auth_client.email}")
        print(folders)
        self.mail = {
            "folders": folders,
        }


if __name__ == "__main__":
    logging.basicConfig(level="INFO")

    auth = LoginClient.from_creds("zas")
    auth.login()
    client = LernSaxMailClient(auth)
    client.get_mail_link()
    client.get_startpage()
    client.get_all_mails()
    client.parse_all_mails()
    with open("mails.json", "w+") as f:
        json.dump(render_mail_list(client.mails), f, indent=4, ensure_ascii=False)

    # client.parse_mail_page(client.mail_page)
    # client.parse_all_mails()
    # start = time.perf_counter()
    """
    import time
    from tqdm import tqdm
    for i in tqdm(range(1000)):
        # client.send_mail()
        client.send_mail(receiver="lorenz.marc@wog.lernsax.de", subject=f"test{i}", body="test")
        time.sleep(0.5)  # without it, not all mails get delivered
    # print(f"runtime: {round(time.perf_counter() - start, 2)}s")"""
    

