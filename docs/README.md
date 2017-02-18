# Redmine to Gitlab migrator

[![Build Status](https://travis-ci.org/ultreia-io/migrate-redmine-to-gitlab.svg?branch=master)](https://travis-ci.org/ultreia-io/migrate-redmine-to-gitlab) [![PyPI version](https://badge.fury.io/py/migrate-redmine-to-gitlab.svg)](https://badge.fury.io/py/migrate-redmine-to-gitlab)

Migrate Redmine projects to Gitlab.

Enjoy.

## Does

- Per-project migrations
- Migration of issues, keeping as much metadata as possible:
  - redmine trackers become tags
  - an extra Redmine tag is added on each issue
  - issues comments are kept and assigned to the right users
  - issues final status (open/closed) are kept along with open/close date (not
    detailed status history)
  - issues assignments are kept
  - issues numbers (ex: `#123`)
  - issues/notes authors
  - issue/notes original dates, but as comments
  - issue/attachments
  - relations (although gitlab model for relations is simpler)
- Migration of Versions/Roadmaps keeping:
  - issues composing the version
  - statuses & due dates

## Does not

- Migrate users, groups, and permissions (redmine ACL model is complex and
  cannot be transposed 1-1 to gitlab ACL)
- Migrate repositories (piece of cake to do by hand, + redmine allows multiple
  repositories per project where gitlab does not)
- Migrate wikis (because we don't use them at @oasiswork, feel free to contribute)
- Migrate the whole redmine installation at once, because namespacing is different in
  redmine and gitlab
- Archive the redmine project for you
- Keep creation/edit dates as metadata
- Keep "watchers" on tickets (gitlab API v3 does not expose it)
- Keep dates/times as metadata
- Keep track of issue relations orientation (no such notion on gitlab)
- Remember who closed the issue
- Migrate tags ([redmine_tags](https://www.redmine.org/plugins/redmine_tags)
  plugin), as they are not exposed in gitlab API

## Requires

- Python >= 3.4
- gitlab >= 7.0
- redmine >= 1.3
- Admin token on redmine
- Admin token on gitlab
- No preexisting issues on gitlab project
- Already synced users (those required in the project you are migrating)

(It was developed/tested around redmine 3.3, gitlab 8.2.0, python 3.4)

## Credits

Many thanks to the @oasiswork team for the good work they have done with the project 
https://github.com/oasiswork/redmine-gitlab-migrator on which this project is based on.


# Install

You can or can not use
[virtualenvs](http://docs.python-guide.org/en/latest/dev/virtualenvs/), that's
up to you.

Install it:

    pip install migrate-redmine-to-gitlab


(or if you cloned the git: `python setup.py install`)

    migrate-redmine-to-gitlab --help

# Migrate a project

This process is for each project, **order matters**.

For the example we will migrate project observe from [Code Lutin Redmine](https://forge.codelutin.com/projects/observe) to
[Ultreia.io Gitlab](https://gitlab.com/ultreia.io/ird-observe).

## Create the gitlab project

It does not need to be named the same, you just have to record it's URL.

Add users to your project (we will se later how to map redmine users to them).

Note that if a redmine user can't be found in gitlab, the issue/comment will be
assigned to the gitlab admin user.

Import git repository.

Important note: **The project must have NO milestone and NO issue.**

## Init migration

Create a directory, go in it.

``
mkdir observe
cd observe
``

Create a **config.json** file with this content _(adapt content with your credentials)_:
 
 ```
 {
  "redmine": { "url":"https://forge.codelutin.com/projects/observe", "key": "XXX" },
  "gitlab": { "url":"https://gitlab.com/ultreia.io/ird-observe", "key": "XXX" }  
}
 ```

Launch command

``
python3 migrate-redmine-to-gitlab init
``

This will download all the redmine project stuff in direcytoy **redmine**

You should have then a such directory layout:

```
observe
├── config.json
└── redmine
    ├── attachments
    ├── issues
    ├── project.json
    ├── users
    └── versions
```

## Adapt users

The directory **redmine/users** contains all users from the Redmine project. 

To match a gitlab user, you need to set the login attribute in each file to the gitlab login.

Note that you won't be able to continue migration process until all redmine users match any of one gitlab user.

## Migrate Roadmap

``
python3 migrate-redmine-to-gitlab roadmap --check
``

*(remove `--check` to perform it for real)*

## Migrate Attachments

``
python3 migrate-redmine-to-gitlab attachments --check
``

*(remove `--check` to perform it for real)*

## Migrate issues (without adding redmine id in title)

``
python3 migrate-redmine-to-gitlab issues --check
``

*(remove `--check` to perform it for real)*

## Migrate issues (with adding redmine id in title)

``
python3 migrate-redmine-to-gitlab issues-with-id --check
``

*(remove `--check` to perform it for real)*

Note that your issue titles will be annotated with the original redmine issue
ID, like *-RM-1186-MR-logging*. This annotation will be used (and removed) by
the next step.

## Migrate Issues ID (iid) (optional)

You can retain the issues ID from redmine, **this cannot be done via REST
API**, thus it requires **direct access to the gitlab machine**.

So you have to log in the gitlab machine (eg. via SSH), and then issue the
command with sufficient rights, from there:

``
python3 migrate-redmine-to-gitlab iid --check
``

*(remove `--check` to perform it for real)*

## After all

Once all this steps has been performed, the project is fully loaded in GitLab.

Note that redmine caches files has been linked to the GitLab resources; this means that we can now perform operations 
from both applications.

I intend to add a last command to send to redmine a note on each version and issue with his migrated url on GitLab.

Should be done soon...

## Delete all issues of a project

An extra command I develop while testing issues imports. You should not use this command.

``
python3 migrate-redmine-to-gitlab delete-issues
``
