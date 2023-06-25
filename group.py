import requests, json
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import urllib

from auth import LernSaxAuthClient

class LernSaxGroupOverview():
    def __init__(self, name, url=None):
        self.name = name
        self.base_url = url

class LernSaxInstitution():
    def __init__(self, name, url=None):
        self.name = name
        self.base_url = url


class LernSaxGroupClass():
    def __init__(self, name, url=None):
        self.name = name
        #self.unicode_name = self.name.replace("ü", b"\u00fc")
        self.base_url = url
        self.folders = {
            self.name: {
                "name": self.name,
                "link": self.base_url,
                "folders": {}
            }
        }
        self.all_paths = []
            
    # TRY THIS FOR THE RELEVANT GRID: <div class="jail_table"> (NOT YET IMPLEMENTED)
    def get_folder(self, client, folder_url, folder_init=False):
        r = client.session.get("https://www.lernsax.de/wws/" + folder_url)
        with open("html_examples/file_storage.html", "w+") as f:
            f.write(r.text)
        cur_soup = BeautifulSoup(r.text, features="html.parser")
        table = cur_soup.find("table", {"class": "table_list"})
        #<table class="table_list space sort_skip_first">
        # for some reason, these links include "/wws" at the beginning for no reason -> we need [5:]
        all_links = table.find_all("td", {"class": "c_name"})
        cur_folder_link = table.find_all("tr", {"class": "files_item_folder_open"})
        folder_links = [link for link in table.find_all("tr", {"class": "files_item_folder"}) if link != cur_folder_link]
        next_folder_links = [[c.find("a").text.strip(), c.find("a")["href"][5:]] for c in folder_links]
        next_folders = {c[0]: {"name": c[0], "link": c[1], "is_file": False, "is_folder": True, "folders": {}} for c in next_folder_links}
        cur_keys = [elem for elem in next_folders]
        del next_folders[cur_keys[0]]

        print("folders:")
        print(next_folders)
        print("\n")
        
        file_links = table.find_all("tr", {"class": "files_item_file"})
        next_file_links = [[''.join(c["data-drag_downloadurl"].replace("application/pdf:", "").split(":https://www.lernsax.de/")[:-1]), c.find("a")["href"], c["data-drag_downloadurl"]] for c in file_links]
        next_files = {c[0]: {"name": c[0], "link": c[1], "data": c[2], "is_file": True, "is_folder": False} for c in next_file_links}
        print("files:")
        print(next_files)
        print("\n")
        
        further_links = [[c.find("a").text.strip(), c.find("a")["href"][5:]] for c in all_links]
        group_folders = {c[0]: {"name": c[0], "link": c[1], "folders": {}} for c in further_links}
        # the next 2 lines are there because a folder returns a link back to itself when requested IMPORTANT
        cur_keys = [elem for elem in group_folders]
        del group_folders[cur_keys[0]]
        if folder_init:
            self.folders[self.name]["folders"] = group_folders
        print("old method:")
        print(group_folders)
        print("\n")
        
        return group_folders
    
    def get_folders(self, client, folder_url, folder_init=True):
        self.get_folder(client, folder_url, folder_init=True)
        for folder in self.folders[self.name]["folders"]:
            cur_folder = self.folders[self.name]["folders"][folder]
            r = self.get_folder(client, folder_url=cur_folder["link"], folder_init=False)
            self.folders[self.name]["folders"][folder]["folders"] = r
        
        # FOLDER CURRENTLY CONTAIN THEMSELVES!!! --> THAT IS A PROBLEM
        with open("json_tests/folders.json", "w+") as f:
            json.dump(self.folders, f, indent=4)    
    
    def add_folders(self, folder_data):
        self.folders = folder_data
    
    
    
    def __str__(self) -> str:
        return self.name
    
    def __repr__(self) -> str:
        return f"LERNSAX-GRUOP-CLASS-OBJECT <{self.name}>"


class LernSaxGroup(LernSaxGroupClass):
    pass

class LernSaxClass(LernSaxGroupClass):
    pass

# used view groups
class LernSaxGroupClient(LernSaxAuthClient):
    # GROUP STUFF
    def get_user_groups(self):
        if not self.login_startpage:
            self.login()
        soup = BeautifulSoup(self.login_startpage.text, features="html.parser")
        group_select = soup.find_all("select", {"id": "top_select_18"})
        if len(group_select) != 1:
            return {"error": {"class": "API-Error", "description": "API has changed, more than one group select has been found"}}
        group_select = group_select[0]
        
        groups = group_select.find_all("option", {"class": "top_option"})
        
        # PUT HELPER INTO HERE
        self.group_select = group_select
        groups = {group.text.strip(): {"url": group["value"]} for group in groups if group["value"] != ""}
        self.groups = [LernSaxGroup(name=group, url=groups[group]['url']) for group in groups]
        return self.groups
    
    def get_user_classes(self):
        if not self.login_startpage:
            self.login()
        soup = BeautifulSoup(self.login_startpage.text, features="html.parser")
        class_select = soup.find_all("select", {"id": "top_select_19"})
        if len(class_select) != 1:
            return {"error": {"class": "API-Error", "description": "API has changed, more than one class select has been found"}}
        class_select = class_select[0]
        classes = class_select.find_all("option", {"class": "top_option"})
        self.class_select = class_select
        classes = {classx.text.strip(): {"url": classx["value"]} for classx in classes if classx["value"] != ""}
        self.classes = classes
        return classes
    
    def get_user_languages(self):
        if not self.login_startpage:
            self.login()
        soup = BeautifulSoup(self.login_startpage.text, features="html.parser")
        language_select = soup.find_all("select", {"name": "language"})
        if len(language_select) != 1:
            return {"error": {"class": "API-Error", "description": "API has changed, more than one language select has been found"}}
    
    
    # FOLDER STUFF
    def access_user_group(self, group_name):
        print(f"searching for group {group_name}")
        groups = self.get_user_groups()
        possible_groups = [group for group in groups if group.name == group_name]
        if len(possible_groups) == 0:
            print("error: group not found!")

            return {"error": "group not found"}
        group_url = possible_groups[0].base_url
        r = self.session.get("https://www.lernsax.de/wws/" + group_url)
        cur_soup = BeautifulSoup(r.text, features="html.parser")
        folder_url = cur_soup.find("li", { "id" : "menu_125520" }).find("a")["href"]
        
        possible_groups[0].get_folders(client=self, folder_url=folder_url)


if __name__ == "__main__":
    client = LernSaxGroupClient("henninger.arthur@wog.lernsax.de")
    #client.access_user_group('WOG-Schüler')
    print(client.get_user_groups())



