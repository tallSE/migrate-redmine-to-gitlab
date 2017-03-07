#!/bin/env python3

import os
import logging
import json

log = logging.getLogger(__name__)


class MigrationConfig:
    def __init__(self):
        config_file = 'config.json'
        if not os.path.exists(os.path.join('.', config_file)):
            raise FileNotFoundError
        with open(config_file, 'r') as outfile:
            data = json.load(outfile)
        log.debug('config: {}'.format(data))
        self.redmine_host = data['redmine']['host']
        self.redmine_project_url = self.redmine_host + '/' + data['redmine']['path']
        self.redmine_key = data['redmine']['key']
        self.gitlab_host = data['gitlab']['host']
        self.gitlab_project_url = self.gitlab_host + '/' + data['gitlab']['path']
        self.gitlab_key = data['gitlab']['key']
        self.cache_dir = os.path.join('.', 'redmine')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            log.info('Create cache dir: {}'.format(self.cache_dir))
