#!/usr/bin/env python3

import flywheel
import logging
import datalad.api as dl
from shutil import copyfile
import subprocess

context = flywheel.GearContext()  # Get the gear context
config = context.config           # from the gear context, get the config settings

#Initialize logging and set its level
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)

git_config_path = context.get_input_path('git-config')
copyfile(git_config_path,'/root/.gitconfig')
git_config_path = context.get_input_path('openneuro-config')
copyfile(git_config_path,'/root/.openneuro')

#print(dir(context))
bids_path = context.download_project_bids()

if config['new_dataset'] == 'yes': 
    bashCommand = "cat config.json"
    process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()
    print(output)