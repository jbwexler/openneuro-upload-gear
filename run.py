#!/usr/bin/env python3

import flywheel
import logging

context = flywheel.GearContext()  # Get the gear context
config = context.config           # from the gear context, get the config settings

#Initialize logging and set its level
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)

## Load in values from the gear configuration
datalad