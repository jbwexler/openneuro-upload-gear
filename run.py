#!/usr/bin/env python3

import flywheel_gear_toolkit
import logging
import shutil
import os.path
import os
import pygit2
import json
import subprocess
from urllib.parse import urlparse
import sys
import contextlib

log = logging.getLogger(__name__)

FW_PATH = '/flywheel/v0/'
BIDS_VERSION = "1.8.0"

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
    stdout = subprocess.run(command, shell=True, stdout=subprocess.PIPE, check=True).stdout
    stdout_str = stdout.decode("ascii")
    stdout_split = [x.split("=") for x in stdout_str.splitlines()]
    credentials_dict = {k: v for [k, v] in stdout_split}
    credentials = pygit2.UserPass(credentials_dict["username"], credentials_dict["password"])
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
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, check=True)
    return_code = result.returncode
    stdout = result.stdout.decode("ascii")
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
    stdout = subprocess.run(command, shell=True, stdout=subprocess.PIPE).stdout.decode("ascii")
    files = [x.split() for x in stdout.splitlines()]
    large_files = [[x, int(y), z] for [x, y, z] in files if int(y) > cutoff]
    if len(large_files) > 0:
        print(large_files)
        sys.exit(1)


def get_bids_data(gtk_context):
    cl = gtk_context.client
    destination_id = gtk_context.config_json["destination"]["id"]
    job_level = cl.get(destination_id)["parent"]["type"]
    data_id = cl.get(destination_id)["parents"][job_level]
    if job_level == "session":
        sessions = [cl.get_session(data_id)]
    elif job_level == "subject":
        subject = cl.get_subject(data_id)
        sessions = subject.sessions()
    elif job_level == "project":
        project = cl.get_project(data_id)
        sessions = [s for s in project.sessions() if "openneuro" not in s.tags]
    session_labels = [s.label for s in sessions]
    bids_path = gtk_context.download_project_bids(sessions=session_labels)
    return bids_path, sessions


def cp_bids_data(bids_path, ds_path):
    copy_tree(bids_path, ds_path, ignore=['dataset_description.json'])
    ddjson_path_on = os.path.join(ds_path, "dataset_description.json")
    ddjson_path_fw = os.path.join(bids_path, "dataset_description.json")
    if not os.path.isfile(ddjson_path_on):
        if os.path.isfile(ddjson_path_fw):
            shutil.copyfile(ddjson_path_fw, ddjson_path_on)
        else:
            ddjson_dict = {
                "Name": "WBHI",
                "BIDSVersion": BIDS_VERSION,
                "Authors": ["Emily Jacobs"],
            }
            with open(ddjson_path_on, "w") as write_file:
                json.dump(ddjson_dict, write_file)

def main(gear_context):
    gtk_context.init_logging()
    gtk_context.log_config()
    config = gtk_context.config
    work_dir = gtk_context.work_dir

    ds_url = os.path.join(
        config["openneuro_url"],
        "git",
        str(config["git_worker_number"]),
        config["accession_number"],
    )
    ds_path = os.path.join(work_dir, config["accession_number"])
    openneuro_config_dict = {
        "url": config["openneuro_url"],
        "apikey": config["openneuro_api_key"],
        "errorReporting": True,
    }
    with open("/root/.openneuro", "w") as write_file:
        json.dump(openneuro_config_dict, write_file)

    # Validate flywheel data
    bids_path, sessions = get_bids_data(gtk_context)
    #bids_path = "/flywheel/v0/test_bids_ds"
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
    bids_validate(ds_path)
    find_large_objects(ds_path)

    # Push to openneuro
    command = "git -C %s push origin main" % ds_path
    subprocess.run(command, shell=True, check=True)
    command = "git -C %s annex copy --to openneuro" % ds_path
    subprocess.run(command, shell=True, check=True)
    
    # Tag sessions after upload
    for s in sessions:
        s.add_tag('openneuro')
        

if __name__ == "__main__":
    with flywheel_gear_toolkit.GearToolkitContext() as gtk_context:
        main(gtk_context)
