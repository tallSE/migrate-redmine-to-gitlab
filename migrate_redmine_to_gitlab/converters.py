import logging

log = logging.getLogger(__name__)


def redmine_uid_to_login(redmine_id, redmine_user_index):
    return redmine_user_index[redmine_id]['login']


def redmine_uid_to_gitlab_uid(redmine_id,
                              redmine_user_index, gitlab_user_index):
    username = redmine_uid_to_login(redmine_id, redmine_user_index)
    return gitlab_user_index[username]['id']


def convert_notes(redmine_issue_journals, redmine_user_index):
    """ Convert a list of redmine journal entries to gitlab notes

    Filters out the empty notes (ex: bare status change)
    Adds metadata as comment

    :param redmine_issue_journals: list of redmine "journals"
    :param redmine_user_index: dictionary of redmine users
    :return: yielded couple ``data``, ``meta``. ``data`` is the API payload for
        an issue note and meta a dict (containing, at the moment, only a "sudo_user" key).
    """

    for entry in redmine_issue_journals:
        journal_notes = entry.get('notes', '')
        if not 'Migrated to https' in journal_notes \
                and not 'Moved to https' in journal_notes \
                and len(journal_notes) > 0:
            body = "{}\n\n*(from redmine: written on {})*".format(
                journal_notes, entry['created_on'][:10])
            try:
                author = redmine_uid_to_login(
                    entry['user']['id'], redmine_user_index)
            except KeyError:
                # In some cases you have anonymous notes, which do not exist in
                # gitlab.
                log.debug(
                    'Redmine user {} is unknown, attribute note '
                    'to current admin\n'.format(entry['user']))
                author = None
            yield {'body': body}, {'sudo_user': author}


def relations_to_string(relations, issue_id):
    """ Convert redmine formal relations to some un-normalized string

    That's the way gitlab does relations, by "mentioning".

    :param relations: list of issues relations
    :param issue_id: the current issue id
    :return a string listing relations.
    """
    l = []
    for i in relations:
        if issue_id == i['issue_id']:
            other_issue_id = i['issue_to_id']
        else:
            other_issue_id = i['issue_id']
        l.append('{} #{}'.format(i['relation_type'], other_issue_id))

    return ', '.join(l)


def convert_issue(redmine_issue,
                  redmine_user_index,
                  redmine_attachments_index,
                  gitlab_project_id,
                  gitlab_user_index,
                  gitlab_milestones_index,
                  with_id=False):
    if redmine_issue.get('closed_on', None):
        # quick'n dirty extract date
        close_text = ', closed on {}'.format(redmine_issue['closed_on'][:10])
        closed = True
    else:
        close_text = ''
        closed = False

    relations = redmine_issue.get('relations', [])
    relations_text = relations_to_string(relations, redmine_issue['id'])
    if len(relations_text) > 0:
        relations_text = ', ' + relations_text

    if with_id:
        title = '-RM-{}-MR-{}'.format(redmine_issue['id'], redmine_issue['subject'])
    else:
        title = redmine_issue['subject']

    labels = 'From Redmine, ' + redmine_issue['tracker']['name'] + ', ' + redmine_issue['priority']['name']
    
    #作成日時と有効期限追加
    created_at = redmine_issue['start_date']
    due_date = redmine_issue['due_date']

    data = {
        'title': title,
        'redmine_id': redmine_issue['id'],
        'description': '{}\n\n*(from redmine issue {} created on {}{}{})*'.format(
            redmine_issue['description'],
            redmine_issue['id'],
            redmine_issue['created_on'][:10],
            close_text,
            relations_text
        ),
        'labels': labels,
        #作成日時と有効期限追加
        'created_at': closed_at,
        'due_date': due_date
    }

    version = redmine_issue.get('fixed_version', None)
    if version:
        data['milestone_id'] = gitlab_milestones_index[version['name']]['id']

    try:
        author_login = redmine_uid_to_login(
            redmine_issue['author']['id'], redmine_user_index)

    except KeyError:
        log.debug(
            'Redmine issue #{} is anonymous, gitlab issue is attributed '
            'to current admin\n'.format(redmine_issue['id']))
        author_login = None

    attachments = []
    for a in redmine_issue.get('attachments', []):
        attachment = redmine_attachments_index[a['id']]
        attachments.append(convert_attachment(gitlab_project_id, attachment))

    meta = {
        'sudo_user': author_login,
        'notes': list(convert_notes(redmine_issue['journals'], redmine_user_index)),
        'must_close': closed,
        'attachments': attachments
    }

    assigned_to = redmine_issue.get('assigned_to', None)
    if assigned_to is not None:
        data['assignee_id'] = redmine_uid_to_gitlab_uid(assigned_to['id'], redmine_user_index, gitlab_user_index)
    return data, meta


def convert_version(redmine_version):
    """ Turns a redmine version into a gitlab milestone

    Do not handle the issues linked to the milestone/version.
    Note that redmine do not expose a due date in API.

    :param redmine_version: a dict describing redmine-api-style version
    :rtype: couple: dict, dict
    :return: a dict describing gitlab-api-style milestone and another for meta
    """
    milestone = {
        "title": redmine_version['name'],
        'redmine_id': redmine_version['id'],
        "description": '{}\n\n*(from redmine: created on {})*'.format(
            redmine_version['description'],
            redmine_version['created_on'][:10])
    }
    if 'due_date' in redmine_version:
        milestone['due_date'] = redmine_version['due_date'][:10]

    must_close = redmine_version['status'] == 'closed'

    return milestone, {'must_close': must_close}


def convert_attachments(redmine_issue, redmine_attachments_index, gitlab_project_id):
    attachments = []
    for redmine_attachment in redmine_issue.get('attachments', []):
        attachment = redmine_attachments_index[redmine_attachment['id']]
        attachments.append(convert_attachment(gitlab_project_id, attachment))

    return attachments


def convert_attachment(gitlab_project_id, redmine_attachment):
    return {"redmine": redmine_attachment, "request": {"id": gitlab_project_id, "file": redmine_attachment['filename']}}
