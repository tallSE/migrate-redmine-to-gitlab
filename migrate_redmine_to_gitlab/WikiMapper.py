#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import json
import requests
import logging
import re
import datetime
import copy
from convert import *

def initLog(file_name):
    current_dir = os.getcwd()
    log_dir = '{}/log/'.format(current_dir)
    file_path = '{}{}'.format(log_dir, file_name)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logging.basicConfig(
        # output log this log file
        filename=file_path
    )

    log = logging.getLogger(__name__)
    log.setLevel(level=logging.DEBUG)
    return log

def writeLog(log, message):
    date = datetime.datetime.today()
    log.debug('{}: {}'.format(date, message))

def extractFiles(content):
    regexp = re.compile('"(.*?)":([A-Za-z0-9-_\/=\?\.\:%]+)')
    regexpFunc = regexp.finditer
    matches = regexpFunc(content)

    extract_url_list = []
    for match in matches:
        extract_url_list.append({
            'file_name': match.group(1),
            'file_url': match.group(2)
        })

    return extract_url_list
    
class InstantApiClient:
    def __init__(self, api_key_name, api_key_value):
        self.api = requests
        self.log = initLog('WikiMapper.log')
        self.headers = {
            api_key_name: api_key_value
        }
    
    def get(self,url):
        response = self.api.get(url,headers=self.headers)        
        writeLog(self.log, 'METHOD:  GET     ,    REQUEST   URL: {},    HEADERS:  {}'.format(url,self.headers))
        try:
            writeLog(self.log, 'METHOD:  GET({}),    RESPONSE  URL: {},    CONTENTS: {}'.format(response.status_code, url, response.json()))
        except json.decoder.JSONDecodeError as e:
            writeLog(self.log, 'METHOD:  GET({}),    RESPONSE  URL: {},    CONTENTS: '.format(response.status_code, url))
        finally:
            return response
    
    def post(self, url, **kwargs):
        kwargs['headers'] = kwargs.get('headers',{})

        for header in self.headers:
            kwargs['headers'][header] = self.headers[header]

        writeLog(self.log, 'METHOD: POST     ,    REQUEST   URL: {},    PARAMS:   {}'.format(url, self.headers))
        writeLog(self.log, 'METHOD: POST({}),    RESPONSE  URL: {},    CONTENTS: {}'.format(response.status_code, url, response.json()))

        return self.api.post(url,**kwargs)


if __name__ == "__main__":
    #TODO: project一覧をどうやって集めるか
    redmine_project_name = 'gitlab'
    redmine_base_url = 'https://project.rich-security.jp'
    redmine_api_key = 'eb9e461d7f686560154f129131dd7a96c399e553'

    gitlab_base_url = 'https://gitlab.rich-security.jp/api/v4'
    gitlab_api_key = 'kpmLeWB8Nvsto5tczmzY'
    gitlab_project_name = 237

    redmine_client = InstantApiClient('X-Redmine-API-Key',redmine_api_key)
    gitlab_client = InstantApiClient('Private-Token',gitlab_api_key)

    response_wiki_list = redmine_client.get('{}/projects/{}/wiki/index.json'.format(redmine_base_url,redmine_project_name))
    wiki_list = response_wiki_list.json()['wiki_pages']

    for wiki in wiki_list:
        response = redmine_client.get('{}/projects/{}/wiki/{}.json'.format(redmine_base_url, redmine_project_name, wiki['title']))
        wiki_page = response.json()['wiki_page']
        text = wiki_page['text']

        file_list = extractFiles(text)

        # TODO: Wikiに紐づくファイル一覧を取得し、以下のループでGitlabに移行する  
        # ファイルがそもそも取れないためコメントアウト    
        # for file_obj in file_list:
        #     file_get_response = redmine_client.get(file_obj['file_url'])

        #     # File Upload
        #     # file_get_response.content is a binary.
        #     post_response = gitlab_client.post('{}/projects/{}/wikis/attachments/'.format(gitlab_base_url, gitlab_project_name), 
        #     files={'file': (file_obj['file_name'], file_get_response.content, 'multipart/form-data') })

        #     post_response_json = post_response.json()

        #     # Replace file link
        #     text = text.replace(file_obj['file_url'], post_response_json['file_path'])       


        # Convert textile to markdown
        text = convertContent(text)

        # TODO: 内部リンクを変換する（いったんパス）

        # Create post body
        body = dict()
        body['content'] = text
        body['format'] = 'markdown'
        body['title'] = wiki_page['title']

        # Create Wiki
        # TODO: 作成してみて、情報が不足していないかどうか確認
        response = gitlab_client.post('{}/projects/{}/wikis/'.format(gitlab_base_url, gitlab_project_name), 
            json=body,
            headers={
                'Content-Type': 'application/json;charset=utf-8'
        })
