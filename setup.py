#!/usr/bin/env python
from __future__ import unicode_literals

import os
from setuptools import setup

try:
    README = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()
except IOError:
    README = ''

setup(
    name='redmine-gitlab-migrate',
    version='2.0.1',
    description='Migrate a redmine project to gitlab',
    long_description=README,
    author='Tony Chemit',
    author_email='dev@tchemit.fr',
    license='GPL',
    url='https://github/ultreia-io/redmine-to-gitlab-migrator/',
    packages=['redmine_gitlab_migrator'],
    install_requires=['requests'],
    entry_points={
        'console_scripts': [
            'migrate-rg = redmine_gitlab_migrator.commands:main'
        ]
    },
    test_suite='redmine_gitlab_migrator.tests',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)'
    ]
)
