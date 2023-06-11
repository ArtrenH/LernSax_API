from doctest import ELLIPSIS_MARKER
import time
import bs4
import requests, json
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from auth import LernSaxAuthClient

# used to get and parse mails
class LernSaxMailClient(LernSaxAuthClient):
    # MAIL STUFF
    # finished --> receives the mail page with all the necessary links
    def check_mail(self):
        self.mails = []
        self.all_mails = []
        print(f"checking mail for {self.username}")
        if not self.login_startpage:
            self.login()
        if not self.login_success:
            return {"error": "couldn't log into LernSax"}
        
        soup = BeautifulSoup(self.login_startpage.text, features="html.parser")
        links = soup.find_all("a")
        self.mail_link = ""
        for link in links:
            if link.text.strip() == "Mail service":
                self.mail_link = "https://www.lernsax.de/wws/" + link["href"]
                break
        if not self.mail_link:
            return False
        self.links["mail"] = {"links": [self.mail_link]}
        r = self.session.get(self.mail_link)
        self.mail_page = r
        print(f"checked mail for {self.username}")
        return r
    # not yet finished --> extracts the urls for the different folders
    def find_mail_folders(self):
        print(f"finding mail folders for {self.username}")
        self.check_mail()
        mail_soup = BeautifulSoup(self.mail_page.text, features="html.parser")
        possible_folder_dropdowns = mail_soup.find_all("select", {"name": "select_folder"})
        if len(possible_folder_dropdowns) != 1:
            return {"error": "Website has changed so that the dropdown-menu for the folders can not be found..."}
        folder_dropdown = possible_folder_dropdowns[0]
        folder_options = folder_dropdown.find_all("option")
        #print(folder_options)
        folders = []
        for folder in folder_options:
            if not "id" in folder.attrs:
                continue
            folders.append({
                "id": folder["id"],
                "name": folder.text.strip(),
                "link": folder["value"]
            })
        
        print(f"found {len(folders)} folders for {self.username}")
        print(folders)
        
        
        #print(r.text)
        """
        idea for structure for objet self.mail: list of folders, whenever a folder is opened, the mails that get retrieved from the server are added as well as the links to the pages below (for example 1-17 cause not all mails are rendered at the same time)
        """
        self.mail = {
            "folders": folders,
        }
    # IT FUCKING WORKS MAN
    def send_mail(self, **kwargs):
        # receivers, cc, bcc
        receiver = kwargs.get("receiver", self.username)
        if isinstance(receiver, str): receiver = [receiver]
        if not isinstance(receiver, list): return {"error": "wrong receiver list format"}
        cc = kwargs.get("cc", [])
        if isinstance(cc, str): cc = [cc]
        if not isinstance(cc, list): return {"error": "wrong cc list format"}
        bcc = kwargs.get("bcc", [])
        if isinstance(bcc, str): bcc = [bcc]
        if not isinstance(bcc, list): return {"error": "wrong bcc list format"}
        
        subject = kwargs.get("subject", f"Mail to {receiver}")
        body = kwargs.get("body", f"Hello {receiver}")
        self.check_mail()
        c = BeautifulSoup(self.mail_page.text)
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
        r = self.session.post("https://www.lernsax.de" + refresh_link, data=payload)
        # METHOD FOR VALIDATING THE RESPONSE
        print(r)
        
    # finding other pages (for example links to 1-10 at the bottom)
    def find_other_mail_pages(self):
        self.check_mail()
        with open("html_examples/mail.html", "w+") as f:
            f.write(self.mail_page.text)
        soup = BeautifulSoup(self.mail_page.text, features="html.parser")
        c = soup.find("p", {"class": "pages"})
        c = c.find_all("a")
        mail_pages = [[x["href"], x.text.strip()] for x in c if x.text.strip()]
        self.mail_pages = mail_pages
        return mail_pages
        
    def get_all_mail_pages(self):
        self.find_other_mail_pages()
        self.mail_page_data = [self.mail_page]
        for page in self.mail_pages:
            self.mail_page_data.append(self.session.get("https://www.lernsax.de" + page[0]))
        return self.mail_page_data
    
    
        
    
    def get_mails(self, **kwargs):
        # for other mail pages (other pages)
        if "mail_page_text" in kwargs:
            mail_page_text = kwargs["mail_page_text"]
        else:
            self.check_mail()
            mail_page_text = self.mail_page.text
        soup = BeautifulSoup(mail_page_text, features="html.parser")
        # the grid: <div class="jail_table">
        c = soup.find("div", {"class": "jail_table"})
        mails_html = c.find("tbody").find_all("tr")
        for mail in mails_html:
            #possible_states = {"../pics/mail_0.svg": "unread","../pics/mail_1.svg": "read","../pics/mail_2.svg": "unread, answered","../pics/mail_3.svg": "answered","../pics/mail_4.svg": "unread, flagged","../pics/mail_5.svg": "flagged","../pics/mail_6.svg": "unread, flagged, answered","../pics/mail_7.svg": "flagged, answered"}
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
            }.get(mail.find("td", {"class": "c_env"}).find("img")["src"], ["unidentified","unidentified", "unidentified"])
            read_link = mail.find("td", {"class": "c_subj"}).find("a")["data-popup"]
            subject = mail.find("td", {"class": "c_subj"}).find("a").text.strip()
            author_name = mail.find("td", {"class": "c_from"}).find("span").text.strip()
            author_address = mail.find("td", {"class": "c_from"}).find("span")["title"]
            size = mail.find("td", {"class": "c_size"}).text.strip()
            date = mail.find("td", {"class": "c_date"}).text.strip()
            number = mail.find("td", {"class": "c_cb"}).find("input")["name"].split("[")[1].split("]")[0]
            self.mails.append([number, read_link, read_status, subject, author_name, author_address, size, date])
            # TIMESTAMPS; NUMBERS MISSING!!!
        with open("json_tests/mail.json", "w+") as f:
            json.dump(self.mails, f, indent=4)
        return self.mails
    
    def get_all_emails(self):
        self.get_all_mail_pages()
        for page in self.mail_page_data:
            self.get_mails(mail_page_text=page.text)
    
    def parse_mail(self, **kwargs):
        if "mail_link" in kwargs:
            mail_link = kwargs["mail_link"]
        else:
            self.get_mails()
            mail_link = self.mails[0][1]
        r = self.session.get("https://www.lernsax.de/wws/" + mail_link)
        with open("html_examples/mail_view_3.html", "w+") as f:
            f.write(r.text)
        soup = BeautifulSoup(r.text, features="html.parser")
        metadata_table = soup.find("table", {"class": "table_lr"})
        tr = metadata_table.find_all("tr")
        mail_data = {
            "date": tr[1].find("td", {"class": "data"}).text.strip(),
            "sender": tr[0].find("span")["title"], # sometimes, in that part, we can find USERIDS!!!
            "recipient": [span["title"] for span in tr[2].find_all("span")],
            "subject": tr[3].find("td", {"class", "data"}).text.strip(),
            "eml_link": tr[-1].find("a")["href"], # eml size not extracted
            "attachments": [],
            "content": str(soup.find("p", {"class": "panel"})).replace('<p class="panel">', '').replace('</p>', '').replace("<br/>", "\n")
        }
        if len(tr) != 5:
            mail_data["attachments"] = [[att.find("a")["href"], att.find_all("a")[-1].text.strip()] for att in tr[-2].find_all("div")[:-1]] # last div is message about viruses
        mail_data = [mail_data[elem] for elem in mail_data]
        if mail_data not in self.all_mails:
            self.all_mails.append(mail_data)
        with open("json_tests/mails_parsed.json", "w+") as f:
            json.dump(self.all_mails, f, indent=4)
        return self.all_mails


    def parse_all_mails(self, **kwargs):
        self.get_all_emails()
        for ind, mail in enumerate(self.mails):
            print(ind, len(self.mails))
            self.parse_mail(mail_link=mail[1])
        
    def get_latest_mails(self, folder):
        pass
    def get_all_mails(self, folder):
        pass
    def show_mail_folder(self, folder_id):
        self.find_mail_folders()
    


if __name__ == "__main__":
    client = LernSaxMailClient()
    client.parse_mail()
    #client.parse_all_mails()
    """start = time.perf_counter()
    for i in range(1):
        client.send_mail()
        #client.send_mail(receiver="lorenz.marc@wog.lernsax.de", subject=f"test{i}", body="test")
        time.sleep(0.5) # without it, not all mails get delivered
    print(f"runtime: {round(time.perf_counter() - start, 2)}s")"""
    

