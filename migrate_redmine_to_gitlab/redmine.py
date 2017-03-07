from itertools import chain
import os
import re
import logging
import json

from . import APIClient, Project

ANONYMOUS_USER_ID = 2

log = logging.getLogger(__name__)


class RedmineClient(APIClient):
    PAGE_MAX_SIZE = 100

    def get_auth_headers(self):
        return {"X-Redmine-API-Key": self.api_key}

    def get(self, *args, **kwargs):
        # In detail views, redmine encapsulate "foo" typed objects under a
        # "foo" key on the JSON.
        # noinspection PyCompatibility
        ret = super().get(*args, **kwargs)
        values = ret.values()
        if len(values) == 1:
            return list(values)[0]
        else:
            return ret

    def get_all_pages(self, *args, **kwargs):
        """ Iterates over API pagination for a given resource list
        """
        kwargs['params'] = kwargs.get('params', {})
        kwargs['params']['limit'] = self.PAGE_MAX_SIZE

        resp = self.get(*args, **kwargs)

        # Try to auto find the top-level key containing
        keys_candidates = (
            set(resp.keys()) - {'total_count', 'offset', 'limit'})

        assert len(keys_candidates) == 1
        res_list_key = list(keys_candidates)[0]

        result_pages = [resp[res_list_key]]
        if 'offset' not in resp:
            raise ValueError('HTTP response data is not paginated')

        while (resp['total_count'] - resp['offset'] - resp['limit']) > 0:
            kwargs['params']['offset'] = (kwargs['params'].get('offset', 0)
                                          + self.PAGE_MAX_SIZE)
            resp = self.get(*args, **kwargs)
            result_pages.append(resp[res_list_key])
        return chain.from_iterable(result_pages)


class RedmineProject(Project):
    REGEX_PROJECT_URL = re.compile(
        r'^(?P<base_url>https?://.*)/projects/(?P<project_name>[\w_-]+)$')

    REGEX_CATEGORY_PROJECT_URL = re.compile(
        r'^(?P<base_url>https?://.*)/project/(?P<category_name>[\w_-]+)/(?P<project_name>[\w_-]+)/?$')

    def __init__(self, url, *args, **kwargs):
        normalized_url = self._remove_category_in_url(url)
        # noinspection PyCompatibility
        super().__init__(normalized_url, *args, **kwargs)
        self.api_url = '{}.json'.format(self.public_url)
        self.instance_url = self._url_match.group('base_url')
        self.project = self.api.get(self.api_url)
        log.info('Got redmine project: {}'.format(self.get_id()))

    def get_id(self):
        return str(self.project.get('id', 0))

    def get_project(self):
        return self.project

    @classmethod
    def _remove_category_in_url(cls, url):
        """ If using categories, return the category-less URL

        eg:
          - category URL: https://example.com/project/dev/foobar/
          - category-less URL: https://example.com/projects/foobar/

        API endpoints are reachable only for category-less URLs.
        """
        m = cls.REGEX_CATEGORY_PROJECT_URL.match(url)
        if m:
            return '{base_url}/projects/{project_name}'.format(**m.groupdict())
        else:
            return url

    def get_all_issues(self):
        issues = self.api.get_all_pages(
            '{}/issues.json?status_id=*'.format(self.public_url))
        detailed_issues = []
        # It's impossible to get issue history from list view, so get it from
        # detail view...

        for issue_id in (i['id'] for i in issues):
            issue_url = '{}/issues/{}.json?include=journals,watchers,relations,childrens,attachments'.format(
                self.instance_url, issue_id)
            detailed_issues.append(self.api.get(issue_url))

        return detailed_issues

    def get_participants(self):
        """Get participating users (issues authors/owners)

        :return: list of all users participating on issues
        :rtype: list
        """
        issues = self.get_all_issues()
        return self.get_participants0(issues)

    def get_participants0(self, issues):
        """Get participating users (issues authors/owners)

        :return: list of all users participating on issues
        :rtype: list
        """
        user_ids = set()
        users = []
        for issue in issues:
            for user in chain(issue.get('watchers', []), [issue['author'], issue.get('assigned_to', None)]):
                if user is None:
                    continue
                user_ids.add(user['id'])

        for user_id in user_ids:
            # The anonymous user is not really part of the project...
            if user_id != ANONYMOUS_USER_ID:
                users.append(self.api.get('{}/users/{}.json'.format(self.instance_url, user_id)))
        return users

    def get_users_index(self):
        """ Returns dict index of users (by user id)
        """
        return {i['id']: i for i in self.get_participants()}

    def get_versions(self):
        response = self.api.get('{}/versions.json'.format(self.public_url))
        return response['versions']

    def load_attachment_file(self, attachment):
        return self.api.load(attachment['content_url'])


class RedmineProjectWithCache(Project):
    REGEX_PROJECT_URL = re.compile(
        r'^(?P<base_url>https?://.*)/projects/(?P<project_name>[\w_-]+)$')

    def __init__(self, url, cache_dir, *args, **kwargs):
        # noinspection PyCompatibility
        super().__init__(url, *args, **kwargs)
        self.api_url = '{}.json'.format(self.public_url)
        self.instance_url = self._url_match.group('base_url')
        self.path = cache_dir
        with open(os.path.join(self.path, 'project.json'), 'r') as outfile:
            self.project = json.load(outfile)
        log.info('Got redmine project: {}'.format(self.get_id()))

    def get_id(self):
        return str(self.project['id'])

    def get_project(self):
        return self.project

    def get_all_issues(self):
        data = self._load_data(os.path.join(self.path, 'issues'))
        return sorted(data, key=lambda issue: issue['id'])

    def get_participants(self):
        return self._load_data(os.path.join(self.path, 'users'))

    def get_users_index(self):
        return {i['id']: i for i in self.get_participants()}

    def get_versions(self):
        data = self._load_data(os.path.join(self.path, 'versions'))
        return sorted(data, key=lambda version: version['id'])

    def get_attachments(self):
        return self._load_data(os.path.join(self.path, 'attachments'))

    def get_attachments_index(self):
        return {i['id']: i for i in self.get_attachments()}

    def link_roadmap(self, version, gitlab_id, gitlab_url, cache):
        if not '/milestones/' in version['description']:
            version['description'] += "Moved to {}/milestones/{}".format(gitlab_url, gitlab_id)
        cache.load_version2(version)

    def link_issue(self, issue, gitlab_id, gitlab_url, cache):
        issue['note'] = "Moved to {}/issues/{}".format(gitlab_url, gitlab_id)
        cache.load_issue2(issue)

    @staticmethod
    def _load_data(path):
        result = []
        for entry in os.scandir(path):
            if entry.is_file() and str(entry.path).endswith('.json'):
                with open(entry.path, 'r') as outfile:
                    data = json.load(outfile)
                    result.append(data)
        return result


class RedmineCacheWriter:
    def __init__(self, cache_dir, project):
        self.path = cache_dir
        log.info('Redmine Cache dir: {}'.format(self.path))
        self.project = project
        self._create_dir(self.path)
        self._store_data(self.path, project.get_project(), 'project', 'Project file')

    def load_versions(self):
        path = os.path.join(self.path, 'versions')
        if os.path.exists(path):
            log.info('Load versions from cache {}'.format(path))
            versions = self._load_data(path)
        else:
            self._create_dir(path)
            log.info('Store versions')
            versions = self.project.get_versions()
            for version in versions:
                self._store_data(path, version, version['id'], 'Version')
        return versions

    def load_issues(self):
        path = os.path.join(self.path, 'issues')
        if os.path.exists(path):
            log.info('Load issues from cache {}'.format(path))
            issues = self._load_data(path)
        else:
            self._create_dir(path)
            log.info('Loading issues')
            issues = self.project.get_all_issues()
            for issue in issues:
                self._store_data(path, issue, issue['id'], 'Issue')
        return issues

    def load_users(self, issues):
        path = os.path.join(self.path, 'users')
        if os.path.exists(path):
            log.info('Load users from cache {}'.format(path))
            users = self._load_data(path)
        else:
            self._create_dir(path)
            log.info('Loading users')
            users = self.project.get_participants0(issues)
            for user in users:
                self._store_data(path, user, user['id'], 'User')
        return users

    def load_attachments(self, issues):
        path = os.path.join(self.path, 'attachments')
        if os.path.exists(path):
            log.info('Load attachments from cache {}'.format(path))
            attachments = self._load_data(path)
        else:
            self._create_dir(path)
            log.info('Loading attachments')
            attachments = []
            for issue in issues:
                at = issue['attachments']
                if at:
                    for a in at:
                        attachments.append(a)
                        a_content = self.project.load_attachment_file(a)
                        file = os.path.join(path, '{}.data'.format(a['id']))
                        with open(file, 'wb') as outfile:
                            outfile.write(a_content)
                        a['file'] = file
                        self._store_data(path, a, a['id'], 'Attachment')
        return attachments

    def load_attachment(self, attachment):
        path = os.path.join(self.path, 'attachments')
        self._store_data(path, attachment, attachment['id'], 'Attachment')

    def load_issue(self, issue):
        path = os.path.join(self.path, 'issues')
        self._store_data(path, issue, issue['id'], 'Issue')

    def load_version(self, version):
        path = os.path.join(self.path, 'versions')
        self._store_data(path, version, version['id'], 'Version')

    def load_version2(self, version):
        path = os.path.join(self.path, 'versions2')
        self._create_dir(path)
        v = {
            "version": {
                "name": version['name'],
                "description": version['description']
            }
        }
        self._store_data(path, v, version['id'], 'Version')

    def load_issue2(self, issue):
        path = os.path.join(self.path, 'issues2')
        self._create_dir(path)
        v = {
            "issue": {
                "notes": issue['note']
            }
        }
        self._store_data(path, v, issue['id'], 'Issue')

    def get_version2_path(self, version_id):
        return os.path.join(self.path, 'versions2', '{}.json'.format(version_id))

    def get_issue2_path(self, issue_id):
        return os.path.join(self.path, 'issues2', '{}.json'.format(issue_id))

    @staticmethod
    def _create_dir(path):
        if not os.path.exists(path):
            os.makedirs(path)
            log.info('Create cache dir: {}'.format(path))

    @staticmethod
    def _store_data(path, data, data_id, msg):
        file = os.path.join(path, '{}.json'.format(data_id))
        with open(file, 'w') as outfile:
            json.dump(data, outfile)
        log.info('{} {} to {}'.format(msg, data_id, file))
        log.debug('{} {} = {}'.format(msg, data_id, data))

    @staticmethod
    def _load_data(path):
        result = []
        for entry in os.scandir(path):
            if entry.is_file() and str(entry.path).endswith('.json'):
                with open(entry.path, 'r') as outfile:
                    data = json.load(outfile)
                    result.append(data)
        return result
