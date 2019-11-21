#!/usr/bin/python

import os
import re
import sys

project_dir = '/Users/yuencong/workplace/Modular'

file_path_map = {}
module_path_map = {}
related_headers_map = {}
module_umbrella_map = {}
framework_header_map = {}
filename_class_map = {}

def get_related_headers(header, ignore_headers):
    if not header:
        return None
    header_path = file_path(header)
    if not header_path or not os.path.isfile(header_path):
        return None
    if header in related_headers_map:
        return related_headers_map[header]

    related_headers = set([header])

    file = open(header_path, 'r')
    for line in file.readlines():
        result = re.compile('^\#import\s*\"(\w+\.h)\"').findall(line)
        if result:
            related_headers.add(result[0])
            continue

        result = re.compile('^@import\s*(\w+)').findall(line)
        if result:
            umbrella = module_umbrella(result[0])
            if umbrella:
                related_headers.add(umbrella)
                continue
        result = re.compile('#import\s+<\w*\/?(\w+\+?\w+\.h)').findall(line)
        if result:
            related_headers.add(result[0])
            continue
    file.close()
    
    ignore_headers.add(header)
    pending_headers = related_headers - ignore_headers
    if len(pending_headers) > 0:
        for pending_header in pending_headers:
            sub_related_headers = get_related_headers(pending_header, set(ignore_headers))
            if sub_related_headers:
                related_headers = related_headers.union(sub_related_headers)
    inter_headers = related_headers.intersection(pending_headers)
    for inter_header in inter_headers:
        if inter_header in related_headers_map:
            related_headers.union(related_headers_map[inter_header])
    related_headers_map[header] = related_headers
    return related_headers


def module_umbrella(module):
    if module in module_umbrella_map:
        return module_umbrella_map[module]
    project_dir = '/'.join(sys.path[0].strip().split('/')[0:-1])
    if len(module_path_map) == 0:
        for line in os.popen('find %s -name \"*.modulemap\"' % project_dir).readlines():
            line = line.strip()
            name = line.split('/')[-1].replace('.modulemap', '')
            module_path_map[name] = line
    if not module in module_path_map:
        return None
    path = module_path_map[module]
    file = open(path, 'r')
    umbrella = None
    for line in file.readlines():
        result = re.compile('umbrella header \"(.*)\"').findall(line)
        if result:
            umbrella = result[0]
    module_umbrella_map[module] = umbrella
    return umbrella


def file_symbols(path):
    if not path or not os.path.isfile(path):
        return None
    filename = path.split('/')[-1]
    file = open(path, 'r')
    symbols = set()
    lines = file.readlines()
    lines_sum = len(lines)
    for index in range(lines_sum):
        line = lines[index]
        #delete description
        line = re.sub('\".*\"', '', line)
        #delete annotation
        line = re.sub('//\s*.*', '', line)
        #match enum
        enum_type = None
        result = re.compile('(NS_OPTIONS|NS_ENUM){1}\s*\(\s*\w+\s*,\s*(\w+)\s*\)').findall(line)
        if result:
            enum_type = result[0][-1]
        else:
            result = re.compile('typedef\s*enum\s*(\w+)\s*:').findall(line)
            if result:
                enum_type = result[0]
        if enum_type:
            symbols.add(enum_type)
            index = index + 1
            while index < lines_sum and '}' not in lines[index]:
                line = lines[index]
                result = re.compile('(\w*%s\w*)' % enum_type).findall(line)
                if result:
                    symbols.add(result[0])
                index = index + 1
            continue
        #match extern
        if line.startswith('extern'):
            result = re.compile('(\w+)\s*;').findall(line)
            if result:
                symbols.add(result[0])
                continue
            result = re.compile('(\w+)\(.*\)\s*;').findall(line)
            if result:
                symbols.add(result[0])
            continue
        #match define
        result = re.compile('^\s*#define\s+(\w+)').findall(line)
        if result:
            symbols.add(result[0])
            continue
        #match static
        if line.startswith('static'):
            result = re.compile('(\w+)\s*=').findall(line)
            if result:
                symbols.add(result[0])
            continue
        #match interface
        result = re.compile('^\s*@interface\s+(\w+)\s*:').findall(line)
        if result:
            symbols.add(result[0])
            if filename in filename_class_map:
                filename_class_map[filename].add(result[0])
            else:
                filename_class_map[filename] = set([result[0]])
            continue
        #match protocol
        result = re.compile('^\s*@protocol\s+(\w+)\s*').findall(line)
        if result:
            symbols.add(result[0])
            continue

    symbols = symbols - filter_symbols()
    return symbols


def invoke_h_files(filename, symbols):
    if not filename or not symbols or len(symbols) == 0:
        return
    files = set()
    md5_values = set()
    for line in os.popen('find %s -name \"*.h\"' % project_dir).readlines():
        line = line.strip()
        classname = line.split('/')[-1]
        if classname in files:
            continue
        if not os.access(line, os.R_OK) or not os.access(line, os.W_OK):
            continue
        related_headers = get_related_headers(classname, set())
        if filename in related_headers:
            continue

        invoke_symbols = set()
        ignore_symbols = set()
        super_symbols = set()
        file = open(line, 'r')
        for sub_line in file.readlines():
            #delete description
            sub_line = re.sub('\".*\"', '', sub_line)
            #delete annotation
            sub_line = re.sub('//\s*.*', '', sub_line)
            #match enum
            if len(sub_line) == 0:
                continue
            for symbol in symbols:
                if symbol in sub_line:
                    result = re.compile('^@class').findall(sub_line)
                    if result:
                        if string_contains_symbol(symbol, sub_line):
                            continue
                        ignore_symbols.add(symbol)
                        continue
                    if string_contains_symbol(symbol, sub_line):
                        continue
                    result = re.compile('@interface\s+%s' % symbol).findall(sub_line)
                    if result:
                        ignore_symbols.add(symbol)
                        continue
                    result = re.compile('@interface\s*\w+\s*:\s*(%s)' % symbol).findall(sub_line)
                    if result:
                        super_symbols.add(symbol)
                        invoke_symbols.add(symbol)
                        continue
                    invoke_symbols.add(symbol)
        file.close()
        invoke_symbols = invoke_symbols - ignore_symbols
        if len(invoke_symbols) == 0:
            continue
        print '--- --- --- --- --- ---'
        print 'insert header: ' + filename
        print 'invoke file: ' + classname
        print 'invoke symbols: ' + ','.join(invoke_symbols)
        print '--- --- --- --- --- ---\n\n'

        atclass_symbols = set()
        for invoke_symbol in set(invoke_symbols):
            if filename in filename_class_map and invoke_symbol in filename_class_map[filename] and invoke_symbol not in super_symbols:
                invoke_symbols.remove(invoke_symbol)
                atclass_symbols.add(invoke_symbol)
        if len(invoke_symbols) == 0:
            for atclass_symbol in atclass_symbols:
                modify_h_file(line, True, atclass_symbol)
        else:
            modify_h_file(line, False, filename)
        files.add(classname)


def modify_h_file(path, atclass, insert_header_name):
    import_index = -1
    atclass_index = -1
    count_index = -1
    macro_start = -1
    macro_end = -1
    macro_last_import = -1
    first_space_index = -1

    file = open(path, 'r')
    lines = file.readlines()
    for line in lines:
        count_index = count_index + 1

        if re.compile('@interface').findall(line):
            break

        if first_space_index == -1 and len(line.strip()) == 0:
            first_space_index = count_index
            continue

        result = re.compile('^#import').findall(line)
        if result:
            import_index = count_index
            continue

        result = re.compile('^@class').findall(line)
        if result:
            atclass_index = count_index
            continue

        if re.compile('#ifn?def').findall(line):
            macro_start = count_index
            macro_last_import = import_index
            continue

        if re.compile('#endif').findall(line):
            macro_end = count_index
            continue

    if import_index > macro_start and import_index < macro_end:
        import_index = macro_last_import
    
    filename = path.strip().split('/')[-1]
    if atclass:
        if atclass_index == -1:
            if import_index == -1:
                atclass_index = first_space_index
            else:
                atclass_index = import_index + 1
            lines.insert(atclass_index + 1, '\n')
        lines.insert(atclass_index + 1, '@class %s;\n' % insert_header_name.replace('.h', ''))
    else:
        if import_index == -1:
            import_index = first_space_index
        if insert_header_name in framework_header_map:
            insert_header_name = framework_header_map[insert_header_name]
            lines.insert(import_index + 1, '#import %s\n' % insert_header_name)
        else:
            lines.insert(import_index + 1, '#import \"%s\"\n' % insert_header_name)

    with open(path, 'w') as file:
        for line in lines:
            file.write(line)
        file.close()
    
    if filename in related_headers_map:
        related_headers_map.pop(filename)


def invoke_m_files(filename, symbols):
    if not filename or not symbols or len(symbols) == 0:
        return
    print 'Delete File: %s\n' % filename 
    print 'Match symbols: %s\n' % '\n'.join(symbols)
    files = set()
    md5_values = set()
    for line in os.popen('find %s -name \"*.m\"' % project_dir).readlines():
        line = line.strip()
        classname = line.split('/')[-1]
        if classname in files:
            continue
        if not os.access(line, os.R_OK) or not os.access(line, os.W_OK):
            continue
        relatedfiles = get_related_headers(classname, set())
        if filename in relatedfiles:
            continue

        invoke_symbols = set()
        file = open(line, 'r')
        for sub_line in file.readlines():
            #delete description
            sub_line = re.sub('\".*\"', '', sub_line)
            #delete annotation
            sub_line = re.sub('//\s*.*', '', sub_line)
            #match enum
            if len(sub_line) == 0:
                continue
            for symbol in symbols:
                if symbol in sub_line:
                    if string_contains_symbol(symbol, sub_line):
                        continue
                    invoke_symbols.add(symbol)
        file.close()
        if len(invoke_symbols) == 0:
            continue

        modify_m_file(line, filename)
        files.add(classname)
        print '--- --- --- --- --- ---'
        print 'insert header: ' + filename
        print 'invoke file: ' + classname
        print 'invoke symbols: ' + ','.join(invoke_symbols)
        print '--- --- --- --- --- ---\n\n'


def modify_m_file(path, insert_stirng):
    import_index = -1
    count_index = -1
    macro_start = -1
    macro_end = -1
    macro_last_import = -1
    first_space_index = -1

    file = open(path, 'r')
    lines = file.readlines()
    for line in lines:
        count_index = count_index + 1
        if re.compile('@interface').findall(line) or re.compile('@implementation').findall(line):
            break

        if first_space_index == -1 and len(line.strip()) == 0:
            first_space_index = count_index
            continue

        result = re.compile('^#import').findall(line)
        if result:
            import_index = count_index
            continue

        if re.compile('#ifn?def').findall(line):
            macro_start = count_index
            macro_last_import = import_index
            continue

        if re.compile('#endif').findall(line):
            macro_end = count_index
            continue

    if import_index > macro_start and import_index < macro_end:
        import_index = macro_last_import
    
    filename = path.strip().split('/')[-1]
    if import_index == -1:
        import_index = first_space_index
        if len(lines[first_space_index + 1].strip()) != 0:
            lines.insert(import_index + 1, '\n')

    if insert_stirng in framework_header_map:
        insert_stirng = framework_header_map[insert_stirng]
        lines.insert(import_index + 1, '#import %s\n' % insert_stirng)
    else:
        lines.insert(import_index + 1, '#import \"%s\"\n' % insert_stirng)

    with open(path, 'w') as file:
        for line in lines:
            file.write(line)
        file.close()


def string_contains_symbol(symbol, line):
    result = re.compile('\w*%s\w*' % symbol).findall(line)
    if result and symbol in result:
        return False
    return True


def filter_symbols():
    return set(['UIImageView', 'UIImage', 'sharedInstance', 'NS_DESIGNATED_INITIALIZER', '_name'])


def filter_headers():
    headers = set(['Masonry.h', 'Mantle.h'])
    results = set()
    for header in headers:
        results = results.union(get_related_headers(header, set()))
    return results


def file_path(filename):
    if len(file_path_map) == 0:
        for line in os.popen('find %s -name \"*.[h|m]\"' % project_dir).readlines():
            line = line.strip()
            name = line.split('/')[-1]
            result = re.compile('(\w+)\.framework/Headers').findall(line)
            if result:
                framework_header_map[name] = '<%s/%s>' % (result[0], name)
            file_path_map[name] = line
        for line in os.popen('find %s -name \"*.pch\"' % project_dir).readlines():
            line = line.strip()
            name = line.split('/')[-1]
            file_path_map[name] = line
    if filename in file_path_map:
        return file_path_map[filename]
    return None


if __name__ == '__main__':
    # pch_path = '/'.join(sys.path[0].strip().split('/')[0:-1]) + '/Tutor/Application/TutorPrefixFile.pch'
    # headers = related_headers('TutorPrefixFile.pch', pch_path, set())

    # filename = 'TTCommonPrefix.h'
    # path = file_path(filename)
    # symbols = file_symbols(path)
    # headers = get_related_headers(filename,set())
    # print headers
    # exit(0)

    # print file_symbols(file_path('TTNetworkConstants.h'))
    # exit(0)

    # modify_m_file(file_path('TTEpisodeModifyViewController.m'), 'TTAlertUtilss')
    # exit(0)

    # filename = raw_input('\nFile that need to be processed:\n').strip()
    # filename = 'TTHasLoadingIndicator.h'

    filename = 'TTDateAgent.h'
    headers = get_related_headers(filename, set())
    headers = headers - filter_headers()
    print 'Filename: ' + filename
    print 'Related Headers:\n%s\n' % '\n'.join(headers)
    for header in headers:
        symbols = file_symbols(file_path(header))
        invoke_h_files(header, symbols)

    for header in headers:
        symbols = file_symbols(file_path(header))
        invoke_m_files(header, symbols)

    # header = 'Masonry.h'
    # symbols = set(['mas_makeConstraints','mas_remakeConstraints','mas_updateConstraints'])
    # invoke_m_files(header, symbols)