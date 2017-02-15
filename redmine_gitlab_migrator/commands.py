#!/bin/env python3
import argparse
import logging
import re

from redmine_gitlab_migrator.redmine import RedmineProject, RedmineClient, RedmineCacheWriter, RedmineProjectWithCache
from redmine_gitlab_migrator.gitlab import GitlabProject, GitlabClient
from redmine_gitlab_migrator.converters import convert_issue, convert_version
from redmine_gitlab_migrator.logging import setup_module_logging
from redmine_gitlab_migrator import sql

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

    download_redmine = subparsers.add_parser(
        'download-redmine', help=perform_download_redmine.__doc__)
    download_redmine.set_defaults(func=perform_download_redmine)

    migrate_roadmap = subparsers.add_parser(
        'roadmap', help=perform_migrate_roadmap.__doc__)
    migrate_roadmap.set_defaults(func=perform_migrate_roadmap)

    migrate_attachments = subparsers.add_parser(
        'attachments', help=perform_migrate_attachments.__doc__)
    migrate_attachments.set_defaults(func=perform_migrate_attachments)

    migrate_issues = subparsers.add_parser(
        'issues', help=perform_migrate_issues.__doc__)
    migrate_issues.set_defaults(func=perform_migrate_issues)

    migrate_issues_with_id = subparsers.add_parser(
        'issues-with-id', help=perform_migrate_issues_with_id.__doc__)
    migrate_issues_with_id.set_defaults(func=perform_migrate_issues_with_id)

    delete_issues = subparsers.add_parser(
        'delete-issues', help=perform_delete_issues.__doc__)
    delete_issues.set_defaults(func=perform_delete_issues)

    parser_iid = subparsers.add_parser(
        'iid', help=perform_migrate_iid.__doc__)
    parser_iid.set_defaults(func=perform_migrate_iid)

    for i in (download_redmine, migrate_issues, migrate_roadmap, migrate_attachments, migrate_issues_with_id):
        i.add_argument('redmine_project_url')
        i.add_argument(
            '--redmine-key',
            required=True,
            help="Redmine administrator API key")
        i.add_argument(
            '--cache-dir',
            required=True,
            help="Redmine local cache directory")

    for i in (migrate_issues, delete_issues, migrate_roadmap, parser_iid, migrate_attachments, migrate_issues_with_id):
        i.add_argument('gitlab_project_url')
        i.add_argument(
            '--gitlab-key',
            required=True,
            help="Gitlab administrator API key")

        i.add_argument(
            '--check',
            required=False, action='store_true', default=False,
            help="do not perform any action, just check everything is ready")

    for i in (download_redmine, migrate_issues, migrate_roadmap, parser_iid, migrate_attachments, delete_issues,
              migrate_issues_with_id):
        i.add_argument(
            '--debug',
            required=False, action='store_true', default=False,
            help="More output")

    return parser.parse_args()


def check(func, message, redmine_project, gitlab_project):
    ret = func(redmine_project, gitlab_project)
    if ret:
        log.info('{}... OK'.format(message))
    else:
        log.error('{}... FAILED'.format(message))
        exit(1)


def check_users(redmine_project, gitlab_project):
    users = redmine_project.get_participants()
    # Filter out anonymous user
    nicks = set([i['login'] for i in users if i['login'] != ''])
    log.info('Project users are: {}'.format(', '.join(nicks) + ' '))

    gitlab_user_names = set([i['username'] for i in gitlab_project.get_all_users()])
    return all((i in gitlab_user_names for i in nicks))


def check_no_issue(redmine_project, gitlab_project):
    return len(gitlab_project.get_issues()) == 0


def check_no_milestone(redmine_project, gitlab_project):
    return len(gitlab_project.get_milestones()) == 0


def check_origin_milestone(redmine_project, gitlab_project):
    return len(redmine_project.get_versions()) > 0


def perform_download_redmine(args):
    redmine = RedmineClient(args.redmine_key)
    redmine_project = RedmineProject(args.redmine_project_url, redmine)
    redmine_cache = RedmineCacheWriter(args.cache_dir, redmine_project)

    versions = redmine_cache.load_versions()
    log.info('{} version(s) loaded'.format(len(versions)))

    issues = redmine_cache.load_issues()
    log.info('{} issue(s) loaded'.format(len(issues)))

    users = redmine_cache.load_users(issues)
    log.info('{} user(s) loaded'.format(len(users)))

    attachments = redmine_cache.load_attachments(issues)
    log.info('{} attachment(s) loaded'.format(len(attachments)))


def perform_migrate_roadmap(args):
    redmine = RedmineClient(args.redmine_key)
    gitlab = GitlabClient(args.gitlab_key)

    redmine_project = RedmineProjectWithCache(args.redmine_project_url, args.cache_dir, redmine)
    gitlab_project = GitlabProject(args.gitlab_project_url, gitlab)

    checks = [
        (check_no_milestone, 'Gitlab project has no pre-existing milestone'),
        (check_origin_milestone, 'Redmine project contains versions'),
    ]
    for i in checks:
        check(
            *i, redmine_project=redmine_project,
            gitlab_project=gitlab_project)

    versions = redmine_project.get_versions()
    versions_data = (convert_version(i) for i in versions)
    if args.check:
        for data, meta in versions_data:
            log.info("Would create version {}".format(data))
        pass

    gitlab_versions = []
    created_version, bad_versions = _create_versions(gitlab_project, versions_data, [])
    gitlab_versions += created_version
    while len(bad_versions) > 0:
        log.info('Some versions were not created: {}'.format(bad_versions))

        created_version, bad_versions = _create_versions(gitlab_project, versions_data, bad_versions)
        gitlab_versions += created_version

    log.info('{} version(s) created on GitLab'.format(len(gitlab_versions)))


def _create_versions(gitlab_project, versions_data, incoming_bad_versions):
    bad_versions = []
    created_version = []
    for data, meta in versions_data:
        if len(incoming_bad_versions) == 0 or str(data['id']) in incoming_bad_versions:
            try:
                created = gitlab_project.create_milestone(data, meta)
                created_version.append(created)
                log.info("Version {}".format(created['title']))
            except:
                log.error('Could not create version {}'.format(data['id']))
                bad_versions.append(data['id'])
    return created_version, bad_versions


def perform_delete_issues(args):
    gitlab = GitlabClient(args.gitlab_key)
    gitlab_project = GitlabProject(args.gitlab_project_url, gitlab)

    for issue in gitlab_project.get_issues():
        log.info('delete issue {}'.format(issue['id']))
        gitlab_project.delete_issue(issue['id'])


def perform_migrate_issues(args):
    redmine = RedmineClient(args.redmine_key)
    gitlab = GitlabClient(args.gitlab_key)

    redmine_project = RedmineProjectWithCache(args.redmine_project_url, args.cache_dir, redmine)
    gitlab_project = GitlabProject(args.gitlab_project_url, gitlab)

    gitlab_users_index = gitlab_project.get_users_index()
    redmine_users_index = redmine_project.get_users_index()

    checks = [
        (check_users, 'Required users presence'),
        (check_no_issue, 'Project has no pre-existing issue'),
    ]
    for i in checks:
        check(
            *i, redmine_project=redmine_project, gitlab_project=gitlab_project)

    # Get issues

    issues = redmine_project.get_all_issues()
    attachments_index = redmine_project.get_attachments_index()
    milestones_index = gitlab_project.get_milestones_index()
    gitlab_project_id = gitlab_project.get_id()
    issues_data = (convert_issue(i, redmine_users_index, attachments_index, gitlab_project_id, gitlab_users_index,
                                 milestones_index) for i in issues)

    if args.check:
        for data, meta in issues_data:
            milestone_id = data.get('milestone_id', None)
            if milestone_id:
                try:
                    gitlab_project.get_milestone_by_id(milestone_id)
                except ValueError:
                    raise CommandError(
                        "issue \"{}\" points to unknown milestone_id \"{}\". "
                        "Check that you already migrated roadmaps".format(
                            data['title'], milestone_id))

            log.info(
                'Would create issue "{}" with {} notes and {} attachments.'.format(data['title'], len(meta['notes']),
                                                                                   len(meta['attachments'])))
        return

    gitlab_issues = []

    created_issues, bad_issues = _create_issues(gitlab_project, issues_data, [])
    gitlab_issues += created_issues
    while len(bad_issues) > 0:
        log.info('Some issues were not created: {}'.format(bad_issues))

        issues_data = (convert_issue(i, redmine_users_index, attachments_index, gitlab_project_id, gitlab_users_index,
                                     milestones_index) for i in issues)

        created_issues, bad_issues = _create_issues(gitlab_project, issues_data, bad_issues)
        gitlab_issues += created_issues

    log.info('{} issue(s) created on GitLab'.format(len(gitlab_issues)))


def perform_migrate_issues_with_id(args):
    redmine = RedmineClient(args.redmine_key)
    gitlab = GitlabClient(args.gitlab_key)

    redmine_project = RedmineProjectWithCache(args.redmine_project_url, args.cache_dir, redmine)
    gitlab_project = GitlabProject(args.gitlab_project_url, gitlab)

    gitlab_users_index = gitlab_project.get_users_index()
    redmine_users_index = redmine_project.get_users_index()

    checks = [
        (check_users, 'Required users presence'),
        (check_no_issue, 'Project has no pre-existing issue'),
    ]
    for i in checks:
        check(
            *i, redmine_project=redmine_project, gitlab_project=gitlab_project)

    # Get issues

    issues = redmine_project.get_all_issues()
    attachments_index = redmine_project.get_attachments_index()
    milestones_index = gitlab_project.get_milestones_index()
    gitlab_project_id = gitlab_project.get_id()
    issues_data = (
        convert_issue(i, redmine_users_index, attachments_index, gitlab_project_id, gitlab_users_index,
                      milestones_index, with_id=True) for i in issues)

    if args.check:
        for data, meta in issues_data:
            milestone_id = data.get('milestone_id', None)
            if milestone_id:
                try:
                    gitlab_project.get_milestone_by_id(milestone_id)
                except ValueError:
                    raise CommandError(
                        "issue \"{}\" points to unknown milestone_id \"{}\". "
                        "Check that you already migrated roadmaps".format(
                            data['title'], milestone_id))

            log.info(
                'Would create issue "{}" with {} notes and {} attachments.'.format(data['title'], len(meta['notes']),
                                                                                   len(meta['attachments'])))
        return

    gitlab_issues = []

    created_issues, bad_issues = _create_issues(gitlab_project, issues_data, [])
    gitlab_issues += created_issues
    while len(bad_issues) > 0:
        log.info('Some issues were not created: {}'.format(bad_issues))

        issues_data = (
            convert_issue(i, redmine_users_index, attachments_index, gitlab_project_id, gitlab_users_index,
                          milestones_index, with_id=True) for i in issues)

        created_issues, bad_issues = _create_issues(gitlab_project, issues_data, bad_issues)
        gitlab_issues += created_issues

    log.info('{} issue(s) created on GitLab'.format(len(gitlab_issues)))


def _create_issues(gitlab_project, issues_data, incoming_bad_issues):
    bad_issues = []
    created_issues = []
    for data, meta in issues_data:
        data_id = str(data['redmine_id'])
        if len(incoming_bad_issues) == 0 or data_id in incoming_bad_issues:
            try:
                created_issue = gitlab_project.create_issue(data, meta)
                created_issues.append(created_issue)
                log.info("Created issue (was: {}) {}".format(data_id, created_issue['title']))
            except:
                log.error('Could not create issue {}'.format(data_id))
                bad_issues.append(data_id)
    return created_issues, bad_issues


def perform_migrate_attachments(args):
    redmine = RedmineClient(args.redmine_key)
    gitlab = GitlabClient(args.gitlab_key)

    redmine_project = RedmineProjectWithCache(args.redmine_project_url, args.cache_dir, redmine)
    gitlab_project = GitlabProject(args.gitlab_project_url, gitlab)

    gitlab_users_index = gitlab_project.get_users_index()
    redmine_users_index = redmine_project.get_users_index()

    # Get issues

    issues = redmine_project.get_all_issues()
    attachments_index = redmine_project.get_attachments_index()
    milestones_index = gitlab_project.get_milestones_index()
    gitlab_project_id = gitlab_project.get_id()
    issues_data = (convert_issue(i, redmine_users_index, attachments_index, gitlab_project_id, gitlab_users_index,
                                 milestones_index) for i in issues)

    if args.check:
        for data, meta in issues_data:
            milestone_id = meta.get('attachments', None)
            if milestone_id:
                for a in milestone_id:
                    log.info('Would create attachment "{}"'.format(a['redmine']['filename']))
        return

    gitlab_attachments = []
    created_attachments, bad_attachments = _create_attachments(gitlab_project, issues_data, [])
    gitlab_attachments += created_attachments
    while len(bad_attachments) > 0:
        log.info('Some attachments were not created: {}'.format(bad_attachments))
        issues_data = (convert_issue(i, redmine_users_index, attachments_index, gitlab_project_id, gitlab_users_index,
                                     milestones_index) for i in issues)

        created_attachments, bad_attachments = _create_attachments(gitlab_project, issues_data, bad_attachments)
        gitlab_attachments += created_attachments

    redmine_cache = RedmineCacheWriter(args.cache_dir, redmine_project)

    for attachment in created_attachments:
        redmine_attachment = attachment['redmine']
        redmine_attachment['gitlab'] = attachment['gitlab']
        redmine_cache.load_attachment(redmine_attachment)

    log.info('{} attachments(s) created on GitLab'.format(len(gitlab_attachments)))


def _create_attachments(gitlab_project, attachments_data, incoming_bad_attachments):
    bad_attachments = []
    created_attachments = []
    for dataIDontCare, meta in attachments_data:
        for data in meta['attachments']:
            data_redmine_ = data['redmine']
            data_id = str(data_redmine_['id'])
            if len(incoming_bad_attachments) == 0 or data_id in incoming_bad_attachments:
                try:
                    created_attachment = gitlab_project.create_attachment(data)
                    data['gitlab'] = created_attachment
                    created_attachments.append(data)
                    log.info("Created attachment (was: {}) {}".format(data_id, created_attachment['markdown']))
                except:
                    bad_attachments.append(data_id)
                    log.error('Could not create attachment {} {} (size: {})'.format(data_id, data_redmine_['filename'],
                                                                                    data_redmine_['filesize']))
    return created_attachments, bad_attachments


def perform_migrate_iid(args):
    """ Should occur after the issues migration
    """

    gitlab = GitlabClient(args.gitlab_key)
    gitlab_project = GitlabProject(args.gitlab_project_url, gitlab)
    gitlab_project_id = gitlab_project.get_id()

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

    if not args.check:
        sql_cmd = sql.MIGRATE_IID_ISSUES.format(
            regex=regex_saved_iid, project_id=gitlab_project_id)
        out = sql.run_query(sql_cmd)

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


def main():
    args = parse_args()
    if hasattr(args, 'func'):
        if args.debug:
            loglevel = logging.DEBUG
        else:
            loglevel = logging.INFO

        # Configure global logging
        setup_module_logging('redmine_gitlab_migrator', level=loglevel)
        try:
            args.func(args)

        except CommandError as e:
            log.error(e)
            exit(12)
