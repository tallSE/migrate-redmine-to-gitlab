#!/usr/bin/env python3
from __future__ import unicode_literals

import os

from setuptools import setup

try:
    README = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()
except IOError:
    README = ''

setup(
    name='migrate-redmine-to-gitlab',
    version='2.0.2',
    description='Migrate a redmine project to Gitlab',
    long_description=README,
    author='Tony Chemit',
    author_email='dev@tchemit.fr',
    license='GPL',
    url='https://github/ultreia-io/migrate-redmine-to-gitlab',
    packages=['migrate_redmine_to_gitlab'],
    install_requires=['requests'],
    entry_points={
        'console_scripts': [
            'migrate-redmine-to-gitlab = migrate_redmine_to_gitlab.commands:main'
        ]
    },
    test_suite='migrate_redmine_to_gitlab.tests',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)'
    ]
)
