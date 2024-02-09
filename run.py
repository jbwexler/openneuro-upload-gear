#!/usr/bin/env python3

import flywheel_gear_toolkit
import logging
import shutil
import os.path
import os
import pygit2
import json
import subprocess
import sys
import contextlib
import requests
from urllib.parse import urlparse


log = logging.getLogger(__name__)

FW_PATH = "/flywheel/v0/"
BIDS_VERSION = "1.9.0"


def graphql_query(query, openneuro_url, openneuro_api_key):
    headers = {"Content-Type": "application/json"}
    cookies = {"accessToken": openneuro_api_key}
    url = os.path.join(openneuro_url, "crn/graphql")
    json={"query": query}
    response = requests.post(url, headers=headers, json=json, cookies=cookies)
    return response.json()

def get_git_worker_number(accession_number, openneuro_url, openneuro_api_key):
    query = """
    query {
        dataset(id: "accession_number") {
            worker
        }
    }
    """.replace("accession_number", accession_number)

    response_json = graphql_query(query, openneuro_url, openneuro_api_key)
    git_worker_number = str(response_json["data"]["dataset"]["worker"][-1])
    return git_worker_number
    

def new_dataset_query(openneuro_url, openneuro_api_key):
    try:
        affirmed_defaced = config["defaced"].split(":")[0]
    except KeyError:
        print("'generate_new_dataset' is true but an entry for 'defaced' was not provided.")
        sys.exit(1)
        
    query = """
    mutation {
      createDataset(affirmedDefaced: affirmed_defaced) {
        id
      }
    }
    """.replace("affirmed_defaced", affirmed_defaced)
    
    response_json = graphql_query(query, openneuro_url, openneuro_api_key)  
    accession_number = response_json["data"]["createDataset"]["id"]
    return accession_number


def copy_tree(src, dst, ignore=[]):
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_tree(s, d)
        elif os.path.isfile(s):
            if item in ignore:
                continue
            with contextlib.suppress(FileNotFoundError):
                os.remove(d)
            shutil.copyfile(s, d)


def openneuro_callbacks(ds_url):
    parse = urlparse(ds_url)
    command = (
        "./node_modules/.bin/openneuro git-credential fill <<EOF\nprotocol=%s\nhost=%s\npath=%s\nEOF"
        % (parse.scheme, parse.netloc, parse.path)
    )
    stdout = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, check=True
    ).stdout
    stdout_str = stdout.decode()
    stdout_split = [x.split("=") for x in stdout_str.splitlines()]
    credentials_dict = {k: v for [k, v] in stdout_split}
    credentials = pygit2.UserPass(
        credentials_dict["username"], credentials_dict["password"]
    )
    callbacks = pygit2.RemoteCallbacks(credentials=credentials)
    return credentials, callbacks


def git_add_all_commit(repo):
    git_config = pygit2.Config.get_global_config()
    name = git_config["user.name"]
    email = git_config["user.email"]
    author = pygit2.Signature(name, email)
    committer = pygit2.Signature(name, email)

    ref = repo.head.name
    parents = [repo.head.target]
    index = repo.index
    index.add_all()
    index.write()
    message = "[Flywheel Gear] Adding new data from flywheel"
    tree = index.write_tree()
    repo.create_commit(ref, author, committer, message, tree, parents)


def bids_validate(bids_path, ddjson_warn=False):
    if ddjson_warn is True:
        config_path = os.path.join(FW_PATH, "bids-validator-config_ddjson-warn.json")
    else:
        config_path = os.path.join(FW_PATH, "bids-validator-config_ddjson-err.json")
    config_path_rel = os.path.relpath(config_path, bids_path)

    command = "bids-validator %s -c %s" % (bids_path, config_path_rel)
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE)
    return_code = result.returncode
    stdout = result.stdout.decode()
    if return_code == 1:
        print(stdout)
        sys.exit(1)


def find_large_objects(ds_path):
    """
    Checks to make sure large objects (over 10mb) aren't stored in Git.
    This is both to ensure good git performance and to make sure files
    accidentally containing private data can later be purged via git-annex.
    """
    cutoff = 2**20 * 10  # 10mb
    # From https://stackoverflow.com/a/42544963
    command = """
    git -C {ds_path} rev-list --objects --all |
      git -C {ds_path} cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
      sed -n 's/^blob //p' |
      sort --numeric-sort --key=2
    """.format(ds_path=ds_path)  # Convert to pygit2
    stdout = subprocess.run(command, shell=True, stdout=subprocess.PIPE).stdout.decode()
    files = [x.split() for x in stdout.splitlines()]
    large_files = [[x, int(y), z] for [x, y, z] in files if int(y) > cutoff]
    if len(large_files) > 0:
        print(large_files)
        raise Exception("Large files were found in git.")


def get_bids_data(accession_number):
    job_level = client.get(destination_id)["parent"]["type"]
    data_id = client.get(destination_id)["parents"][job_level]
    if job_level == "session":
        sessions = [client.get_session(data_id)]
    elif job_level == "subject":
        subject = client.get_subject(data_id)
        sessions = subject.sessions()
    elif job_level == "project":
        project = client.get_project(data_id)
        sessions = [s for s in project.sessions() if accession_number not in s.tags]
    session_labels = [s.label for s in sessions]
    if not session_labels:
        if not gtk_context.get_input_path("dataset_description"):
            error_message = """ 
            No data was uploaded because either:
            1) No bidsified data was found
            2) All sessions contain the tag '{accession_number}'. This gear is 
            running at the project level, which means it will exclude sessions 
            that contain a tag matching the accession number. To upload specific 
            sessions, you may run this gear at the session or subject level, or 
            remove the '{accession_number}' tag and rerun at the project level.
            """.format(accession_number=accession_number)
            print(' '.join(error_message.split()))
            sys.exit(1)
        else:
            return None, sessions
    bids_path = gtk_context.download_project_bids(sessions=session_labels)
    return bids_path, sessions


def cp_bids_data(bids_path, ds_path):
    copy_tree(bids_path, ds_path, ignore=["dataset_description.json"])
    ddjson_path_on = os.path.join(ds_path, "dataset_description.json")
    ddjson_path_fw = gtk_context.get_input_path("dataset_description")
    if ddjson_path_fw:
        with contextlib.suppress(FileNotFoundError):
            os.remove(ddjson_path_on)
        shutil.copyfile(ddjson_path_fw, ddjson_path_on)
    elif not os.path.isfile(ddjson_path_on):
        ddjson_dict = project_info["BIDS"]
        ddjson_dict.pop("rule_id", None)
        ddjson_dict.pop("template", None)
        ddjson_dict = {k: v for k, v in ddjson_dict.items() if v}
        with open(ddjson_path_on, "w") as write_file:
            json.dump(ddjson_dict, write_file)

def get_config():
    openneuro_url = "https://openneuro.org" # Default value
    if "openneuro-upload" in project_info:
        if "accession_number" in project_info["openneuro-upload"]:
            accession_number = project_info["openneuro-upload"]["accession_number"]
        if "openneuro_api_key" in project_info["openneuro-upload"]:
            openneuro_api_key = project_info["openneuro-upload"]["openneuro_api_key"]
        if "openneuro_url" in project_info["openneuro-upload"]:
            openneuro_url = project_info["openneuro-upload"]["openneuro_url"]
    if config:
        if "accession_number" in config:
            accession_number = config["accession_number"]
        if "openneuro_api_key" in config:
            openneuro_api_key = config["openneuro_api_key"]
        if "openneuro_url" in config:
            openneuro_url = config["openneuro_url"]
    if not openneuro_url.endswith("/"):
        openneuro_url = openneuro_url + "/"
    if config["generate_new_dataset"]:
        accession_number = None
    return accession_number, openneuro_api_key, openneuro_url

def upload(accession_number, openneuro_api_key, openneuro_url):
    git_worker_number = get_git_worker_number(
        accession_number, openneuro_url, openneuro_api_key
    )
    ds_url = os.path.join(
        openneuro_url,
        "git",
        git_worker_number,
        accession_number,
    )
    ds_path = os.path.join(work_dir, accession_number)
    openneuro_config_dict = {
        "url": openneuro_url,
        "apikey": openneuro_api_key,
        "errorReporting": True,
    }
    with open("/root/.openneuro", "w") as write_file:
        json.dump(openneuro_config_dict, write_file)

    # Validate flywheel data
    bids_path, sessions = get_bids_data(accession_number)
    if bids_path:
        bids_validate(bids_path, ddjson_warn=True)

    # Setup openneuro dataset
    credentials, callbacks = openneuro_callbacks(ds_url)
    repo = pygit2.clone_repository(ds_url, ds_path, callbacks=callbacks)
    repo.remotes["origin"].fetch(["git-annex:git-annex"], callbacks=callbacks)
    command = (
        "git -C %s annex initremote openneuro type=external externaltype=openneuro encryption=none url=%s"
        % (ds_path, ds_url)
    )
    subprocess.run(command, shell=True, check=True)

    # Add new data
    cp_bids_data(bids_path, ds_path)
    command = "git -C %s annex add ." % ds_path
    subprocess.run(command, shell=True, check=True)
    git_add_all_commit(repo)

    # Perform checks
    # bids_validate(ds_path)
    find_large_objects(ds_path)

    # Push to openneuro
    command = "git -C %s push origin main" % ds_path
    subprocess.run(command, shell=True, check=True)
    command = "git -C %s annex copy --to openneuro" % ds_path
    subprocess.run(command, shell=True, check=True)

    # Tag sessions after upload
    for s in sessions:
        if accession_number not in s.tags:
            s.add_tag(accession_number)
            
    return project_id, accession_number, openneuro_api_key
    
def update_project_info(accession_number, openneuro_api_key, openneuro_url):
    new_info = {
        "openneuro-upload": {
            "accession_number": accession_number,
            "openneuro_api_key": openneuro_api_key,
            "openneuro_url": openneuro_url
        }
    }
    
    project = gtk_context.client.get_project(project_id)
    project.update_info(new_info)

def main():
    gtk_context.init_logging()
    gtk_context.log_config()
    
    accession_number, openneuro_api_key, openneuro_url = get_config()
    
    if config["generate_new_dataset"]:
        accession_number = new_dataset_query(openneuro_url, openneuro_api_key)
        print("Generated new OpenNeuro accession number: %s" % accession_number)
    if not config["skip_upload"]:
        upload(accession_number, openneuro_api_key, openneuro_url)
    if gtk_context.config["copy_to_project_info"]:
        update_project_info(accession_number, openneuro_api_key, openneuro_url)
        
if __name__ == "__main__":
    with flywheel_gear_toolkit.GearToolkitContext() as gtk_context:
        config = gtk_context.config
        work_dir = gtk_context.work_dir
        client = gtk_context.client

        destination_id = gtk_context.config_json["destination"]["id"]
        project_id = client.get(destination_id)["parents"]["project"]
        project_info = client.get_project(project_id)["info"]
        
        main()
