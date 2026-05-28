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


def graphql_query(query, openneuro_url, openneuro_api_key):
    headers = {"Content-Type": "application/json"}
    cookies = {"accessToken": openneuro_api_key}
    url = os.path.join(openneuro_url, "crn/graphql")
    response = requests.post(
        url, headers=headers, json={"query": query}, cookies=cookies
    )
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
        log.error(
            "'generate_new_dataset' is enabled but the 'defaced' config field was not "
            "provided. Set 'defaced' to indicate whether the dataset has been defaced "
            "before creating a new dataset."
        )
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


def openneuro_callbacks(ds_url, env):
    parse = urlparse(ds_url)
    stdout = subprocess.run(
        "openneuro git-credential get <<EOF\nprotocol=%s\nhost=%s\npath=%s\nEOF"
        % (parse.scheme, parse.netloc, parse.path),
        shell=True,
        stdout=subprocess.PIPE,
        check=True,
        env=env,
    ).stdout
    stdout_str = stdout.decode()
    stdout_pairs = [p for p in stdout_str.split("\n") if "=" in p]
    credentials_dict = dict(p.split("=", 1) for p in stdout_pairs)
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

    result = subprocess.run(
        "bids-validator %s -c %s" % (bids_path, config_path),
        shell=True,
        stdout=subprocess.PIPE,
    )
    return_code = result.returncode
    stdout = result.stdout.decode()
    if return_code == 1:
        log.error("BIDS validation failed for %s:\n%s", bids_path, stdout)
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
        formatted = "\n".join(
            "  %s  %d bytes  %s" % (sha, size, name) for sha, size, name in large_files
        )
        log.error(
            "Found %d file(s) larger than 10MB tracked in git. Remove them from history "
            "before uploading:\n%s",
            len(large_files),
            formatted,
        )
        sys.exit(1)


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
            log.error(
                "No sessions available to upload. Either no BIDS data was found, or "
                "every session is already tagged with the accession number '%s'. When "
                "this gear runs at the project level, it skips sessions tagged with the "
                "accession number; to upload specific sessions, rerun at the session or "
                "subject level, or remove the '%s' tag and rerun at the project level.",
                accession_number,
                accession_number,
            )
            sys.exit(1)
        else:
            return None, sessions
    bids_path = gtk_context.download_project_bids(sessions=session_labels)
    return bids_path, sessions


def strip_sessions(ds_path):
    """Remove the session level from the BIDS structure under ds_path.

    Moves files from sub-XX/ses-YY/<modality>/ up to sub-XX/<modality>/ and strips
    _ses-YY tokens from filenames. Exits with an error if any subject has more
    than one session, or if any subject-level sessions.tsv/.json files exist
    (the user must resolve those manually before stripping).
    """
    subjects = sorted(
        d
        for d in os.listdir(ds_path)
        if d.startswith("sub-") and os.path.isdir(os.path.join(ds_path, d))
    )

    multi_session = []
    sessions_files = []
    for subj in subjects:
        subj_dir = os.path.join(ds_path, subj)
        sessions = sorted(
            d
            for d in os.listdir(subj_dir)
            if d.startswith("ses-") and os.path.isdir(os.path.join(subj_dir, d))
        )
        if len(sessions) > 1:
            multi_session.append((subj, sessions))
        for fname in os.listdir(subj_dir):
            if fname.endswith("_sessions.tsv") or fname.endswith("_sessions.json"):
                sessions_files.append(os.path.join(subj, fname))

    fail = False
    if multi_session:
        formatted = "\n".join(
            "  %s: %s" % (subj, ", ".join(ses)) for subj, ses in multi_session
        )
        log.error(
            "Cannot strip sessions: %d subject(s) have more than one session, which "
            "would cause filename collisions after flattening. Affected subjects:\n%s",
            len(multi_session),
            formatted,
        )
        fail = True
    if sessions_files:
        log.error(
            "Cannot strip sessions: found %d subject-level sessions file(s). Remove "
            "or relocate them before enabling strip_sessions:\n%s",
            len(sessions_files),
            "\n".join("  " + p for p in sessions_files),
        )
        fail = True
    if fail:
        sys.exit(1)

    log.info(
        "Stripping session level from %d subject(s) under %s", len(subjects), ds_path
    )

    for subj in subjects:
        subj_dir = os.path.join(ds_path, subj)
        sessions = [
            d
            for d in os.listdir(subj_dir)
            if d.startswith("ses-") and os.path.isdir(os.path.join(subj_dir, d))
        ]
        if not sessions:
            continue

        ses_label = sessions[0]
        ses_dir = os.path.join(subj_dir, ses_label)
        ses_token = "_" + ses_label

        for root, _dirs, files in os.walk(ses_dir):
            rel = os.path.relpath(root, ses_dir)
            target_root = subj_dir if rel == "." else os.path.join(subj_dir, rel)
            os.makedirs(target_root, exist_ok=True)
            for f in files:
                new_name = f.replace(ses_token, "")
                shutil.move(os.path.join(root, f), os.path.join(target_root, new_name))

        shutil.rmtree(ses_dir)


def cp_bids_data(bids_path, ds_path):
    if bids_path:
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
    accession_number = None
    openneuro_api_key = None
    openneuro_url = "https://openneuro.org"
    if "openneuro-upload" in project_info:
        pi = project_info["openneuro-upload"]
        if pi.get("accession_number"):
            accession_number = pi["accession_number"]
        if pi.get("openneuro_api_key"):
            openneuro_api_key = pi["openneuro_api_key"]
        if pi.get("openneuro_url"):
            openneuro_url = pi["openneuro_url"]
    if config:
        if config.get("accession_number"):
            accession_number = config["accession_number"]
        if config.get("openneuro_api_key"):
            openneuro_api_key = config["openneuro_api_key"]
        if config.get("openneuro_url"):
            openneuro_url = config["openneuro_url"]
    openneuro_url = openneuro_url.rstrip("/")
    if config["generate_new_dataset"]:
        accession_number = None
    return accession_number, openneuro_api_key, openneuro_url


def upload(accession_number, openneuro_api_key, openneuro_url, env):
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

    # Validate flywheel data
    bids_path, sessions = get_bids_data(accession_number)
    if bids_path:
        bids_validate(bids_path, ddjson_warn=True)

    # Setup openneuro dataset
    if os.path.exists(ds_path):
        shutil.rmtree(ds_path)
    credentials, callbacks = openneuro_callbacks(ds_url, env)
    repo = pygit2.clone_repository(ds_url, ds_path, callbacks=callbacks)
    repo.remotes["origin"].fetch(["git-annex:git-annex"], callbacks=callbacks)
    subprocess.run(
        "git -C %s annex initremote openneuro type=external externaltype=openneuro encryption=none url=%s"
        % (ds_path, ds_url),
        shell=True,
        check=True,
        env=env,
    )

    # Add new data
    cp_bids_data(bids_path, ds_path)
    if config["strip_sessions"]:
        strip_sessions(ds_path)
    subprocess.run("git -C %s annex add ." % ds_path, shell=True, check=True, env=env)
    git_add_all_commit(repo)

    # Perform checks
    bids_validate(ds_path)
    find_large_objects(ds_path)

    # Push to openneuro
    subprocess.run(
        "git -C %s push origin main" % ds_path, shell=True, check=True, env=env
    )
    subprocess.run(
        "git -C %s annex copy --to openneuro" % ds_path, shell=True, check=True, env=env
    )

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
            "openneuro_url": openneuro_url,
        }
    }

    project = gtk_context.client.get_project(project_id)
    project.update_info(new_info)


def main():
    gtk_context.init_logging()
    gtk_context.log_config()

    accession_number, openneuro_api_key, openneuro_url = get_config()
    env = os.environ.copy()
    env["OPENNEURO_API_KEY"] = openneuro_api_key
    env["OPENNEURO_URL"] = openneuro_url
    subprocess.run(
        "openneuro login --error-reporting true", shell=True, check=True, env=env
    )

    if config["generate_new_dataset"]:
        accession_number = new_dataset_query(openneuro_url, openneuro_api_key)
        log.info("Generated new OpenNeuro accession number: %s", accession_number)
    if not config["skip_upload"]:
        upload(accession_number, openneuro_api_key, openneuro_url, env)
    if gtk_context.config["copy_to_project_info"]:
        update_project_info(accession_number, openneuro_api_key, openneuro_url)


if __name__ == "__main__":
    with flywheel_gear_toolkit.GearToolkitContext() as gtk_context:
        config = gtk_context.config
        work_dir = gtk_context.work_dir
        client = gtk_context.client

        destination_id = gtk_context.destination["id"]
        project_id = client.get(destination_id)["parents"]["project"]
        project_info = client.get_project(project_id)["info"]

        main()
