#!/usr/bin/python
# -*- coding: utf-8  -*-
"""Create or update mapping lists."""
import os
from collections import Counter, OrderedDict


import pywikibot
from pywikibot.data import sparql

import batchupload.common as common
from batchupload.listscraper import MappingList

SETTINGS = "settings.json"
MAPPINGS_DIR = 'mappings'
HARVEST_FILE = 'dimu_harvest_data.json'


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

        self.kulturnav_hits = load_kulturnav_data()
        self.people_to_map = {}
        self.places_to_map = OrderedDict()
        self.subjects_to_map = Counter()

        self.parse_harvest_data(harvest_data)
        self.check_and_remove_code_place_entries()
        self.dump_to_wikifiles()

    def dump_to_wikifiles(self):
        """Dump the mappings to wikitext files."""
        self.dump_places()
        self.dump_subjects()
        self.dump_people()

    def get_intro_text(self, key):
        return (self.settings.get('intro_texts').get(key) or
                self.settings.get('default_intro_text').format(key.title()))

    def dump_places(self):
        ml = make_places_list(
            mapping_root=self.settings.get('wiki_mapping_root'))
        intro_text = self.get_intro_text('places')
        merged_places_data = {}
        preserved_places_data = None
        update = True
        for k, v in self.places_to_map.items():
            merged_places, preserved_places = ml.merge_old_and_new_mappings(
                v.most_common(), update=update)
            update = False  # only update first time
            merged_places_data[k] = merged_places

            # combine entries to only keep those which are still unused
            preserved_places = set(preserved_places)
            if not preserved_places_data:
                # first time aroung
                preserved_places_data = preserved_places
            preserved_places_data &= preserved_places

        ml.save_as_wikitext(
            merged_places_data, preserved_places_data, intro_text)

    def dump_subjects(self):
        mk = make_keywords_list(
            mapping_root=self.settings.get('wiki_mapping_root'))
        intro_text = self.get_intro_text('keyword')
        merged_keywords, preserved_keywords = mk.merge_old_and_new_mappings(
            self.subjects_to_map.most_common(), update=True)
        mk.save_as_wikitext(merged_keywords, preserved_keywords, intro_text)

    def dump_people(self):
        mp = make_people_list(
            mapping_root=self.settings.get('wiki_mapping_root'))
        intro_text = self.get_intro_text('people')
        merged_people, preserved_people = mp.merge_old_and_new_mappings(
            self.format_person_data(), update=True)
        mp.save_as_wikitext(merged_people, preserved_people, intro_text)

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
                knav_id = data.get('k_nav')
                if knav_id in self.kulturnav_hits:
                    knav_data = self.kulturnav_hits.get(knav_id)
                    entry['wikidata'] = knav_data.get('wd')
                    if knav_data.get('creator'):
                        entry['creator'] = knav_data.get('creator')
                    if knav_data.get('commonscat'):
                        entry['category'] = knav_data.get('commonscat')
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

    # @todo: is connection between place levels broken by this?
    #        Risk of mismatches?
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
            if typ not in self.places_to_map:
                continue
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
    """Load the harvested data from a file."""
    filename = filename or HARVEST_FILE
    harvest_data = common.open_and_read_file(filename, as_json=True)
    return harvest_data


def load_mappings(update_mappings, mappings_dir=None,
                  load_mapping_lists=False):
    """
    Update mapping files, load these and package appropriately.

    :param update_mappings: whether to first download the latest mappings
    :param mappings_dir: path to directory in which mappings are found
    :param load_mapping_lists: if mapping_lists should also be loaded
    """
    mappings = {}
    mappings_dir = mappings_dir or MAPPINGS_DIR
    common.create_dir(mappings_dir)  # ensure it exists

    parish_file = os.path.join(mappings_dir, 'socken.json')
    muni_file = os.path.join(mappings_dir, 'kommun.json')
    county_file = os.path.join(mappings_dir, 'lan.json')
    province_file = os.path.join(mappings_dir, 'province.json')
    country_file = os.path.join(mappings_dir, 'country.json')

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

        # dump to mappings
        common.open_and_write_file(
            parish_file, mappings['parish'], as_json=True)
        common.open_and_write_file(
            muni_file, mappings['municipality'], as_json=True)
        common.open_and_write_file(
            county_file, mappings['county'], as_json=True)

    else:
        mappings['parish'] = common.open_and_read_file(
            parish_file, as_json=True)
        mappings['municipality'] = common.open_and_read_file(
            muni_file, as_json=True)
        mappings['county'] = common.open_and_read_file(
            county_file, as_json=True)

    # static files
    mappings['province'] = common.open_and_read_file(
        province_file, as_json=True)
    mappings['country'] = common.open_and_read_file(
        country_file, as_json=True)

    if load_mapping_lists:
        load_mapping_lists_mappings(mappings_dir, update_mappings, mappings)

    pywikibot.output('Loaded all mappings')
    return mappings


def load_mapping_lists_mappings(mappings_dir, update=True, mappings=None):
    """
    Add mapping lists to the loaded mappings.

    :param update: whether to first download the latest mappings
    :param mappings_dir: path to directory in which mappings are found
    :param mappings: dict to which mappings should be added. If None then a new
        dict is returned.
    """
    mappings = mappings or {}
    mappings_dir = mappings_dir or MAPPINGS_DIR

    ml = make_places_list(mappings_dir)
    mappings['places'] = ml.consume_entries(
        ml.load_old_mappings(update=update), 'name',
        require=['category', 'wikidata'])

    mk = make_keywords_list(mappings_dir)
    mappings['keywords'] = mk.consume_entries(
        mk.load_old_mappings(update=update), 'name', require='category',
        only='category')

    mp = make_people_list(mappings_dir)
    mappings['people'] = mp.consume_entries(
        mp.load_old_mappings(update=update), 'name',
        require=['creator', 'category', 'wikidata'])
    return mappings


def make_places_list(mapping_dir=None, mapping_root=None):
    """Create a MappingList object for places."""
    mapping_dir = mapping_dir or MAPPINGS_DIR
    mapping_root = mapping_root or 'dummy'
    parameters = ['name', 'category', 'wikidata', 'frequency']
    header = '{{User:André Costa (WMSE)/mapping-head|category=|wikidata=}}'
    return MappingList(
        page='{}/places'.format(mapping_root),
        parameters=parameters,
        header_template=header,
        mapping_dir=mapping_dir)


def make_keywords_list(mapping_dir=None, mapping_root='dummy'):
    """Create a MappingList object for keywords."""
    mapping_dir = mapping_dir or MAPPINGS_DIR
    mapping_root = mapping_root or 'dummy'
    parameters = ['name', 'category', 'frequency']
    header = '{{User:André Costa (WMSE)/mapping-head|category=}}'
    return MappingList(
        page='{}/keywords'.format(mapping_root),
        parameters=parameters,
        header_template=header,
        mapping_dir=mapping_dir)


def make_people_list(mapping_dir=None, mapping_root='dummy'):
    """Create a MappingList object for people."""
    mapping_dir = mapping_dir or MAPPINGS_DIR
    mapping_root = mapping_root or 'dummy'
    parameters = ['name', 'more', 'creator', 'category', 'wikidata', 'other',
                  'frequency']
    header = ('{{User:André Costa (WMSE)/mapping-head'
              '|category=|creator=|wikidata=|other=leftover comments}}')
    return MappingList(
        page='{}/people'.format(mapping_root),
        parameters=parameters,
        header_template=header,
        mapping_dir=mapping_dir)


def load_kulturnav_data():
    """
    Load all known KulturNav entries (P1248) on Wikidata.

    In addition to qid also load data on commonscat (P373) and
    Creator templates (P1472).
    """
    query = build_query('P1248', ['P373', 'P1472'])
    return query_to_lookup(
        query, props={'P373': 'commonscat', 'P1472': 'creator'})


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


# @todo: make this load settings appropriately (cf. harvester)
def main():
    """Initialise and run the mapping updater."""
    options = {
        'harvest_file': 'nm_data.json',
        'mapping_log_file': 'nm_mappings.log',
        'mappings_dir': 'mappings',
        'wiki_mapping_root': 'Commons:Nordiska_museet/mapping',
        'default_intro_text': (
            '{} mapping table for [[Commons:Nordiska museet]]\n'),
        'intro_texts': {
            'keyword': (
                'Keyword mapping table for [[Commons:Nordiska museet]]. '
                'Originally populated from '
                '[[Commons:Batch uploading/Nordiska Museet/keywords]].\n'),
            'people': (
                'People mapping table for [[Commons:Nordiska museet]]. '
                'Originally populated from '
                '[[Commons:Batch uploading/Nordiska Museet/creators]].\n')
        }
    }
    updater = DiMuMappingUpdater(options)
    pywikibot.output(updater.log.close_and_confirm())


if __name__ == '__main__':
    main()
