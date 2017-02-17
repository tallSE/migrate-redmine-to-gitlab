import unittest

from .fake import FakeGitlabClient
from migrate_redmine_to_gitlab.gitlab import  GitlabProject


class GitlabprojectTestCase(unittest.TestCase):
    def setUp(self):
        self.client = FakeGitlabClient()

        self.project_1 = GitlabProject(
            'http://localhost:3000/diaspora/diaspora-project-site',
            self.client)

        self.project_2 = GitlabProject(
            'http://localhost:3000/brightbox/puppet',
            self.client)

    def test_check_repository_empty(self):
        self.assertEqual(self.project_1.is_repository_empty(), False)
        self.assertEqual(self.project_2.is_repository_empty(), True)

    def test_issues(self):
        self.assertEqual(len(self.project_1.get_issues()), 2)
        self.assertEqual(len(self.project_2.get_issues()), 0)

    def test_members(self):
        self.assertEqual(
            self.project_1.has_members(['john_smith', 'jack_smith']),
            True)
        self.assertEqual(
            self.project_1.has_members(
                ['john_smith', 'jack_smith', 'macha_smith']),
            False)
        self.assertEqual(
            self.project_1.has_members([]),
            True)
