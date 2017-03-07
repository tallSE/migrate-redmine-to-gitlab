#!/bin/env python3
import argparse
import logging
import re

import subprocess

from migrate_redmine_to_gitlab import sql
from migrate_redmine_to_gitlab.config import MigrationConfig
from migrate_redmine_to_gitlab.converters import convert_issue, convert_version, convert_attachments
from migrate_redmine_to_gitlab.gitlab import GitlabClient, GitlabProject
from migrate_redmine_to_gitlab.logging import setup_module_logging
from migrate_redmine_to_gitlab.redmine import RedmineClient, RedmineProjectWithCache, RedmineProject, RedmineCacheWriter

"""Migration commands for issues and roadmaps from redmine to gitlab
"""

log = logging.getLogger(__name__)


class CommandError(Exception):
    """ An error that will nicely pop up to user and stops program
    """

    def __init__(self, msg):
        self.msg = msg


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command')
    commands = []

    init = subparsers.add_parser('init', help=Init.__doc__)
    init.set_defaults(command=Init)
    commands.append(init)

    roadmap = subparsers.add_parser('roadmap', help=Versions.__doc__)
    roadmap.set_defaults(command=Versions)
    commands.append(roadmap)

    attachments = subparsers.add_parser('attachments', help=Attachments.__doc__)
    attachments.set_defaults(command=Attachments)
    commands.append(attachments)

    issues = subparsers.add_parser('issues', help=Issues.__doc__)
    issues.set_defaults(command=Issues)
    commands.append(issues)

    issues_with_id = subparsers.add_parser('issues-with-id', help=IssuesWithId.__doc__)
    issues_with_id.set_defaults(command=IssuesWithId)
    commands.append(issues_with_id)

    delete_issues = subparsers.add_parser('delete-issues', help=DeleteIssues.__doc__)
    delete_issues.set_defaults(command=DeleteIssues)
    commands.append(delete_issues)

    link_roadmap = subparsers.add_parser('link-roadmap', help=LinkRedmineRoadmap.__doc__)
    link_roadmap.set_defaults(command=LinkRedmineRoadmap)
    commands.append(link_roadmap)

    link_issue = subparsers.add_parser('link-issues', help=LinkRedmineIssue.__doc__)
    link_issue.set_defaults(command=LinkRedmineIssue)
    commands.append(link_issue)

    iid = subparsers.add_parser('iid', help=Iid.__doc__)
    iid.set_defaults(command=Iid)
    commands.append(iid)

    for i in commands:
        i.add_argument('--check', required=False, action='store_true', default=False,
                       help="do not perform any action, just check everything is ready")
        i.add_argument('--debug', required=False, action='store_true', default=False, help="More output")

    return parser.parse_args()


def main():
    args = parse_args()
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # Configure global logging
    setup_module_logging('migrate_redmine_to_gitlab', level=log_level)

    config = MigrationConfig()

    try:
        args.command(config, args).run()
    except CommandError as e:
        log.error(e)
        exit(12)


class Command:
    def __init__(self, config, args):
        self.gitlab = None
        self.redmine = None
        self.args = args
        self.config = config
        log.info('Init {}'.format(self))

    def run(self):
        log.info('Run {}'.format(self))
        self.execute()
        log.info('End {}'.format(self))

    def check(self, func, message):
        # noinspection PyCallingNonCallable
        ret = func(redmine=self.redmine, gitlab=self.gitlab)
        if ret:
            log.info('{}... OK'.format(message))
        else:
            log.error('{}... FAILED'.format(message))
            exit(1)

    def redmine_project_with_cache(self):
        redmine_client = RedmineClient(self.config.redmine_key)
        return RedmineProjectWithCache(self.config.redmine_project_url, self.config.cache_dir, redmine_client)

    def redmine_project(self):
        redmine_client = RedmineClient(self.config.redmine_key)
        return RedmineProject(self.config.redmine_project_url, redmine_client)

    def gitlab_project(self):
        gitlab_client = GitlabClient(self.config.gitlab_key)
        return GitlabProject(self.config.gitlab_project_url, gitlab_client)

    def redmine_cache(self, redmine_project):
        return RedmineCacheWriter(self.config.cache_dir, redmine_project)

    def execute(self):
        pass


class Init(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.redmine = self.redmine_project()
        self.gitlab = self.gitlab_project()
        self.cache = self.redmine_cache(self.redmine)

    def execute(self):
        versions = self.cache.load_versions()
        log.info('{} version(s) loaded'.format(len(versions)))

        issues = self.cache.load_issues()
        log.info('{} issue(s) loaded'.format(len(issues)))

        users = self.cache.load_users(issues)
        log.info('{} user(s) loaded'.format(len(users)))

        attachments = self.cache.load_attachments(issues)
        log.info('{} attachment(s) loaded'.format(len(attachments)))


class Versions(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.redmine = self.redmine_project_with_cache()
        self.gitlab = self.gitlab_project()
        self.cache = self.redmine_cache(self.redmine)

        checks = [
            (self.check_no_milestone, 'Gitlab project has no pre-existing milestone'),
            (self.check_origin_milestone, 'Redmine project contains versions'),
        ]
        for i in checks:
            self.check(*i)

        self.redmine_versions = self.redmine.get_versions()
        log.info('Got {} version(s) from redmine.'.format(len(self.redmine_versions)))

    def execute(self):

        existing_gitlab_versions = self.gitlab.get_milestones_index().keys()

        versions_data = [convert_version(redmine_version) for redmine_version in self.redmine_versions]
        if self.args.check:
            for data, meta in versions_data:
                if not data['title'] in existing_gitlab_versions:
                    log.info("Would create version {}".format(data))
            return

        gitlab_versions = []
        created_versions, bad_versions = self._create_versions(versions_data, [], existing_gitlab_versions)
        gitlab_versions += created_versions
        while len(bad_versions) > 0:
            log.info('Some versions were not created: {}'.format(bad_versions))

            created_versions, bad_versions = self._create_versions(versions_data,
                                                                   bad_versions,
                                                                   existing_gitlab_versions)
            gitlab_versions += created_versions

        versions_index = {str(redmine_version['id']): redmine_version for redmine_version in self.redmine_versions}

        for gitlab_version in gitlab_versions:
            redmine_id = gitlab_version['redmine_id']
            redmine_version = versions_index[redmine_id]
            redmine_version['gitlab_id'] = gitlab_version['id']
            self.cache.load_version(redmine_version)

        log.info('{} version(s) created on GitLab'.format(len(gitlab_versions)))

    # noinspection PyUnusedLocal
    @staticmethod
    def check_origin_milestone(redmine, gitlab):
        return len(redmine.get_versions()) > 0

    # noinspection PyUnusedLocal
    @staticmethod
    def check_no_milestone(redmine, gitlab):
        return len(gitlab.get_milestones()) == 0

    def _create_versions(self, versions_data, incoming_bad_versions, existing_gitlab_versions):
        bad_versions = []
        created_versions = []
        for data, meta in versions_data:
            if data['title'] in existing_gitlab_versions:
                log.info("skip existing milestone {}".format(data['title']))
                pass
            log.debug(data)
            data_id = str(data['redmine_id'])
            if len(incoming_bad_versions) == 0 or data_id in incoming_bad_versions:
                # noinspection PyBroadException
                try:
                    created_version = self.gitlab.create_milestone(data, meta)
                    created_version['redmine_id'] = data_id
                    created_versions.append(created_version)
                    log.info("Version {}".format(created_version['title']))
                except:
                    log.error('Could not create version {}'.format(data_id))
                    bad_versions.append(data_id)
        return created_versions, bad_versions


class Attachments(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.redmine = self.redmine_project_with_cache()
        self.gitlab = self.gitlab_project()
        self.cache = self.redmine_cache(self.redmine)

        self.redmine_issues = self.redmine.get_all_issues()
        log.info('Got {} issue(s) from redmine.'.format(len(self.redmine_issues)))

        self.attachments_index = self.redmine.get_attachments_index()
        log.info('Got {} attachment(s) from redmine.'.format(len(self.attachments_index.values())))

    def execute(self):

        gitlab_id = self.gitlab.get_id()

        attachments_data = []

        for redmine_issue in self.redmine_issues:
            attachments_data += convert_attachments(redmine_issue, self.attachments_index, gitlab_id)

        if self.args.check:
            for data in attachments_data:
                log.info('Would create attachment "{}"'.format(data['redmine']['filename']))
            return

        gitlab_attachments = []
        created_attachments, bad_attachments = self._create_attachments(attachments_data, [])
        gitlab_attachments += created_attachments
        while len(bad_attachments) > 0:
            log.info('Some attachments were not created: {}'.format(bad_attachments))

            created_attachments, bad_attachments = self._create_attachments(attachments_data, bad_attachments)
            gitlab_attachments += created_attachments

        for attachment in gitlab_attachments:
            redmine_attachment = attachment['redmine']
            redmine_attachment['gitlab'] = attachment['gitlab']
            self.cache.load_attachment(redmine_attachment)

        log.info('{} attachments(s) created on GitLab'.format(len(gitlab_attachments)))

    def _create_attachments(self, attachments_data, incoming_bad_attachments):
        bad_attachments = []
        created_attachments = []
        for data in attachments_data:
            data_redmine_ = data['redmine']
            data_id = str(data_redmine_['id'])
            if len(incoming_bad_attachments) == 0 or data_id in incoming_bad_attachments:
                # noinspection PyBroadException
                try:
                    created_attachment = self.gitlab.create_attachment(data)
                    data['gitlab'] = created_attachment
                    created_attachments.append(data)
                    log.info("Created attachment (was: {}) {}".format(data_id, created_attachment['markdown']))
                except:
                    bad_attachments.append(data_id)
                    # noinspection SpellCheckingInspection
                    log.error(
                        'Could not create attachment {} {} (size: {})'.format(data_id, data_redmine_['filename'],
                                                                              data_redmine_['filesize']))
        return created_attachments, bad_attachments


class Issues(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.redmine = self.redmine_project_with_cache()
        self.gitlab = self.gitlab_project()
        self.cache = self.redmine_cache(self.redmine)

        self.gitlab_users_index = self.gitlab.get_users_index()
        log.info('Got {} users(s) from gitlab.'.format(len(self.gitlab_users_index.values())))

        self.redmine_users_index = self.redmine.get_users_index()
        log.info('Got {} users(s) from redmine.'.format(len(self.redmine_users_index.values())))

        checks = [
            (self.check_users, 'Required users presence'),
            (self.check_no_issue, 'Project has no pre-existing issue'),
        ]
        for i in checks:
            self.check(*i)

        self.redmine_issues = self.redmine.get_all_issues()
        log.info('Got {} issue(s) from redmine.'.format(len(self.redmine_issues)))

        self.attachments_index = self.redmine.get_attachments_index()
        log.info('Got {} attachment(s) from redmine.'.format(len(self.attachments_index.values())))

        self.milestones_index = self.gitlab.get_milestones_index()
        log.info('Got {} milestone(s) from gitlab.'.format(len(self.milestones_index.values())))

        self.gitlab_id = self.gitlab.get_id()

    def execute(self):

        issues_data = self._convert_issues()

        if self.args.check:
            for data, meta in issues_data:
                milestone_id = data.get('milestone_id', None)
                if milestone_id:
                    try:
                        self.gitlab.get_milestone_by_id(milestone_id)
                    except ValueError:
                        raise CommandError(
                            "issue \"{}\" points to unknown milestone_id \"{}\". "
                            "Check that you already migrated roadmaps".format(
                                data['title'], milestone_id))

                log.info(
                    'Would create issue "{}" with {} notes and {} attachments.'.format(data['title'],
                                                                                       len(meta['notes']),
                                                                                       len(meta['attachments'])))
            return

        gitlab_issues = []

        created_issues, bad_issues = self._create_issues(issues_data, [])
        gitlab_issues += created_issues
        while len(bad_issues) > 0:
            log.info('Some issues were not created: {}'.format(bad_issues))
            created_issues, bad_issues = self._create_issues(issues_data, bad_issues)
            gitlab_issues += created_issues

        issues_by_index = {str(redmine_issue['id']): redmine_issue for redmine_issue in self.redmine_issues}

        for gitlab_issue in gitlab_issues:
            redmine_id = gitlab_issue['redmine_id']
            redmine_issue = issues_by_index[redmine_id]
            redmine_issue['gitlab_id'] = gitlab_issue['iid']
            self.cache.load_issue(redmine_issue)
        log.info('{} issue(s) created on GitLab'.format(len(gitlab_issues)))

    def _convert_issues(self):
        return [
            convert_issue(redmine_issue,
                          self.redmine_users_index,
                          self.attachments_index,
                          self.gitlab_id,
                          self.gitlab_users_index,
                          self.milestones_index) for redmine_issue in self.redmine_issues]

    # noinspection PyUnusedLocal
    @staticmethod
    def check_no_issue(redmine, gitlab):
        return len(gitlab.get_issues()) == 0

    @staticmethod
    def check_users(redmine, gitlab):
        users = redmine.get_participants()
        # Filter out anonymous user
        nicks = set([i['login'] for i in users if i['login'] != ''])
        log.info('Project users are: {}'.format(', '.join(nicks) + ' '))

        gitlab_user_names = set([i['username'] for i in gitlab.get_all_users()])
        return all((i in gitlab_user_names for i in nicks))

    def _create_issues(self, issues_data, incoming_bad_issues):
        bad_issues = []
        created_issues = []
        for data, meta in issues_data:
            data_id = str(data['redmine_id'])
            if len(incoming_bad_issues) == 0 or data_id in incoming_bad_issues:
                # noinspection PyBroadException
                try:
                    created_issue = self.gitlab.create_issue(data, meta)
                    created_issue['redmine_id'] = data_id
                    created_issues.append(created_issue)
                    log.info("Created issue (was: {}) {}".format(data_id, created_issue['title']))
                except:
                    log.error('Could not create issue {}'.format(data_id))
                    bad_issues.append(data_id)
        return created_issues, bad_issues


class IssuesWithId(Issues):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)

    def _convert_issues(self):
        return [
            convert_issue(redmine_issue,
                          self.redmine_users_index,
                          self.attachments_index,
                          self.gitlab_id,
                          self.gitlab_users_index,
                          self.milestones_index,
                          with_id=True) for redmine_issue in self.redmine_issues]


class Iid(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.redmine = self.redmine_project_with_cache()
        self.gitlab = self.gitlab_project()
        self.cache = self.redmine_cache(self.redmine)

    def execute(self):

        gitlab_project_id = self.gitlab.get_id()

        regex_saved_iid = r'-RM-([0-9]+)-MR-(.*)'

        sql_cmd = sql.COUNT_UNMIGRATED_ISSUES.format(
            regex=regex_saved_iid, project_id=gitlab_project_id)

        output = sql.run_query(sql_cmd)

        try:
            m = re.match(r'\s*(\d+)\s*', output, re.DOTALL | re.MULTILINE)
            issues_count = int(m.group(1))
        except (AttributeError, ValueError):
            raise ValueError(
                'Invalid output from postgres command: "{}"'.format(output))

        if issues_count > 0:
            log.info('Ready to recover iid for {} issues.'.format(
                issues_count))
        else:
            log.error(
                "No issue to migrate iid, possible causes: "
                "you already migrated iid or you haven't migrated issues yet.")
            exit(1)

        if not self.args.check:
            sql_cmd = sql.MIGRATE_IID_ISSUES.format(
                regex=regex_saved_iid, project_id=gitlab_project_id)
            out = sql.run_query(sql_cmd)
            log.info(out)
            try:
                m = re.match(
                    r'\s*(\d+)\s*', output,
                    re.DOTALL | re.MULTILINE)
                migrated_count = int(m.group(1))
                log.info('Migrated successfully iid for {} issues'.format(
                    migrated_count))
            except (IndexError, AttributeError):
                raise ValueError(
                    'Invalid output from postgres command: "{}"'.format(output))


class DeleteIssues(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.gitlab = self.gitlab_project()

    def execute(self):
        log.info('Start {}'.format(self))

        gitlab_issues = self.gitlab.get_issues()
        log.info('Got {} issue(s) from gitlab.'.format(len(gitlab_issues)))

        for issue in gitlab_issues:
            log.info('delete issue {}'.format(issue['id']))
            self.gitlab.delete_issue(issue['id'])


class LinkRedmineRoadmap(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.redmine = self.redmine_project_with_cache()
        self.gitlab = self.gitlab_project()
        self.cache = self.redmine_cache(self.redmine)

    def execute(self):
        log.info('Start {}'.format(self))

        redmine_versions = self.redmine.get_versions()
        log.info('Got {} version(s) from redmine.'.format(len(redmine_versions)))

        gitlab_milestones = self.gitlab.get_milestones()
        log.info('Got {} milestone(s) from gitlab.'.format(len(gitlab_milestones)))
        gitlab_milestones_index = {i['title']: i for i in gitlab_milestones}

        for redmine_version in redmine_versions:

            name = redmine_version['name']
            gitlab_milestone = gitlab_milestones_index[name]
            log.debug(gitlab_milestone)
            gitlab_milestone_iid = gitlab_milestone['iid']
            self.redmine.link_roadmap(redmine_version, gitlab_milestone_iid, self.gitlab.project_url, self.cache)

            redmine_version_id = redmine_version['id']
            json_file_path = self.cache.get_version2_path(redmine_version_id)

            action = ['curl', '-v', '-X', 'PUT',
                      '-H', 'Content-Type: application/json',
                      '-H', 'X-Redmine-API-Key:{}'.format(self.config.redmine_key),
                      '--data-binary', '@{}'.format(json_file_path),
                      '{}/versions/{}.json'.format(self.config.redmine_host, redmine_version_id)]
            if self.args.check:
                log.info(
                    'Would link redmine version {} ({}) to gitlab milestone {}'.format(redmine_version_id, name,
                                                                                       gitlab_milestone_iid))
                log.info('using command: {}'.format(action))
            else:
                log.info('Link redmine version {} ({}) to gitlab milestone {}'.format(redmine_version_id, name,
                                                                                      gitlab_milestone_iid))
                log.debug('using command: {}'.format(action))
                subprocess.run(action, stdout=subprocess.PIPE)


class LinkRedmineIssue(Command):
    def __init__(self, config, args):
        # noinspection PyCompatibility
        super().__init__(config, args)
        self.redmine = self.redmine_project_with_cache()
        self.gitlab = self.gitlab_project()
        self.cache = self.redmine_cache(self.redmine)

    def execute(self):
        log.info('Start {}'.format(self))

        redmine_issues = self.redmine.get_all_issues()

        log.info('Got {} issue(s) from redmine.'.format(len(redmine_issues)))

        gitlab_issues = self.gitlab.get_issues()
        gitlab_issues_index = {i['title']: i for i in gitlab_issues}

        log.info('Got {} issue(s) from gitlab.'.format(len(gitlab_issues)))

        for redmine_issue in redmine_issues:
            subject = redmine_issue['subject'].strip()
            gitlab_issue = gitlab_issues_index[subject]
            redmine_issue_id = redmine_issue['id']
            self.redmine.link_issue(redmine_issue, gitlab_issue['iid'], self.gitlab.project_url, self.cache)

            json_file_path = self.cache.get_issue2_path(redmine_issue_id)

            action = ['curl', '-X', 'PUT',
                      '-H', 'Content-Type: application/json',
                      '-H', 'X-Redmine-API-Key:{}'.format(self.config.redmine_key),
                      '--data-binary', '@{}'.format(json_file_path),
                      '{}/issues/{}.json'.format(self.config.redmine_host, redmine_issue_id)]
            if self.args.check:
                log.info(
                    'Would link redmine issue {} ({}) to {}'.format(redmine_issue_id, subject, gitlab_issue['iid']))
                log.info('using command: {}'.format(action))
            else:
                log.info('Link redmine issue {} ({}) to {}'.format(redmine_issue_id, subject, gitlab_issue['iid']))
                log.debug('using command: {}'.format(action))
                subprocess.run(action, shell=True, check=True)
