#!/usr/bin/python
# -*- coding: utf-8  -*-
"""
Sanity checker for data

Notes:
    P373 is Commonscat
    P1472 is Creator-template

@todo: Deprecate and move last bits to make_SMM_info

This is largely deprecated but still contains some bits for making mapping lists
which should be preserved.
"""

import batchupload.helpers as helpers  # must therefore run from parent dir
import batchupload.common as common  # temp before this is merged with helper
import batchupload.csv_methods as csv_methods
import codecs
import os
import batchupload.listscraper as listscraper
import urllib2
import json
CWD_PATH = u'SMM-images'
OUT_PATH = u'connections'
filenameList = {}
keywordList = {}
personList = {}
ortList = {}
materialList = {}
benamningList = {}
kNavList = {}
infile = ''

# black-listed
badNamn = (u'Okänd fotograf', u'Okänd konstnär')
badDate = (u'odaterad', )


def run(filename):
    global infile
    infile = filename
    setCWD(filename)
    header, lines = csv_methods.open_csv_file(infile)
    testLabels(header)
    logs = {}
    idnos = []
    for l in lines:
        idno, log = checkLine(l.strip(), idnos)
        idnos.append(idno)
        if len(log) > 0:
            logs[idno] = log

    # output log and lists
    f = codecs.open(u'%s.log' % infile, 'w', 'utf8')
    for key, log in logs.iteritems():
        f.write(u'%s: %s\n' % (key, log))
    f.close()

    dumpToList(u'keywords', keywordList)
    dumpToList(u'people', personList)
    dumpToList(u'places', ortList)
    dumpToList(u'materials', materialList)

    # filename style
    f = codecs.open(u'%s.filenames.txt' % infile, 'w', 'utf8')
    no = 0
    for k, v in filenameList.iteritems():
        if v['descr'] is not None:
            no += 1
        else:
            v['descr'] = ''
    f.write(u'%d of %d files got filenames\n' % (no, len(lines)))
    for key, name in filenameList.iteritems():
        f.write(u'%s|%s|%s\n' % (key, name['typ'], name['descr']))
    f.close()

    print secondaryKeywordTest(lines)

    print 'Done'


def setCWD(filename):
    """
    set CWD_PATH baed on infile
    """
    global CWD_PATH
    CWD_PATH = os.path.split(filename)[0]


def checkLine(line, idnos):
    if len(line) == 0:
        return '', ''

    log = []
    params = line.split('|')

    idno = params[0].strip()
    typ = params[1].strip()
    benamning = params[2].strip()
    material = params[3].strip().split(',')
    namn_konstnar = helpers.flip_name(params[4].strip())
    namn_konstnar_knav = params[5].strip()
    namn_konstruktor = [params[6].strip(), ]
    namn_konstruktor_knav = params[7].strip()
    namn_konstruktor.append(params[8].strip())
    namn_fotograf = params[9].strip()
    namn_tillverkare = [params[10].strip(), ]
    namn_tillverkare.append(params[11].strip())
    namn_tillverkare.append(params[12].strip())
    date_foto = params[13].strip()
    date_produktion = params[14].strip()
    avbildad_namn = [helpers.flip_name(params[15].strip()), ]
    avbildad_namn_knav = params[16].strip()
    avbildad_namn.append(params[17].strip())
    avbildad_namn.append(params[18].strip())
    avbildad_ort = params[19].strip()
    amnesord = params[20].strip().split(',')
    beskrivning = params[21].strip()
    motiv_amnesord = params[22].strip().split(',')
    motiv_beskrivning = params[23].strip()
    rattighet = params[24].strip()
    samling = params[25].strip()
    dimukod = params[26].strip()

    # cleanup lists
    material = common.trim_list(material)
    namn_tillverkare = common.trim_list(namn_tillverkare)
    avbildad_namn = common.trim_list(avbildad_namn)
    namn_konstruktor = common.trim_list(namn_konstruktor)
    amnesord = common.trim_list(amnesord)
    motiv_amnesord = common.trim_list(motiv_amnesord)

    # kNav
    if len(namn_konstnar_knav) > 0:
        addTokNavList(namn_konstnar_knav, namn_konstnar)
    if len(avbildad_namn_knav) > 0:
        addTokNavList(avbildad_namn_knav, avbildad_namn[0])
    if len(namn_konstruktor_knav) > 0:
        addTokNavList(avbildad_namn_knav,
                      helpers.flip_name(namn_konstruktor[0]))

    log.append(testId(idno, idnos))
    log.append(checkType(typ))
    log.append(testRight(rattighet))
    log.append(testCollection(samling))
    log.append(testKeywords(amnesord, motiv_amnesord, benamning))
    log.append(testDescription(beskrivning, motiv_beskrivning))
    for namn in namn_tillverkare:
        log.append(testName(namn))
    for namn in avbildad_namn:
        log.append(testName(namn))
    for namn in namn_konstruktor:
        log.append(testName(namn))
    log.append(testName(namn_fotograf))
    log.append(testName(namn_konstnar))
    log.append(testName(namn_fotograf))
    log.append(testDateRange(date_foto))
    log.append(testDateRange(date_produktion))

    # test filenames
    log.append(
        testNameGeneration(idno, typ, benamning, motiv_beskrivning,
                           avbildad_namn, avbildad_ort, date_foto,
                           date_produktion))

    # some counters
    if len(avbildad_ort) > 0:
        helpers.addOrIncrement(ortList, avbildad_ort)
    for m in material:
        helpers.addOrIncrement(materialList, m.lower())
    if len(benamning) > 0:
        helpers.addOrIncrement(benamningList, benamning.lower())

    # compile and return
    logtext = ''
    for l in log:
        if l:
            logtext += u'%s. ' % l
    return idno, logtext.strip()


def testLabels(line):
    labels = u'Identifikationsnr|Typ av objekt|Benämning|Material|' + \
             u'Namn-Konstnär|KulturNav|Namn-Konstruktör|KulturNav|' + \
             u'Namn-Konstruktör|Namn-Fotograf|Namn-Tillverkare|' + \
             u'Namn-Tillverkare|Namn-Tillverkare|Datering-Fotografering|' + \
             u'Datering-Produktion|Avbildade namn|KulturNav|' + \
             u'Avbildade namn|Avbildade namn|Avbildade - orter|' + \
             u'Ämnesord|Beskrivning|Motiv-ämnesord|Motiv-beskrivning|' + \
             u'Rättigheter|Samling|Dimukode'
    if line != labels.split('|'):
        print u'The labels or their order have changed, please update checker'
        exit(1)


def checkType(typ):
    if typ not in (u'Foto', u'Föremål'):
        return u'Udda typ: %s' % typ


def testId(idno, idnos):
    if idno in idnos:
        return u'Duplicate id'


def testRight(rattighet):
    if rattighet not in (u'Erkännande-Dela lika', u'Utgången skyddstid'):
        return u'Udda rättighet: %s' % rattighet


def testCollection(samling):
    if samling not in (u'Sjöhistoriska museet', u'Vasamuseet'):
        return u'Udda samling: %s' % samling


def testKeywords(amnesord, motiv_amnesord, benamning):
    keywords = amnesord + motiv_amnesord + [benamning, ]
    keywords = common.trim_list(keywords)
    if len(keywords) < 1:
        return u'Inga ämnesord'

    for k in keywords:
        helpers.addOrIncrement(keywordList, k.lower())


def testNameGeneration(idno, typ, benamning, motiv_beskrivning,
                       avbildad_namn, avbildad_ort, date_foto,
                       date_produktion):
    need_more = (u'Fartygsmodell', u'Fartygsporträtt', u'Marinmotiv',
                 u'Modell', u'Ritning', u'Teckning', u'Akvarell', u'Karta',
                 u'Kopparstick', u'Lavering', u'Sjökort', u'Sjöstrid',
                 u'Porträtt')
    txt = u''
    if typ == u'Foto':
        if len(avbildad_namn) > 0:
            txt += ', '.join(helpers.flip_names(avbildad_namn))
            if len(txt) > 0 and len(avbildad_ort) > 0:
                txt += u'. '
            txt += avbildad_ort
            # only add date if other info
            if date_foto.lower() != u'odaterad':
                if len(txt) > 0 and len(date_foto) > 0:
                    txt += u'. '
                txt += date_foto
        elif len(motiv_beskrivning) > 0:
            txt += motiv_beskrivning
        if len(txt) == 0:
            filenameList[idno] = {'typ': typ, 'descr': None}
            return u'Inget namn kan genereras (foto3)'
    if typ == u'Föremål':
        txt += benamning
        if len(benamning) == 0:
            filenameList[idno] = {'typ': typ, 'descr': None}
            return u'Inget namn kan genereras (föremål3)'
        elif benamning in need_more:
            txt2 = ''
            if len(avbildad_namn) > 0:
                txt2 += ', '.join(helpers.flip_names(avbildad_namn))
            elif len(motiv_beskrivning) > 0:
                txt2 += motiv_beskrivning
            else:
                filenameList[idno] = {'typ': typ, 'descr': None}
                return u'Inget namn kan genereras (föremål3 med need_more)'
            if len(avbildad_ort) > 0:
                txt2 += u'. %s' % avbildad_ort
            if len(date_produktion) > 0 and \
                    date_produktion.lower() != u'odaterad':
                txt2 += u'. %s' % date_produktion
            txt = u'%s-%s' % (txt, txt2)
    txt = helpers.cleanString(txt)
    txt = helpers.touchup(txt)
    filenameList[idno] = {'typ': typ, 'descr': helpers.shortenString(txt)}


def testDescription(beskrivning, motiv_beskrivning):
    if len(beskrivning) + len(motiv_beskrivning) == 0:
        return u'Ingen beskrivning'
    # if len(beskrivning) > 0 and len(motiv_beskrivning) > 0:
    #    return u'Dubbel beskrivning'


def testName(namn):
    if len(namn) == 0:
        return None
    elif namn in badNamn:
        return None
    elif len(namn.split(',')) not in (1, 2):
        return u'För många komman i ett namn: %s' % namn
    elif namn.endswith(','):
        return u'Namn slutar med komma: %s' % namn
    helpers.addOrIncrement(personList, helpers.flip_name(namn))


def testDateRange(date):
    if len(date) == 0:
        return None
    elif ' - ' in date:
        dates = date.split(' - ')
        if len(dates) != 2:
            return u'Weirdly formated date range: %s' % date
        logs = []
        for d in dates:
            logs.append(testDate(d))
        log = ''
        for l in logs:
            if l:
                log += u'%s. ' % l
        if len(log) > 0:
            return log.strip()
    else:
        if date.lower() in badDate:
            return testDate(date)


def testDate(date):
    '''
    Check that a date is YYYY or YYYY-MM or YYYY-MM-DD
    '''
    date = date.lower().strip('ca ')
    item = date[:len('YYYY-MM-DD')].split('-')
    if len(item) == 3 and all(common.is_pos_int(x) for x in item) and \
            int(item[1][:len('MM')]) in range(1, 12 + 1) and \
            int(item[2][:len('DD')]) in range(1, 31 + 1):
        # 1921-09-17Z or 2014-07-11T08:14:46Z
        return None
    elif len(item) == 1 and common.is_pos_int(item[0][:len('YYYY')]):
        # 1921Z
        return None
    elif len(item) == 2 and \
            all(common.is_pos_int(x) for x in (item[0], item[1][:len('MM')])) and \
            int(item[1][:len('MM')]) in range(1, 12 + 1):
        # 1921-09Z
        return None
    elif len(item) == 2 and common.is_pos_int(item[0][:len('YYYY')]) and \
            item[1] == u'talet':
        # 1900-talet
        return None
    else:
        return u'Weirdly formated date: %s' % date


def secondaryKeywordTest(lines):
    """
    How many files get keywords if we limit them by frequency
    """
    offset = 3
    num = 8  # 3, 4, 5, 6, 7, 8, 9, 10
    passNo = []
    for i in range(num):
        passNo.append(0)
    for l in lines:
        passed = []
        for i in range(num):
            passed.append(False)
        params = l.split('|')
        keywords = params[20].strip().split(',')
        keywords += params[22].strip().split(',')
        keywords = common.trim_list(keywords)
        for k in keywords:
            k = k.lower()
            for i in range(offset, num + offset):
                if not passed[i - offset] and keywordList[k] >= i:
                    passNo[i - offset] += 1
                    passed[i - offset] += True
    txt = u'frekvens: bilder utan kategori\n'
    for i in range(offset, num + offset):
        txt += u'%d: %d\n' % (i, len(lines) - passNo[i - offset])
    txt += u'(utav %d filer)' % len(lines)
    return txt


def addTokNavList(uuid, namn):
    """
    Add an uuid to kNavList
    """
    # Convert url to uuid
    if uuid.startswith(u'http://kulturnav.org'):
        uuid = uuid.split('/')[-1]
    if len(uuid) > 0:
        if uuid in kNavList.keys():
            if namn not in kNavList[uuid]['namn']:
                kNavList[uuid]['namn'].append(namn)
        else:
            kNavList[uuid] = {'namn': [namn, ]}


def dumpToList(desc, dictionary):
    outputWiki = None
    if desc == 'keywords':
        outputWiki = outputWikiKeyword
    elif desc == 'people':
        outputWiki = outputWikiPerson
    elif desc == 'places':
        outputWiki = outputWikiPlace
    elif desc == 'materials':
        outputWiki = outputWikiMaterials
    else:
        print 'dumpToList not implemented for: %s' % desc
        return
    listscraper.mergeWithOld(helpers.sortedDict(dictionary), desc,
                             outputWiki, working_path=CWD_PATH,
                             out_path=OUT_PATH)


def outputWikiKeyword(mapping):
    """
    output keywords in Commons format
    param mapping: list of Entries|None
    """
    # set-up
    header = u'{{user:Lokal Profil/LSH2|category=}}\n'
    row = u'{{User:Lokal Profil/LSH3\n' \
          u'|name      = %s\n' \
          u'|more      = %s\n' \
          u'|frequency = %d\n' \
          u'|category  = %s\n' \
          u'}}\n'
    footer = u'|}\n'
    intro = u'Set commonsconnection of irrelevant keywords to "-"\n\n' \
            u'Multiple categories are separated by "/"\n' \
            u'===Keyword|frequency|description|commonsconnection===\n'

    # output
    preserved = False
    wiki = u''
    wiki += intro
    wiki += header
    for m in mapping:
        if m is None:
            continue
        if not preserved and m[u'frequency'] == 0:
            preserved = True
            wiki += footer
            wiki += u'\n===Preserved mappings===\n'
            wiki += header
        wiki += row % (m[u'name'][0],
                       '/'.join(m[u'more']),
                       m[u'frequency'],
                       '/'.join(m[u'category']))
    wiki += footer
    return wiki


def outputWikiPlace(mapping):
    """
    output place in Commons format
    param mapping: list of Entries|None
    """
    # set-up
    header = u'{{user:Lokal Profil/LSH2|name=Place|' \
             u'other=Commons connection}}\n'
    row = u'{{User:Lokal Profil/LSH3\n' \
          u'|name      = %s\n' \
          u'|frequency = %d\n' \
          u'|other     = %s\n' \
          u'}}\n'
    footer = u'|}\n'
    intro = u'The preferred order of making connections are: page, category' \
            u'(where the category is prefixed by a ":").\n\n' \
            u'Set commonsconnection of irrelevant places to "-"\n\n' \
            u'===Place|Frequency|Commonsconnection===\n'
    # output
    preserved = False
    wiki = u''
    wiki += intro
    wiki += header
    for m in mapping:
        if m is None:
            continue
        if not preserved and m[u'frequency'] == 0:
            preserved = True
            wiki += footer
            wiki += u'\n===Preserved mappings===\n'
            wiki += header
        wiki += row % (m[u'name'][0],
                       m[u'frequency'],
                       '/'.join(m[u'other']))
    wiki += footer
    return wiki


def outputWikiMaterials(mapping):
    """
    output materials in Commons format
    param mapping: list of Entries|None
    """
    # set-up
    header = u'{{user:Lokal Profil/LSH2|name=Technique/material|technique=}}\n'
    row = u'{{User:Lokal Profil/LSH3\n' \
          u'|name      = %s\n' \
          u'|frequency = %d\n' \
          u'|technique = %s\n' \
          u'}}\n'
    footer = u'|}\n'
    intro = u'commonsconnection is the relevant parameter for ' \
            u'{{tl|technique}}. Don\'t forget to add a translation in ' \
            u'Swedish at [[Template:Technique/sv]]\n\n' \
            u'Set commonsconnection of irrelevant technique/material ' \
            u'to "-".\n\n' \
            u'===technique/material|frequency|commonsconnection===\n'
    # output
    preserved = False
    wiki = u''
    wiki += intro
    wiki += header
    for m in mapping:
        if m is None:
            continue
        if not preserved and m[u'frequency'] == 0:
            preserved = True
            wiki += footer
            wiki += u'\n===Preserved mappings===\n'
            wiki += header
        wiki += row % (m[u'name'][0],
                       m[u'frequency'],
                       '/'.join(m[u'technique']))
    wiki += footer
    return wiki


def outputWikiPerson(mapping):
    """
    output people in Commons format
    param mapping: list of Entries|None
    @todo: needs to take other params
    """
    # process kNavList
    nameToKNav = crunchKNavList()

    # set-up
    header = u'{{user:Lokal Profil/LSH2|name=Name <small>(kulturNav)</small>' \
             u'|link=Wikidata-link|creator=|category=}}\n'
    row = u'{{User:Lokal Profil/LSH3\n' \
          u'|name      = %s\n' \
          u'|more      = %s\n' \
          u'|frequency = %d\n' \
          u'|link      = %s\n' \
          u'|creator   = %s\n' \
          u'|category  = %s\n' \
          u'}}\n'
    footer = u'|}\n'
    intro = u'Set irrelevant commonsconnection of irrelevant keywords to "-". ' \
            u'Note that creator is only relevant for artists.\n\n' \
            u'Multiple categories are separated by "/"\n' \
            u'===Name|knav|frequency|creator|link|category===\n'

    # output
    preserved = False
    wiki = u''
    wiki += intro
    wiki += header
    for m in mapping:
        if m is None:
            continue
        if not preserved and m[u'frequency'] == 0:
            preserved = True
            wiki += footer
            wiki += u'\n===Preserved mappings===\n'
            wiki += header

        # add knav stuff
        if m[u'name'][0] in nameToKNav.keys():
            namn = m[u'name'][0]
            # uuid
            if m[u'more'] and m[u'more'][-1] != nameToKNav[namn]['uuid']:
                print 'new kulturnav uuid for: %s' % namn
            else:
                uuid = u'http://kulturnav.org/%s' % nameToKNav[namn]['uuid']
                m[u'more'] = uuid.split('/')
            # wikidata
            if 'wikidata' in nameToKNav[namn].keys():
                qNo = u':d:%s' % nameToKNav[namn]['wikidata']
                if m[u'link'] and m[u'link'][-1] != qNo:
                    print u'new wikidata id for: %s ' \
                          u'(%s <-> %s)' % (namn, m[u'link'][-1], qNo)
                else:
                    m[u'link'] = [qNo, ]
            # commonscat
            if 'P373' in nameToKNav[namn].keys():
                cat = nameToKNav[namn]['P373']
                if m[u'category'] and m[u'category'][-1] != cat:
                    print u'new cat for: %s ' \
                          u'(%s <-> %s)' % (namn, m[u'category'][-1], cat)
                else:
                    m[u'category'] = [cat, ]
            # creator
            if 'P1472' in nameToKNav[namn].keys():
                creator = nameToKNav[namn]['P1472']
                if m[u'creator'] and m[u'creator'][-1] != creator:
                    print u'new creator-template for: %s ' \
                          u'(%s <-> %s)' % (namn, m[u'creator'][-1], creator)
                else:
                    m[u'creator'] = [creator, ]

        # add row
        wiki += row % (m[u'name'][0],
                       '/'.join(m[u'more']),
                       m[u'frequency'],
                       '/'.join(m[u'link']),
                       '/'.join(m[u'creator']),
                       '/'.join(m[u'category']))
    wiki += footer
    return wiki


def crunchKNavList():
    """
    Lookup uuid connections in wikidata and return a dict with name as key.
    """
    queryurl = u'https://wdq.wmflabs.org/api?q=string[1248:"%s"]' \
               u'+AND+CLAIM[373]&props=373,1248,1472'
    i = 0
    props = {'P373': [], 'P1248': [], 'P1472': []}
    while i < len(kNavList):
        # Split up into 10 uuid chunks
        ks = '",1248:"'.join(kNavList.keys()[i:i + 10])
        i += 10
        recordPage = urllib2.urlopen(queryurl % ks)
        recordData = recordPage.read()
        # fix for empty 1472 data
        recordData = recordData.replace(u',[]', u''). \
            replace(u'{[]}', u'{"hack":[]}')
        jsonData = json.loads(recordData)
        if '373' in jsonData['props']:
            props['P373'] += jsonData['props']['373']
        if '1248' in jsonData['props']:
            props['P1248'] += jsonData['props']['1248']
        if '1472' in jsonData['props']:
            props['P1472'] += jsonData['props']['1472']

    # reshuffle with Qno as key
    qDict = {}
    for key in props.keys():
        for v in props[key]:
            q = u'Q%d' % v[0]
            if q not in qDict.keys():
                qDict[q] = {key: v[2]}
            else:
                qDict[q][key] = v[2]

    # stick into kNavList
    for q, vals in qDict.iteritems():
        uuid = vals['P1248']
        kNavList[uuid]['wikidata'] = q
        if 'P373' in vals.keys():
            kNavList[uuid]['commonscat'] = vals['P373']
        if 'P1472' in vals.keys():
            kNavList[uuid]['creator'] = vals['P1472']

    # reorder by name
    nameToKNav = {}
    for uuid, vals in kNavList.iteritems():
        vals['uuid'] = uuid
        for name in vals['namn']:
            nameToKNav[name] = vals

    return nameToKNav


if __name__ == "__main__":
    import sys
    usage = '''Usage: python check_indata.py infile'''
    argv = sys.argv[1:]
    if len(argv) == 1:
        run(filename=argv[0])
    else:
        print usage
# EoF
