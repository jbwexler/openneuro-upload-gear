#!/usr/bin/env python3

import flywheel
import flywheel_gear_toolkit
import logging
from shutil import copyfile,copytree,ignore_patterns
import os.path
import os
import pygit2
import json
import subprocess
from urllib.parse import urlparse
import sys

def openneuro_callbacks():
    parse = urlparse(ds_url)
    command = './node_modules/.bin/openneuro git-credential fill <<EOF\nprotocol=%s\nhost=%s\npath=%s\nEOF' % (parse.scheme, parse.netloc, parse.path)
    stdout = subprocess.run(command, shell=True, stdout=subprocess.PIPE).stdout
    stdout_str = stdout.decode('ascii')
    stdout_split = [x.split('=') for x in stdout_str.splitlines()]
    credentials_dict = {k:v for [k,v] in stdout_split}
    credentials = pygit2.UserPass(credentials_dict['username'], credentials_dict['password'])
    callbacks = pygit2.RemoteCallbacks(credentials=credentials)
    return callbacks
    
def git_add_all_commit():
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
    message = '[Flywheel Gear] Adding new data from flywheel'
    tree = index.write_tree()
    repo.create_commit(ref, author, committer, message, tree, parents)
    
def bids_validate(bids_path, ddjson_warn=False):
    if ddjson_warn == True:
        config_path = 'bids-validator-config_ddjson-warn.json'
    else:
        config_path = '../../bids-validator-config_ddjson-err.json'
    command = 'bids-validator %s -c %s' % (bids_path, config_path)
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE)
    return_code = result.returncode
    stdout = result.stdout.decode('ascii')
    if return_code == 1:
        print(stdout)
        sys.exit(1)

# From https://stackoverflow.com/a/42544963
def find_large_objects():
    cutoff = 2**20 * 10 # 10mb
    command = '''
    git rev-list --objects --all |
      git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
      sed -n 's/^blob //p' |
      sort --numeric-sort --key=2
    ''' # Convert to pygit2
    stdout = subprocess.run(command, shell=True, stdout=subprocess.PIPE).stdout.decode('ascii')
    files = [x.split() for x in stdout.splitlines()]
    large_files = [[x,int(y),z] for [x,y,z] in files if int(y) > cutoff]
    if len(large_files) > 0:
        print(large_files)
        sys.exit(1)

def get_bids_data(gtk_context):
    destination_id = gtk_context.config_json['destination']['id']
    job_level = gtk_context.client.get(destination_id)['parent']['type']
    if job_level in ('session', 'subject'):
        bids_path = gtk_context.download_session_bids()
    else:
        bids_path = gtk_context.download_project_bids()
    return bids_path
         
with flywheel_gear_toolkit.GearToolkitContext() as gtk_context:
   gtk_context.init_logging()
   gtk_context.log_config()
   bids_path = get_bids_data(gtk_context)
   config = gtk_context.config
   work_dir = gtk_context.work_dir

get_bids_data()
#bids_path = '/flywheel/v0/test_bids_ds'
bids_validate(bids_path, ddjson_warn=True)

ds_url = os.path.join(config['openneuro_url'], 'git', str(config['git_worker_number']), config['accession_number'])
ds_path = os.path.join(work_dir, config['accession_number'])
openneuro_config_dict = {"url":config['openneuro_url'], "apikey":config['openneuro_api_key'], "errorReporting":True}
with open('/root/.openneuro', 'w') as write_file:
    json.dump(openneuro_config_dict, write_file)

#import pdb; pdb.set_trace()
callbacks = openneuro_callbacks()
repo = pygit2.clone_repository(ds_url, ds_path, callbacks=callbacks)
repo.remotes['origin'].fetch(['git-annex:git-annex'], callbacks=callbacks)
os.chdir(ds_path)
command = 'git annex initremote openneuro type=external externaltype=openneuro encryption=none url=%s' % ds_url
subprocess.run(command, shell=True)
copytree(bids_path, ds_path, dirs_exist_ok=True, ignore=ignore_patterns('dataset_description.json'))
if not os.path.isfile(os.path.join(ds_path,'dataset_description.json')):
    copyfile(os.path.join(bids_path,'dataset_description.json'), os.path.join(ds_path,'dataset_description.json'))
# else: json.dumps to create our own dataset_description.json and copy in
command = 'git annex add .'
subprocess.run(command, shell=True)
git_add_all_commit()
bids_validate(ds_path, False)
find_large_objects()
# git push main and git-annex
import pdb; pdb.set_trace()
