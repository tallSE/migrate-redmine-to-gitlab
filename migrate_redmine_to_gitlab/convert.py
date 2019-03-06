#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import sys
from helper import *

def terminateProgramFunc():
    printHelp()
    # exit program
    exit(1)

def printHelp():
    print('コマンドは以下のように入力してください。\n')
    print('python convert.py [変換元のtextileのパス] [返還後のreadmeのファイル名とパス]')
    print('ex.) python convert.py ./sample.textile ./sample.md')

def convert(row):
    row = basicListConverter(row)
    row = numberedLlistConverter(row)
    row = linkConverter(row)
    row = propertyRemover(row)
    # WARNING: headerConver must be invoked after numberedLlistConverter
    row = headerConverter(row)
    row = tableConveter(row)
    # row = preConverter(row)
    # todo: wikiの中で、同じプロジェクト内の [[ URL ]] と書かれた部分を mdの []()に変更する
    return row.rstrip()
    
def preConverter(row):
    return baseConveter('<[/]?pre>|<[/]?code.*?>', row, 'search', 
        lambda regexpString, match,row: re.sub(regexpString, '```', row))

def headerConverter(row):
    def converter(regexpString, match,row):
        sharps = ''
        for i in range(0, int(match.group(1))):
            sharps += '#'
        return re.sub(regexpString, sharps, row)

    return baseConveter('^.*h(\d{1})\.', row, 'match', converter)

def propertyRemover(row):
    return baseConveter('\*\%\{.*?\}(.*?)\%\*', row, 'match',  
        lambda regexpString, match,row: re.sub(regexpString, match.group(1), row))


def basicListConverter(row):
    row = baseConveter('^\*\*\* (.*)$', row, 'match', 
        lambda regexpString, match,row: re.sub(regexpString, '\t\t* {}'.format(match.group(1)), row))
    row = baseConveter('^\*\* (.*)$', row, 'match',  
        lambda regexpString, match,row: re.sub(regexpString, '\t* {}'.format(match.group(1)), row))
    row = baseConveter('^\* (.*)$', row, 'match', 
        lambda regexpString, match,row: re.sub(regexpString, '* {}'.format(match.group(1)), row)) 

    return row


def numberedLlistConverter(row):
    row = baseConveter('^\#\#\# (.*)$', row, 'match', 
        lambda regexpString, match,row: re.sub(regexpString, '\t\t1. {}'.format(match.group(1)), row))
    row = baseConveter('^\#\# (.*)$', row, 'match', 
        lambda regexpString, match,row: re.sub(regexpString, '\t1. {}'.format(match.group(1)), row)) 
    row = baseConveter('^\# (.*)$', row, 'match', 
        lambda regexpString, match,row: re.sub(regexpString, '1. {}'.format(match.group(1)), row))

    return row 
    

def tableConveter(row):
    row = tableHeaderConverter(row)
    row = tableBodyConverter(row)

    return row 


def tableHeaderConverter(row):
    def converter(regexpString, match, row): 
        for m in match:
            row = re.sub(regexpString, '| ', row)
        return row

    return baseConveter('\|_\.', row, 'finditer', converter)


def tableBodyConverter(row):
    def converter(regexpString, match, row): 
        row = re.sub('\|[=><]?\.', '| ', row)
        row = re.sub('\|\/\d{1}\. ', '| ', row)
        return row 

    return baseConveter('^\|', row, 'match', converter)


def linkConverter(row):
    def converter(regexpString, match, row): 
        for m in match:
            row = re.sub(regexpString, '[{}]({})'.format(m.group(1),m.group(2)), row)
        return row 

    return baseConveter('"(.*?)":([A-Za-z0-9-_\/=\?\.\:%]+)', row, 'finditer', converter)


def selectRegexpFunc(regexpString, regexpType):
    regexp = re.compile(regexpString)
    # match: 先頭に、正規表現がマッチするか
    if regexpType == 'match':
        regexpFunc = regexp.match
    # match: 先頭に、任意の位置に正規表現がマッチするか（ただし、最初のマッチ部分だけ返る）
    elif regexpType == 'search':
        regexpFunc = regexp.search
    # match: 先頭に、任意の位置に正規表現がマッチするか（全てのマッチ部分だけ返る）
    elif regexpType == 'finditer':
        regexpFunc = regexp.finditer
    else:
        regexpFunc = regexp.findall

    return regexpFunc


def addHeaderLine(row):
    def converter(regexpString, match, row): 
        header_str = ''
        
        for _ in range(0, len(match)-1):
            header_str += ' | -- '
        header_str += '|'
        return row + '\n' + header_str

    return baseConveter('\|', row, 'findall', converter)


# regexpString: 正規表現
# row: １行分のStringの文字列
# regexpType: reのどのメソッドを使うのか

# regexpString: 正規表現

def baseConveter(regexpString, row, regexpType, convertFunc):
    
    regexpFunc = selectRegexpFunc(regexpString, regexpType)

    match = regexpFunc(row)
    if(match):
        row = convertFunc(regexpString, match, row)
        
    return row     


def convertLines(line_list):
    new_line_list = []
    is_header_exists = False

    for line in line_list:
        new_line = convert(line)

        # check whether table element(header or body) or not
        if new_line.endswith('|'):
            # if line is a table header, add extra line for separate header and body
            if not is_header_exists:
                new_line = addHeaderLine(new_line)            
            is_header_exists = True
        else:
            is_header_exists = False

        new_line_list.append(new_line + '\n')
        
    return new_line_list


def convertContent(content, sepalator='\n'):
    line_list = ['{}\n'.format(elem) for elem in content.replace('\r','').split(sepalator)]
    converted_line_list = convertLines(line_list)
    return generateMarkDownStringFromList(converted_line_list)


def generateMarkDownStringFromList(target_list):
    # remove additional new line between each table header, table body
    return '\n'.join(target_list).replace('|\n\n|', '|\n|')

# if __name__ == "__main__":
#     try:
#         line_list = getLineListFromFile(sys.argv[1])
#         converted_line_list = convertLines(line_list)       
#         writeFile(sys.argv[2], generateMarkDownStringFromList(converted_line_list))
#     except FileNotFoundError as e:
#         terminateProgramFunc()