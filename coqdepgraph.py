#!/usr/bin/env python

import sys
import os
import re
import subprocess

COQPROJECT = "_CoqProject"
FILENAME_OUT = "deps-{}.pdf"
# Some categorical coulor schemes recognised by dot: pastel19, set312
# http://www.graphviz.org/doc/info/colors.html#brewer
# A scheme is the name and the number of colours defined by the colour scheme
COLOUR_SCHEME = ('pastel19', 9)
COLOUR_SCHEME = ('set312', 12)
COLOUR_SCHEME_NAME = COLOUR_SCHEME[0]
N_COL = COLOUR_SCHEME[1]

BASE_STYLE = "rounded,filled"

def dot_prefix(s):
    l = re.split('\\.[^.]+$', s)
    if len(l) <= 1 :
        return ''
    return l[0]

def dot_split(s):
    return re.split('\\.', s)

def all_prefixes(path):
    # only add the empty prefix if we actually start with a direct name
    # otherwise it'll always get allocated a colour even though it doesn't occur
    if dot_prefix(path) == '' :
        return set([''])
    prefixes = set()
    while True :
        pre = dot_prefix(path)
        if len(pre) > 0 :
            prefixes.add(pre)
            path = pre
        else :
            break
    return prefixes

def shared_prefixes(paths):
    all_prefs = [all_prefixes(path) for path in paths]
    if (all_prefs == []) :
        return set()
    shared = all_prefs.pop()
    while not (all_prefs == []) :
        prefs = all_prefs.pop()
        shared = shared.intersection(prefs)
    return shared

def longest_shared_prefix(paths):
    shared = shared_prefixes(paths)
    shared = sorted(list(shared), key=len, reverse=True)
    if len(shared) == 0 :
        return ''
    return shared[0]

def module_prefixes(modules):
    return list(set([prefix for name in modules for prefix in all_prefixes(name)]))

def module_prefixes_count(paths):
    prefixes = [prefix for path in paths for prefix in all_prefixes(path)]
    return [ (x, prefixes.count(x)) for x in set(prefixes) ]

def key_prefix_count(prefix):
    return (len(dot_split(prefix[0])), -prefix[1])

def sort_prefixes_count(prefixes):
    return sorted(prefixes, key=key_prefix_count)

missing_colours = 0
merged_prefixes = set()

def colour(prefix, sorted_prefixes):
    global missing_colours
    global merged_prefixes
    # if prefix == '' :
    #     return 0
    try :
        i = sorted_prefixes.index(prefix)+1
    except ValueError :
        # print("Warn: hit ValueError on prefix '{}'".format(prefix))
        # default to the least-used colour
        return N_COL
    if i > N_COL :
        missing_colours = missing_colours + 1
        merged_prefixes.add(prefix)
        return colour(dot_prefix(prefix), sorted_prefixes)
    return i

def colour_dict(sorted_prefixes):
    return {prefix : colour(prefix, sorted_prefixes)
            for prefix in sorted_prefixes}

def rewrite_modules(coqproject=COQPROJECT):
    abbrev = dict()
    with open(coqproject, 'r') as f :
        for l in f.readlines() :
            x = re.match('^[ \\t]*-Q[ \\t]+(?P<from>\\w+)[ \\t]+(?P<to>\\w+)$', l)
            if not (x is None) :
                abbrev[x['from']] = x['to']
    return abbrev

def deps_from_coq(coqproject=COQPROJECT):
    coqdep_args = ["coqdep", "-vos", "-dyndep", "var", "-f", coqproject]
    # If the coqproject doesn't list any .v files, we look for them via find(1)
    # and pass them to coqdep(1) explicitly.
    use_find = True
    with open(coqproject, 'r') as f :
        for l in f.readlines() :
            x = re.match('^[ \\t]*\\S+\\.v', l)
            if not (x is None) :
                use_find = False
                break
    if use_find :
            coqfiles = subprocess.run(["find", ".", "-regex", "\\.[0-9a-zA-Z_/]+.v"], capture_output=True).stdout
            coqfiles = coqfiles.decode().splitlines()
            coqfiles = [re.sub('^\\./', '', f) for f in coqfiles]
            # coqfiles = coqfiles[0:len(coqfiles)]
            # coqfiles = " ".join(coqfiles)
            # coqdep_args.append(coqfiles)
            coqdep_args = coqdep_args + coqfiles
    lines = subprocess.run(coqdep_args,capture_output=True).stdout
    lines = lines.decode().splitlines()
    abbrev = rewrite_modules(coqproject)
    z = []
    for line in lines :
        for k, v in abbrev.items() :
            line = re.sub('(^|\\s){}/'.format(k), '\\1{}/'.format(v), line)
        line, n = re.subn('\\.vo.*:\\s+\\S*\\.v', '', line)
        if n > 0 :
            line = re.sub('\\.vo\\S*', '', line)
            line = re.sub('/', '.', line)
            src_dests = line.split(maxsplit=1)
            src = src_dests[0]
            if not name_filter_p(src) :
                continue
            if len(src_dests) > 1 :
                dests = src_dests[1].split()
                dests = [ d for d in dests if name_filter_p(d) ]
            else :
                dests = []
            z.append((src, dests))
    return z

def strip_shared(path, shared):
    n = len(shared)
    if n > 0 :
        return path[n+1:]
    return path

def strip_shared_from_deps(deps,shared):
    return [(strip_shared(src,shared), [strip_shared(d,shared) for d in ds]) for (src,ds) in deps]

def pp_dep(src, dests, colours):
    col = colours[dot_prefix(src)]
    res = [ '"{}" [fillcolor={}]'.format(src, col) ]
    for d in dests :
        res.append('"{}" -> "{}"'.format(src, d))
    return res


if len(sys.argv) == 2 :
    filter_keep = sys.argv[1]
    def name_filter_p(p):
        return not (re.search(filter_keep, p) is None)
elif len(sys.argv) > 2 :
    filter_keep = sys.argv[1]
    filter_drop = sys.argv[2]
    def name_filter_p(p):
        return (not (re.search(filter_keep, p) is None)) and (re.search(filter_drop, p) is None)
else :
    def name_filter_p(p):
        return True


deps = deps_from_coq()
modules = [ m for ms in [[x[0]] + x[1] for x in deps] for m in ms ]
longest_shared = longest_shared_prefix(modules)
deps = strip_shared_from_deps(deps, longest_shared)
modules = [ m for ms in [[x[0]] + x[1] for x in deps] for m in ms ]

prefixes = module_prefixes_count(modules)
sorted_prefixes_counted = sort_prefixes_count(prefixes)
sorted_prefixes = [ x[0] for x in sorted_prefixes_counted ]

colours = colour_dict(sorted_prefixes)
pp_deps = [pp_dep(src, dests, colours) for src, dests in deps]

preamble = ['digraph interval_deps {',
            'labelloc="b" labeljust="l" label = "Prefix: {}"'.format(longest_shared),
            'node [shape=box, style="{}", URL="html/\\N.html", colorscheme={}];'.format(BASE_STYLE, COLOUR_SCHEME_NAME)]
postamble = ['}']
pp_deps_str = '\n'.join(['\n'.join(l) for l in [preamble] + pp_deps + [postamble]])

p_out = subprocess.run(['tred'],
                       text=True, capture_output=True, input=pp_deps_str).stdout
p_out = subprocess.run(['gvpr', '-c', 'N[outdegree == 0]{shape="doubleoctagon"}'],
                       text=True, capture_output=True, input=p_out).stdout
p_out = subprocess.run(['gvpr', '-c', 'N[indegree == 0]{penwidth=5,color=red}'],
                       text=True, capture_output=True, input=p_out).stdout
if longest_shared == '' :
    longest_shared = os.path.basename(os.getcwd())
with open(FILENAME_OUT.format(longest_shared), 'w') as f_out :
    # '-Gnodesep=1',
    subprocess.run(['dot', '-Granksep=1', '-T', 'pdf'], text=True, input=p_out, stdout=f_out)

if (missing_colours > 0) :
    print("The colour theme '{}' defines {} colours, {} more colours are needed for full disambiguation.".format(COLOUR_SCHEME_NAME, N_COL, missing_colours))
    print("Colours: {}".format(colours))
    print("The following prefixes got merged into their parent: {}".format(sorted(merged_prefixes, key=lambda prefix : (len(dot_split(prefix)), prefix))))

# TODO: try to sort by prefix count only instead of prioritising nesting depth.
