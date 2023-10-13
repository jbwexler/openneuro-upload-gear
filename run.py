#!/usr/bin/env python3

import flywheel
import logging
import datalad.api as dl

context = flywheel.GearContext()  # Get the gear context
config = context.config           # from the gear context, get the config settings

#Initialize logging and set its level
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)

## Load in values from the gear configuration
print(config)
#dl.clone('https://github.com/OpenNeuroDatasets/ds000001.git')
print('yoooooo')