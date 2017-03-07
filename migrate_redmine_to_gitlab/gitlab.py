import re
import logging
from . import APIClient, Project

log = logging.getLogger(__name__)


class GitlabClient(APIClient):
    # see http://doc.gitlab.com/ce/api/#pagination
    MAX_PER_PAGE = 100

    def get(self, *args, **kwargs):
        # Note that we do not handle pagination, but as we rely on list data
        # only for milestones, we assume that we have < 100 milestones. Could
        # be fixed though...
        kwargs['params'] = kwargs.get('params', {})
        kwargs['params']['per_page'] = self.MAX_PER_PAGE
        # noinspection PyCompatibility
        return super().get(*args, **kwargs)

    def get_auth_headers(self):
        return {"PRIVATE-TOKEN": self.api_key}

    def check_is_admin(self):
        pass


class GitlabProject(Project):
    REGEX_PROJECT_URL = re.compile(
        r'^(?P<base_url>https?://.*/)(?P<namespace>[^/]+)/(?P<project_name>[\w_-]+)$')

    def __init__(self, *args, **kwargs):
        # noinspection PyCompatibility
        super().__init__(*args, **kwargs)
        self.api_url0 = ('{base_url}api/v3/projects/{namespace}%2F{project_name}'.format(**self._url_match.groupdict()))
        self.project = self.get_project()
        self.project_id = str(self.project['id'])
        self.project_url = '{base_url}{namespace}/{project_name}'.format(**self._url_match.groupdict())
        log.info('Go gitlab project {}'.format(self.project_id))
        self.api_url = (('{base_url}api/v3/projects/' + self.project_id).format(**self._url_match.groupdict()))
        self.instance_url = '{}/api/v3'.format(self._url_match.group('base_url'))

    def is_repository_empty(self):
        """ Heuristic to check if repository is empty
        """
        return self.api.get(self.api_url)['default_branch'] is None

    def create_attachment(self, data):
        """ High-level attachment creation

        :param data: dict formatted as the gitlab API expects it
        :return: the created attachment
        """
        attachment_url = '{}/uploads'.format(self.api_url)
        data_redmine_ = data['redmine']
        content_type = data_redmine_.get('content_type', 'application/text')
        files = {'file': (data_redmine_['filename'], open(data_redmine_['file'], 'rb'), content_type)}

        return self.api.post(attachment_url, data['request'], files=files)

    def create_issue(self, data, meta):
        """ High-level issue creation

        :param meta: dict with "sudo_user", "should_close", "attachments" and "notes" keys
        :param data: dict formatted as the gitlab API expects it
        :return: the created issue (without notes)
        """
        if len(meta['attachments']) > 0:
            attachment_log = '\n\n### Files'
            for attachment in meta['attachments']:
                redmine_attachment = attachment['redmine']
                gitlab_attachment = redmine_attachment.get('gitlab', None)
                if gitlab_attachment is None:
                    attachment_log += '\n  * [{}] ({})'.format(redmine_attachment['filename'],
                                                               redmine_attachment['content_url'])
                else:
                    attachment_log += '\n  * [{}] ({})'.format(gitlab_attachment['alt'], gitlab_attachment['url'])
            data['description'] += attachment_log

        issues_url = '{}/issues'.format(self.api_url)
        issue = self.api.post(issues_url, data=data)

        issue_url = '{}/{}'.format(issues_url, issue['id'])

        # Handle issues notes
        issue_notes_url = '{}/notes'.format(issue_url, 'notes')
        for note_data, note_meta in meta['notes']:
            self.api.post(issue_notes_url, data=note_data)

        # Handle closed status
        if meta['must_close']:
            altered_issue = issue.copy()
            altered_issue['labels'] = data['labels']
            altered_issue['state_event'] = 'close'
            self.api.put(issue_url, data=altered_issue)

        return issue

    def create_milestone(self, data, meta):
        """ High-level milestone creation

        :param meta: dict with "should_close"
        :param data: dict formatted as the gitlab API expects it
        :return: the created milestone
        """
        milestones_url = '{}/milestones'.format(self.api_url)
        milestone = self.api.post(milestones_url, data=data)

        if meta['must_close']:
            milestone_url = '{}/{}'.format(milestones_url, milestone['id'])
            altered_milestone = milestone.copy()
            altered_milestone['state_event'] = 'close'

            self.api.put(milestone_url, data=altered_milestone)
        return milestone

    def delete_issue(self, issue_id):
        self.api.delete('{}/issues/{}'.format(self.api_url, issue_id))

    def get_issues(self):
        issues = []
        page = 1
        found_issues = self.api.get('{}/issues?page={}&per_page=100'.format(self.api_url, page))
        while len(found_issues) > 0:
            issues += found_issues
            page += 1
            found_issues = self.api.get('{}/issues?page={}&per_page=100'.format(self.api_url, page))
        return issues

    def get_members(self):
        return self.api.get('{}/members'.format(self.api_url))

    def get_milestones(self):
        if not hasattr(self, '_cache_milestones'):
            # noinspection PyAttributeOutsideInit
            self._cache_milestones = []
            page = 1
            found_issues = self.api.get('{}/milestones?page={}&per_page=100'.format(self.api_url, page))
            while len(found_issues) > 0:
                self._cache_milestones += found_issues
                page += 1
                found_issues = self.api.get('{}/milestones?page={}&per_page=100'.format(self.api_url, page))
        return self._cache_milestones

    def get_milestones_index(self):
        return {i['title']: i for i in self.get_milestones()}

    def get_milestone_by_id(self, _id):
        milestones = self.get_milestones()
        for i in milestones:
            if i['id'] == _id:
                return i
        raise ValueError('Could not get milestone')

    # noinspection SpellCheckingInspection
    def has_members(self, usernames):
        gitlab_user_names = set([i['username'] for i in self.get_members()])
        return all((i in gitlab_user_names for i in usernames))

    def get_project(self):
        return self.api.get(self.api_url0)

    def get_id(self):
        return self.project_id

    def get_all_users(self):
        return self.api.get('{}/users'.format(self.api_url))

    def get_users_index(self):
        """ Returns dict index of users (by login)
        """
        return {i['username']: i for i in self.get_all_users()}
