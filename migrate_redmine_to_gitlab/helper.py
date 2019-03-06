#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os


def _readFile(path,readCallback):
    try:
        with open(path, 'r',encoding='utf-8') as f:
            return readCallback(f)
    except FileNotFoundError as e:
        print("読み込むファイルが存在しません。")
        raise e
        
def getLineListFromFile(path):
    return _readFile(path, lambda f : f.readlines())

def getJsonFromFile(path):
    return _readFile(path,lambda f: json.load(f))

def writeFile(path,text_list_String, is_byte = False):
    if is_byte:
        with open(path, 'wb') as f:
            f.write(text_list_String)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(text_list_String)


def getFileList(path, extension, is_include_path = False):
        
        if is_include_path:
                array = [ os.path.join(path, file_name) for file_name in os.listdir(path) if os.path.isfile(os.path.join(path, file_name)) and file_name.endswith(extension) ]        
        else:
                array = [ file_name for file_name in os.listdir(path) if os.path.isfile(os.path.join(path, file_name)) and file_name.endswith(extension) ]
        return array