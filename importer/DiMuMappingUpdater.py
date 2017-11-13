#!/usr/bin/python
# -*- coding: utf-8  -*-
"""Create or update mapping lists."""
import os
from collections import Counter


import pywikibot
from pywikibot.data import sparql

import batchupload.common as common
from batchupload.listscraper import MappingList

SETTINGS = "settings.json"
MAPPINGS_DIR = 'mappings'
HARVEST_FILE = 'dimu_harvest_data.json'
# @todo:
#   * add scraping to load_mappings
#   * check for mappings through k_nav see check_indata.crunchKNavList
#   * proper handling of places
#   * is connection between place levels broken? Risk of mismatches?
#   * ensure load_mappings can be used by make_NM...


class DiMuMappingUpdater(object):
    """Update mappings based on data extracted from a DiMu harvester."""

    def __init__(self, options):
        """Initialise an mapping updater for a DigitaltMuseum harvest."""
        self.settings = options
        self.log = common.LogFile('', self.settings.get('mapping_log_file'))
        self.mappings = load_mappings(
            update_mappings=True,
            mappings_dir=self.settings.get('mappings_dir'))
        harvest_data = load_harvest_data(self.settings.get('harvest_file'))

        self.people_to_map = {}
        self.places_to_map = {}
        self.subjects_to_map = Counter()

        self.parse_harvest_data(harvest_data)
        self.check_and_remove_code_place_entries()
        self.dump_to_wikifiles()

    #does not correctly harvest places
    def dump_to_wikifiles(self):
        """Dump the mappings to wikitext files."""
        # places
        parameters = ['name', 'category', 'wikidata', 'frequency']
        intro_text = (
            'Places mapping table for [[Commons:Nordiska museet]].\n')
        header = '{{User:André Costa (WMSE)/mapping-head|category=|wikidata=}}'
        ml = MappingList(
            page='Commons:Nordiska_museet/mapping/places',
            parameters=parameters,
            header_template=header,
            mapping_dir=MAPPINGS_DIR)
        wikitext = intro_text
        for k, v in self.places_to_map.items():
            merged_places = ml.merge_old_and_new_mappings(
                v.most_common(), update=False)
            wikitext += ml.mappings_to_wikipage(
                merged_places, '==== {} ===='.format(k))

        wiki_file = os.path.join(
            ml.wikitext_dir, 'commons-{}.wiki'.format(ml.page_name))
        common.open_and_write_file(wiki_file, wikitext)

        # subjects
        parameters = ['name', 'category', 'frequency']
        intro_text = (
            'Keyword mapping table for [[Commons:Nordiska museet]]. '
            'Originally populated from '
            '[[Commons:Batch uploading/Nordiska Museet/keywords]].\n')
        header = '{{User:André Costa (WMSE)/mapping-head|category=}}'
        mk = MappingList(
            page='Commons:Nordiska_museet/mapping/keywords',
            parameters=parameters,
            header_template=header,
            mapping_dir=MAPPINGS_DIR)
        merged_keywords = mk.merge_old_and_new_mappings(
            self.subjects_to_map.most_common(), update=True)
        mk.save_as_wikitext(merged_keywords, intro_text)

        # people
        parameters = ['name', 'more', 'creator', 'category',
                      'wikidata', 'other', 'frequency']
        intro_text = (
            'People mapping table for [[Commons:Nordiska museet]]. '
            'Originally populated from '
            '[[Commons:Batch uploading/Nordiska Museet/creators]].\n')
        header = ('{{User:André Costa (WMSE)/mapping-head'
                  '|category=|creator=|wikidata=|other=leftover comments}}')
        mp = MappingList(
            page='Commons:Nordiska museet/mapping/people',
            parameters=parameters,
            header_template=header,
            mapping_dir=MAPPINGS_DIR)
        merged_people = mp.merge_old_and_new_mappings(
            self.format_person_data(), update=True)
        mp.save_as_wikitext(merged_people, intro_text)

        self.log.write('\n== people ==')
        for k, v in self.people_to_map.items():
            self.log.write('{}: {}'.format(v.get('data'), v.get('count')))

    def format_person_data(self):
        """Take the people_to_map data and output as ..."""
        out_data = []
        for k, v in self.people_to_map.items():
            data = v.get('data')
            entry = {}
            entry['name'] = data.get('name')
            entry['more'] = 'Roles: {}'.format('/'.join(data.get('roles')))
            if data.get('k_nav'):
                entry['more'] += ' [http://kulturnav.org/{0} {0}]'.format(
                    data.get('k_nav'))
            out_data.append((entry, v.get('count')))
        return out_data

    def parse_harvest_data(self, harvest_data):
        """Go through the harvest data breaking out data needing mapping."""
        for key, image in harvest_data.items():
            self.subjects_to_map.update(image.get('subjects'))

            if image.get('default_copyright'):
                for person in image.get('default_copyright').get('persons'):
                    self.parse_person(person)
            if image.get('copyright'):
                for person in image.get('copyright').get('persons'):
                    self.parse_person(person)

            self.parse_place(image.get('depicted_place'))
            for place in image.get('description_place').values():
                self.parse_place(place)
            if image.get('creation'):
                for place in image.get('creation').get('related_places'):
                    self.parse_place(place)
                for person in image.get('creation').get('related_persons'):
                    self.parse_person(person)
            for event in image.get('events'):
                for place in event.get('related_places'):
                    self.parse_place(place)
                for person in event.get('related_persons'):
                    self.parse_person(person)

    def parse_place(self, place_data):
        """Gather and combine place data."""
        del place_data['role']
        place_data.update(place_data.pop('other'))
        for typ, value in place_data.items():
            if typ not in self.places_to_map:
                self.places_to_map[typ] = Counter()
            self.places_to_map[typ].update((value, ))

    def parse_person(self, person_data):
        """Gather and combine person data."""
        idno = person_data.pop('id')
        role = person_data.pop('role')
        if idno not in self.people_to_map:
            person_data['roles'] = set()
            self.people_to_map[idno] = {'count': 0, 'data': person_data}
        self.people_to_map[idno]['count'] += 1
        self.people_to_map[idno]['data']['roles'].add(role)

    def check_and_remove_code_place_entries(self):
        """Go through places data, ensure codes are known then remove."""
        code_entries = ('county', 'parish', 'municipality', 'province',
                        'country')

        for typ in code_entries:
            mapped_keys = set(self.mappings.get(typ))
            unknown = set(self.places_to_map.get(typ)) - mapped_keys
            if not unknown:
                del self.places_to_map[typ]
            else:
                old_counter = self.places_to_map.pop(typ)
                self.places_to_map[typ] = Counter(
                    {k: old_counter[k]
                     for k in old_counter
                     if k not in mapped_keys})


def load_harvest_data(filename):
    filename = filename or HARVEST_FILE
    harvest_data = common.open_and_read_file(filename, as_json=True)
    return harvest_data


def load_mappings(update_mappings, mappings_dir=None):
    """
    Update mapping files, load these and package appropriately.

    :param update_mappings: whether to first download the latest mappings
    :param mappings_dir: path to directory in which mappings are found
    """
    mappings = {}
    mappings_dir = mappings_dir or MAPPINGS_DIR
    common.create_dir(mappings_dir)  # ensure it exists

    parish_file = os.path.join(mappings_dir, 'socken.json')
    muni_file = os.path.join(mappings_dir, 'kommun.json')
    county_file = os.path.join(mappings_dir, 'lan.json')
    province_file = os.path.join(mappings_dir, 'province.json')
    country_file = os.path.join(mappings_dir, 'country.json')
    people_file = os.path.join(mappings_dir, 'people.json')
    #keywords_file = os.path.join(mappings_dir, 'keywords.json')

    #photographer_page = 'Institution:Riksantikvarieämbetet/KMB/creators'

    if update_mappings:
        query_props = {'P373': 'commonscat'}
        mappings['parish'] = query_to_lookup(
            build_query('P777', optional_props=query_props.keys()),
            props=query_props)
        mappings['municipality'] = query_to_lookup(
            build_query('P525', optional_props=query_props.keys()),
            props=query_props)
        mappings['county'] = query_to_lookup(
            build_query('P507', optional_props=query_props.keys()),
            props=query_props)
        #county
        #land
        #mappings['photographers'] = self.get_photographer_mapping(
        #    photographer_page)

        # dump to mappings
        common.open_and_write_file(
            parish_file, mappings['parish'], as_json=True)
        common.open_and_write_file(
            muni_file, mappings['municipality'], as_json=True)
        common.open_and_write_file(
            county_file, mappings['county'], as_json=True)
        #common.open_and_write_file(
        #    photographer_file, self.mappings['photographers'],
        #    as_json=True)
    else:
        mappings['parish'] = common.open_and_read_file(
            parish_file, as_json=True)
        mappings['municipality'] = common.open_and_read_file(
            muni_file, as_json=True)
        mappings['county'] = common.open_and_read_file(
            county_file, as_json=True)
        #mappings['photographers'] = common.open_and_read_file(
        #    photographer_file, as_json=True)

    # static files
    mappings['province'] = common.open_and_read_file(
        province_file, as_json=True)
    mappings['country'] = common.open_and_read_file(
        country_file, as_json=True)

    pywikibot.output('Loaded all mappings')
    return mappings


def build_query(main_prop, optional_props=None):
    """
    Construct a sparql query returning items containing a given property.

    The main_prop is given the label 'value' whereas any optional_props
    use the property pid as the label.

    :param main_prop: property pid (with P-prefix) to require
    :param optional_props: list of other properties pids to include as
        optional
    """
    optional_props = optional_props or []
    query = 'SELECT ?item ?value '
    if optional_props:
        query += '?{0} '.format(' ?'.join(optional_props))
    query += 'WHERE { '
    query += '?item wdt:{0} ?value . '.format(main_prop)
    for prop in optional_props:
        query += 'OPTIONAL { ?item wdt:%s ?%s } ' % (prop, prop)
    query += '}'
    return query


def query_to_lookup(query, item_label='item', value_label='value',
                    props=None):
    """
    Fetch sparql result and return it as a lookup table for wikidata id.

    If props are not provided the returned dict simply consists of
    value_label:item_label pairs. If props are provided the returned dict
    becomes value_label:{'wd':item_label, other props}

    :param item_label: the label of the selected wikidata id
    :param value_label: the label of the selected lookup key
    :param props: dict of other properties to save from the results using
        the format label_in_sparql:key_in_output.
    :return: dict
    """
    wdqs = sparql.SparqlQuery()
    result = wdqs.select(query, full_data=True)
    lookup = {}
    for entry in result:
        if entry[value_label] in lookup:
            raise pywikibot.Error('Non-unique value in lookup')
        key = str(entry[value_label])
        qid = entry[item_label].getID()
        if not props:
            lookup[key] = qid
        else:
            lookup[key] = {'wd': qid}
            for prop, label in props.items():
                if entry[prop] and not entry[prop].type:
                    entry[prop] = repr(entry[prop])
                lookup[key][label] = entry[prop]
    return lookup

#make this load settings appropriately
def main():
    """Initialise and run the mapping updater."""
    options = {
        'harvest_file': 'nm_data.json',
        'mapping_log_file': 'nm_mappings.log',
        'mappings_dir': 'mappings'
    }
    updater = DiMuMappingUpdater(options)
    pywikibot.output(updater.log.close_and_confirm())


if __name__ == '__main__':
    main()