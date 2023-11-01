#!/usr/bin/env python3

import flywheel
import flywheel_gear_toolkit
import logging
import datalad.api as dl
from shutil import copyfile
import os.path
import os
import pygit2

with flywheel_gear_toolkit.GearToolkitContext() as gtk_context:
   # Setup basic logging
   gtk_context.init_logging()

   # Log the configuration for this job
   gtk_context.log_config()


config = gtk_context.config

accession_number = config['accession_number']
git_config_path = gtk_context.get_input_path('git-config')
copyfile(git_config_path,'/root/.gitconfig')
openneuro_config_path = gtk_context.get_input_path('openneuro-config')
copyfile(openneuro_config_path,'/root/.openneuro')

bids_path = gtk_context.download_session_bids()

if config['new_dataset'] == 'yes':
    ds_path = os.path.join(gtk_context.work_dir,'new_dataset')
    dl.create(path=ds_path)
    repo_obj = pygit2.Repository(ds_path)
    copyfile(os.path.join('/flywheel/v0','gitattributes.txt'),os.path.join(ds_path,'.gitattributes'))
    #copyfile(os.path.join(gtk_context.work_dir,'gitattributes.txt'),os.path.join(ds_path,'.gitattributes'))
    repo_obj.config.set_multivar('credential.useHttpPath','', 'true')
    repo_obj.config.set_multivar('credential.helper','','/path/to/openneuro git-credential')
else:
    ds_path = os.path.join(gtk_context.work_dir,accession_number)
    dl.clone('https://github.com/OpenNeuroDatasets/%s.git' % accession_number)
    repo_obj = pygit2.Repository(ds_path)
    repo_obj.config.set_multivar('safe.directory','', '/flywheel/v0')
