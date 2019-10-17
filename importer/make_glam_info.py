#!/usr/bin/python
# -*- coding: utf-8  -*-
"""
Construct image info templates and categories for imgs from DigitaltMuseum.

These templates may be Artwork/Photograph/Information depending on the image
type.

Transforms the partially processed data generated by DiMuHarvester into a
BatchUploadTools-compliant json file.
"""
import os.path
from collections import OrderedDict
from datetime import datetime
import re

import pywikibot

import batchupload.common as common
import batchupload.helpers as helpers
import batchupload.listscraper as listscraper
from batchupload.make_info import MakeBaseInfo

import DiMuMappingUpdater as mapping_updater

MAPPINGS_DIR = 'mappings'
SETTINGS_DIR = 'settings'
LOGFILE = 'makeinfo_processing.log'
GEO_ORDER = ('other', 'parish', 'municipality', 'county', 'province',
             'country')


class GLAMInfo(MakeBaseInfo):
    """Construct descriptions + filenames for a GLAM batch upload."""

    def handle_args(args):
        """
        Parse and load all of the basic arguments.

        Redefined from parent so that categories don't
        have to be passed manually.

        Also passes any needed arguments on to pywikibot and sets any defaults.
        @param args: arguments to be handled
        @type args: list of strings
        @return: list of options
        @rtype: dict
        """
        options = {
            'in_file': None,
            'base_name': None,
            'update_mappings': True,
            'batch_settings': None
        }

        for arg in pywikibot.handle_args(args):
            option, sep, value = arg.partition(':')
            if option == '-in_file':
                options['in_file'] = common.convert_from_commandline(value)
            elif option == '-base_name':
                options['base_name'] = common.convert_from_commandline(value)
            elif option == '-update_mappings':
                options['update_mappings'] = common.interpret_bool(value)
            elif option == '-batch_settings':
                options['batch_settings'] = common.convert_from_commandline(
                    value)

        return options

    def load_batch_settings(self, options):
        """Load batch-specific settings for categorization."""
        fpath = options.get("batch_settings")
        batch_settings = common.open_and_read_file(fpath, as_json=True)
        if ("batch_cat" not in batch_settings.keys() or
                "batch_date" not in batch_settings.keys()):
            err = "Batch settings file ({}) is missing base category or date."
            raise common.MyError(err.format(fpath))
        return batch_settings

    def load_glam_data(self, raw_data):
        """Load GLAM-specific settings for info templates."""
        glam_code = self.b_settings.get("glam_code")
        glam_file = os.path.join(SETTINGS_DIR, glam_code)
        self.glam_data = common.open_and_read_file(
            "{}.json".format(glam_file), as_json=True)

    def __init__(self, **options):
        """Initialise a make_info object."""
        self.b_settings = self.load_batch_settings(options)
        super(GLAMInfo, self).__init__(
            self.b_settings["batch_cat"],
            self.b_settings["batch_date"],
            **options)

        self.commons = pywikibot.Site('commons', 'commons')
        self.wikidata = pywikibot.Site('wikidata', 'wikidata')
        self.category_cache = {}  # cache for category_exists()
        self.wikidata_cache = {}  # cache for Wikidata results
        self.log = common.LogFile(
            '', self.b_settings.get("makeinfo_log_file" or LOGFILE))
        self.log.write_w_timestamp('Make info started...')
        self.pd_year = datetime.now().year - 70

    def load_data(self, in_file):
        """
        Load the provided data (output from DiMuHarvester).

        Return this as a dict with an entry per file which can be used for
        further processing.

        :param in_file: the path to the metadata file generated by harvester
        :return: dict
        """
        raw_data = common.open_and_read_file(in_file, as_json=True)
        self.load_glam_data(raw_data)
        return raw_data

    def load_mappings(self, update_mappings):
        """
        Update mapping files, load these and package appropriately.

        :param update_mappings: whether to first download the latest mappings
        """
        mapping_root = self.glam_data.get("wiki_mapping_root")
        self.mappings = mapping_updater.load_mappings(
            update_mappings,
            load_mapping_lists=mapping_root)

    def mapped_and_wikidata(self, entry, mapping):
        """Add the linked wikidata info to a mapping."""
        if entry in mapping:
            mapped_info = mapping.get(entry)
            if mapped_info.get('wikidata'):
                mapped_info.update(
                    self.get_wikidata_info(mapped_info.get('wikidata')))
            return mapped_info
        return {}

    def process_data(self, raw_data):
        """
        Take the loaded data and construct a GLAMItem for each.

        Populates self.data but filters out, and logs, any problematic entries.

        :param raw_data: output from load_data()
        """
        self.data = {key: GLAMItem(value, self)
                     for key, value in raw_data.items()}

        # remove all problematic entries
        problematic = list(
            filter(lambda x: self.data[x].problems, self.data.keys()))
        for key in problematic:
            item = self.data.pop(key)
            text = '{0} -- image was skipped because of: {1}'.format(
                item.dimu_id, '\n'.join(item.problems))
            pywikibot.output(text)
            self.log.write(text)

    def generate_filename(self, item):
        """
        Given an item (dict) generate an appropriate filename.

        The filename has the shape: descr - Collection - id
        and does not include filetype

        :param item: the metadata for the media file in question
        :return: str
        """
        idno = item.glam_id
        title_desc = item.get_title_description()
        glam = self.glam_data.get("name")
        fname = helpers.format_filename(
            title_desc, glam, idno)
        if item.see_also:
            # sliders are numbered from 0,
            # but we want filenames to be numbered from 1
            # note that get_other_versions must agree w/any changes here
            slider_plus_one = item.slider_order + 1
            fname += "_({})".format(slider_plus_one)
        return fname

    def make_info_template(self, item):
        """
        Given an item of any type return the filled out template.

        @param item: the metadata for the media file in question
        @return: str
        """
        if item.type in ["Photograph", "Fineart"]:
            if item.is_photo:
                return self.make_photograph_template(item)
            else:
                return self.make_artwork_info(item)
        elif item.type == "Thing":
            return self.make_thing_template(item)

    def get_object_location(self, item):
        """
        Append object location if appropriate.

        :param item: the metadata for the media file in question
        :return: str
        """
        if item.latitude and item.longitude:
            return '\n{{Object location dec|%s|%s}}' % (
                item.latitude, item.longitude)
        return ''

    def make_thing_template(self, item):
        """
        Create the Photograph template for a single Thing entry.

        :param item: the metadata for the media file in question
        :return: str
        """
        template_name = 'Photograph'
        template_data = OrderedDict()
        template_data['photographer'] = item.get_creator()
        template_data['title'] = item.get_title()
        template_data['description'] = item.get_description()
        template_data['other_fields_2'] = item.get_original_description()
        template_data['depicted place'] = item.get_depicted_place()
        template_data['object_history'] = item.get_object_history()
        template_data['inscriptions'] = item.get_inscriptions()
        template_data['institution'] = item.get_institution()
        template_data['exhibition_history'] = item.get_exhibitions()
        template_data['accession number'] = item.get_id_link()
        template_data['source'] = item.get_source()
        template_data['permission'] = item.get_license_text()
        template_data['other_versions'] = item.get_other_versions()

        txt = helpers.output_block_template(template_name, template_data, 0)
        txt += self.get_object_location(item)

        return txt

    def make_photograph_template(self, item):
        """
        Create the Photograph template for a single NM entry.

        :param item: the metadata for the media file in question
        :return: str
        """
        template_name = 'Photograph'
        template_data = OrderedDict()
        template_data['photographer'] = item.get_creator()
        template_data['title'] = item.get_title()
        template_data['description'] = item.get_description()
        template_data['other_fields_2'] = item.get_original_description()
        template_data['depicted people'] = item.get_depicted_object(
            typ='person')
        template_data['depicted place'] = item.get_depicted_place()
        template_data['date'] = item.get_creation_date()
        template_data['exhibition_history'] = item.get_exhibitions()
        template_data['institution'] = item.get_institution()
        template_data['accession number'] = item.get_id_link()
        template_data['source'] = item.get_source()
        template_data['permission'] = item.get_license_text()
        template_data['other_versions'] = item.get_other_versions()

        txt = helpers.output_block_template(template_name, template_data, 0)
        txt += self.get_object_location(item)

        return txt

    def make_artwork_info(self, item):
        """
        Create the Artwork template for a single NM entry.

        :param item: the metadata for the media file in question
        :return: str
        """
        template_name = 'Artwork'
        template_data = OrderedDict()
        template_data['artist'] = item.get_creator()
        template_data['title'] = item.get_title()
        template_data['date'] = item.get_creation_date()
        template_data['description'] = item.get_description(with_depicted=True)
        template_data['other_fields_2'] = item.get_original_description()
        template_data['medium'] = item.get_materials()
        template_data['dimensions'] = ''
        template_data['institution'] = item.get_institution()
        template_data['exhibition_history'] = item.get_exhibitions()
        template_data['location'] = ''
        template_data['references'] = ''
        template_data['object history'] = ''
        template_data['credit line'] = ''
        template_data['inscriptions'] = item.get_inscriptions()
        template_data['notes'] = ''
        template_data['accession number'] = item.get_id_link()
        template_data['source'] = item.get_source()
        template_data['permission'] = item.get_license_text()
        template_data['other_versions'] = item.get_other_versions()

        txt = helpers.output_block_template(template_name, template_data, 0)
        txt += self.get_object_location(item)

        return txt

    # @todo: can also try the CORS enabled fdms01.dimu.org server
    def get_original_filename(self, item):
        """
        Generate the url where the original files can be found.

        Uses media_id instead of filename as the latter is not guaranteed to
        exist or be mapped to the right image.
        """
        server = 'http://dms01.dimu.org'
        org_filename = '{server}/image/{id}?dimension=max&filename={id}.jpg'
        org_filename = org_filename.format(server=server, id=item.media_id)
        return org_filename

    def generate_content_cats(self, item):
        """
        Extract any mapped keyword categories or depicted categories.

        :param item: the GLAMItem to analyse
        :return: list of categories (without "Category:" prefix)
        """
        item.make_item_keyword_categories()

        # Add parish/municipality categorisation when needed
        if item.needs_place_cat:
            item.make_place_category()

        return list(item.content_cats)

    def generate_meta_cats(self, item, content_cats):
        """
        Produce maintenance categories related to a media file.

        :param item: the metadata for the media file in question
        :param content_cats: any content categories for the file
        :return: list of categories (without "Category:" prefix)
        """
        cats = set([self.make_maintenance_cat(cat) for cat in item.meta_cats])

        # base cats already added by cooperation template? #@todo
        cats.add(self.batch_cat)

        # problem cats
        if not content_cats:
            cats.add(self.make_maintenance_cat('needing categorisation'))
        # @todo any others?

        # creator cats are classified as meta
        creator_cats = item.get_creator_cat()
        if creator_cats:
            for creator_cat in creator_cats:
                cats.add(creator_cat)

        return list(cats)

    def get_wikidata_info(self, qid):
        """
        Wrap listscraper.get_wikidata_info with local variables.

        :param qid: Qid for the Wikidata item
        :return: bool
        """
        return listscraper.get_wikidata_info(
            qid, site=self.wikidata, cache=self.wikidata_cache)

    def category_exists(self, cat):
        """
        Wrap helpers.self.category_exists with local variables.

        :param cat: category name (with or without "Category" prefix)
        :return: bool
        """
        return helpers.category_exists(
            cat, site=self.commons, cache=self.category_cache)

    # @todo update
    @classmethod
    def main(cls, *args):
        """Command line entry-point."""
        usage = (
            'Usage:'
            '\tpython make_glam_info.py -in_file:PATH -dir:PATH\n'
            '\t-in_file:PATH path to metadata file created by harvester\n'
            '\t-dir:PATH specifies the path to the directory containing a '
            'user_config.py file (optional)\n'
            '\t-update_mappings:BOOL if mappings should first be updated '
            'against online sources (defaults to True)\n'
            '\t-base_name:PATH base name for output files\n'
            '\t-batch_settings:PATH file with batch-specific settings\n'
            '\tExample:\n'
            '\tpython make_glam_info.py '
            '-in_file:dimu_harvest_data.json '
            '-batch_settings:settings/50-tal.json '
            '-base_name:nm_output -update_mappings:True -dir:NM\n'
        )
        info = super(GLAMInfo, cls).main(usage=usage, *args)
        if info:
            info.log.write_w_timestamp('...Make info finished\n')
            pywikibot.output(info.log.close_and_confirm())


class GLAMItem(object):
    """Store metadata and methods for a single media file."""

    def __init__(self, initial_data, glam_info):
        """
        Create a GLAMItem item from a dict where each key is an attribute.

        :param initial_data: dict of data to set up item with
        :param glam_info: the GLAMInfo instance
        """
        # ensure all required variables are present
        required_entries = ('latitude', 'longitude', 'is_photo',
                            'photographer')
        for entry in required_entries:
            if entry not in initial_data:
                initial_data[entry] = None

        for key, value in initial_data.items():
            setattr(self, key, value)

        self.problems = []  # any reasons for not uploading the image
        self.content_cats = set()  # content relevant categories without prefix
        self.meta_cats = set()  # meta/maintenance proto categories
        self.glam_info = glam_info  # the GLAMInfo instance creating this GLAMItem
        self.glam_data = glam_info.glam_data  # GLAM-specific settings
        self.needs_place_cat = True  # if item needs categorisation by place
        self.log = glam_info.log
        self.commons = glam_info.commons
        self.glam_id = self.get_glam_id()  # set the id used by the glam
        self.geo_data = self.get_geo_data()
        self.exclude_bad_copyright()

    def exclude_bad_copyright(self):
        """Exclude images with non-free copyright."""
        bad_copyrights = ["by-nc-nd"]
        copyright = self.copyright or self.default_copyright
        if copyright.get("code") in bad_copyrights:
            self.problems.append(
                "Bad copyright: {}.".format(copyright["code"]))

    def get_glam_id(self):
        """Set the identifier used by the GLAM."""
        for (glam, idno) in self.glam_id:
            if glam == self.glam_data.get("glam_code"):
                return idno

        # without a glam_id we have to abort
        raise common.MyError('Could not find an id for this GLAM in the data')

    def get_title_description(self):
        """Construct an appropriate description for a filename."""
        if self.description is not None:
            return self.description.strip()
        elif hasattr(self, "title"):
            return self.title.strip()
        else:
            return ""

    def get_object_history(self):
        """Add object history to template."""
        history = self.history
        if history:
            history = history.replace("\r", "\n")
            return history

    # @todo: adapt for depicted person, other keywords
    def get_original_description(self):
        """Given an item get an appropriate original description."""
        original_desc = self.description or ""
        if self.other_information:
            original_desc += '\n<br />{label}: {words}'.format(
                label=helpers.bolden('Övrig information'),
                words=self.other_information)
        if hasattr(self, 'insamlingsnr'):
            original_desc += '\n<br />{label}: {words}'.format(
                label=helpers.bolden('Insamlingsnummer'),
                words=self.insamlingsnr)
        if self.subjects:
            original_desc += '\n<br />{label}: {words}'.format(
                label=helpers.bolden('Ämnesord'),
                words='; '.join(self.subjects))
        if self.tags:
            original_desc += '\n<br />{label}: {words}'.format(
                label=helpers.bolden('Användargenererade nyckelord'),
                words='; '.join(self.subjects))

        role_dict = {
            'depicted_place': 'Avbildad plats',
            'view_over': 'Vy över'
        }
        if self.depicted_place:
            places = self.geo_data.get('labels').values()
            role = self.geo_data.get('role')
            original_desc += '\n<br />{label}: {words}'.format(
                label=helpers.bolden(role_dict.get(role)),
                words='; '.join(places))
        tpl = self.glam_data.get("description_template")
        return "{{%s|1=%s}}" % (tpl, original_desc.strip())

    def get_id_link(self):
        """Create the id link template."""
        series, _, idno = self.glam_id.partition('.')
        tpl = self.glam_data.get("link_template")
        return '{{%s|%s|%s}}' % (tpl, series, idno)

    def get_byline(self):
        """Create a photographer/GLAM byline."""
        txt = ''
        persons = self.creator
        display_names = []
        for name in [p.get('name') for p in persons
                     if p["role"] == "creator"]:
            if name not in self.glam_data.get("bad_names"):
                display_names.append(name)
        if len(display_names) > 1:
            txt += '{} / '.format(', '.join(display_names))
        elif len(display_names) == 1:
            txt += '{} / '.format(display_names[0])
        txt += self.glam_data.get("name")
        return txt

    def get_source(self):
        """Produce a linked source statement."""
        template = "{{%s}}" % self.glam_data.get("cooperation_template")
        byline = self.get_byline()
        return '[{url} {link_text}]\n{template}'.format(
            url=self.get_dimu_url(), link_text=byline, template=template)

    def get_dimu_url(self):
        """Create the url for the item on DigitaltMuseum."""
        dimu_domain = 'digitaltmuseum.org'
        if self.glam_data.get("country"):
            if self.glam_data.get("country") == "NO":
                dimu_domain = 'digitaltmuseum.no'
            elif self.glam_data.get("country") == "SE":
                dimu_domain = 'digitaltmuseum.se'
        return 'https://{domain}/{id}/?slide={order}'.format(
            domain=dimu_domain, id=self.dimu_id, order=self.slider_order)

    def get_description(self, with_depicted=False):
        """
        Given an item get an appropriate description.

        :param with_depicted: whether to also include depicted data
        """
        language = self.glam_data.get("language")
        if self.description is None:
            if hasattr(self, "title"):
                self.description = self.title
            else:
                self.description = ""
        desc = '{{%s|%s}}' % (language, self.description)

        if with_depicted:
            desc += '\n{}'.format(self.get_depicted_place(wrap=True))

        desc = desc.replace("\r", "\n")
        return desc.strip()

    def get_depicted_object(self, typ):
        """Format depicted object statement."""
        return ""

    def get_depicted_place(self, wrap=False):
        """
        Format a depicted place statement.

        Always output all "other" values. Then output other places values until
        the first one mapped to Wikidata is encountered.

        :param wrap: whether to wrap the result in {{depicted place}}.
        """
        depicted_place = self.depicted_place or self.description_place

        if not self.geo_data:
            return ''
        role = self.geo_data.get('role')
        wikidata = self.geo_data.get('wd')
        labels = self.geo_data.get('labels')

        depicted = []
        # handle 'other' separately
        if depicted_place.get('other'):
            for geo_type in depicted_place.get('other').keys():
                value = labels.get(geo_type)
                if geo_type in wikidata:
                    value = '{{item|%s}}' % wikidata.get(geo_type)
                depicted.append('{val} ({key})'.format(
                    key=helpers.italicize(geo_type), val=value))

        for geo_type in GEO_ORDER:
            if not depicted_place.get(geo_type) or geo_type == 'other':
                continue
            if geo_type in wikidata:
                depicted.append('{{item|%s}}' % wikidata.get(geo_type))
                break
            else:
                value = labels.get(geo_type)
                depicted.append('{val} ({key})'.format(
                    key=helpers.italicize(geo_type), val=value))

        depicted_str = ', '.join(depicted)
        if not wrap:
            return depicted_str
        elif role == 'depicted_place':
            return '{{depicted place|%s}}' % depicted_str
        else:
            return '{{depicted place|%s|comment=%s}}' % (
                depicted_str, role.replace('_', ' '))

    def get_geo_data(self):
        """
        Find commonscat and wikidata entries for each available place level.

        Returns an dict with the most specific wikidata entry and any matching
        commonscats in decreasing order of relevance.

        If any 'other' value is matched the wikidata ids are returned and the
        categories are added as content_cats.
        """
        if (self.description_place and self.depicted_place and
                (self.description_place != self.depicted_place)):
            self.problems.append(
                'Cannot handle differing depicted_place and description_place:'
                '\nDepicted_place: {0}\nDescription_place: {1}'.format(
                    self.depicted_place, self.description_place))

        depicted_place = self.depicted_place or self.description_place
        if not depicted_place:
            return {}

        if (depicted_place.get('country') and
                depicted_place.get('country').get('code') != 'Sverige'):
            self.meta_cats.add('needing categorisation (not from Sweden)')

        # set up the geo_types and their corresponding mappings ordered from
        # most to least specific
        geo_map = OrderedDict(
            [(i, self.glam_info.mappings.get(i)) for i in GEO_ORDER])
        role = depicted_place.pop('role')

        if any(key not in geo_map for key in depicted_place.keys()):
            diff = set(depicted_place.keys()) - set(geo_map.keys())
            raise common.MyError(
                '{} should be added to GEO_ORDER'.format(', '.join(diff)))

        wikidata = {}
        commonscats = []
        labels = OrderedDict()
        # handle other separately
        geo_map.pop('other')
        if depicted_place.get('other'):
            for geo_type, data in depicted_place.get('other').items():
                mapping = self.glam_info.mapped_and_wikidata(
                    data.get('code'), self.glam_info.mappings['places'])
                if mapping.get('category'):
                    commonscats += mapping.get('category')  # this is a list
                if mapping.get('wikidata'):
                    wikidata[geo_type] = mapping.get('wikidata')
                labels[geo_type] = data.get('label')

        for geo_type, mapping in geo_map.items():
            if not depicted_place.get(geo_type):
                continue
            data = depicted_place.get(geo_type)
            mapped_data = mapping.get(data.get('code'))
            if mapped_data.get('wd'):
                wikidata[geo_type] = mapped_data.get('wd')
            if mapped_data.get('commonscat'):
                commonscats.append(mapped_data.get('commonscat'))
            labels[geo_type] = data.get('label')

        # just knowing country is pretty bad
        if len(commonscats) <= 1:
            self.meta_cats.add('needing categorisation (place)')

        return {
            'role': role,
            'wd': wikidata,
            'commonscats': commonscats,
            'labels': labels
        }

    def get_photographer(self):
        """Return photographer name for Thing object."""
        return self.photographer.get("name")

    def get_creator(self):
        """Return correctly formated creator values in wikitext."""
        mapping = self.glam_info.mappings.get('people')
        if self.type == "Thing":
            persons = self.creator
        elif self.type == "Photograph":
            persons = self.creator
        elif hasattr(self, "creation"):
            persons = self.creation.get('related_persons')
        display_names = []
        for name in [person.get('name') for person in persons]:
            display_name = name  # default
            mapped_info = self.glam_info.mapped_and_wikidata(name, mapping)
            if mapped_info.get('creator'):
                display_name = '{{Creator:%s}}' % mapped_info.get('creator')
            elif mapped_info.get('wikidata'):
                display_name = '{{Item|%s}}' % mapped_info.get('wikidata')
            display_names.append(display_name)
        return ', '.join(display_names)

    def get_creator_cat(self):
        """Return the commonscat(s) for the creator(s)."""
        mapping = self.glam_info.mappings.get('people')
        cats = []
        for person in self.creator:
            name = person.get('name')
            mapped_info = self.glam_info.mapped_and_wikidata(name, mapping)
            if mapped_info.get('commonscat'):
                cat = mapped_info.get('commonscat')
                if self.glam_info.category_exists(cat):
                    cats.append(cat)
        return cats

    def make_place_category(self):
        """Add the most specific geo category."""
        if self.geo_data.get('commonscats'):
            for geo_cat in self.geo_data.get('commonscats'):
                if self.glam_info.category_exists(geo_cat):
                    self.content_cats.add(geo_cat)
                    return True

        # no geo cats found and it's not a Thing
        if self.type != "Thing":
            self.meta_cats.add('needing categorisation (place)')
            return False

    def make_item_keyword_categories(self):
        """Construct categories from the item keyword values."""
        all_keywords = set()
        all_keywords.update(self.subjects)
        if self.tags:
            all_keywords.update(self.tags)
        keyword_map = self.glam_info.mappings['keywords']

        for keyword in all_keywords:
            if keyword not in keyword_map:
                continue
            for cat in keyword_map[keyword]:
                match_on_first = True
                found_testcat = False
                if self.geo_data.get('commonscats'):
                    for place_cat in self.geo_data.get('commonscats'):
                        found_testcat = self.try_cat_patterns(
                            cat, place_cat, match_on_first)
                        if found_testcat:
                            break
                        match_on_first = False
                if not found_testcat and self.glam_info.category_exists(cat):
                    self.content_cats.add(cat)

    def try_cat_patterns(self, base_cat, place_cat, match_on_first):
        """Test various combinations to construct a geographic subcategory."""
        test_cat_patterns = ('{cat} in {place}', '{cat} of {place}')
        for pattern in test_cat_patterns:
            test_cat = pattern.format(cat=base_cat, place=place_cat)
            if self.glam_info.category_exists(test_cat):
                self.content_cats.add(test_cat)
                if match_on_first:
                    self.needs_place_cat = False
                return True
        return False

    def get_materials(self):
        """Format a materials/technique statement."""
        # need to be run through the mappings and formatted accordingly
        if self.techniques or self.materials:
            raise NotImplementedError
        return ''

    def get_exhibitions(self):
        """Add exhibition history."""
        if self.exhibitions:
            printable_exhibitions = []
            for exh in self.exhibitions:
                if len(exh["titles"]) == 1:
                    title = exh["titles"][0]["title"]
                else:
                    # Haven't seen exhibitions w/multiple titles yet,
                    # so let's figure it out when it's relevant…
                    raise NotImplementedError
                if (exh["from_year"] == exh["to_year"] or
                        exh["to_year"] is None):
                    years = exh["from_year"]
                else:
                    years = "{}–{}".format(exh["from_year"],
                                           exh["to_year"])
                dimu_domain = "digitaltmuseum.org"
                if self.glam_data.get("country"):
                    if self.glam_data.get("country") == "NO":
                        dimu_domain = "digitaltmuseum.no"
                    elif self.glam_data.get("country") == "SE":
                        dimu_domain = "digitaltmuseum.se"
                exh_url = "https://{}/{}".format(
                    dimu_domain, exh["dimu_code"])
                link = '[{} {}]'.format(exh_url, title)
                link = "{}: ".format(years) + link
                printable_exhibitions.append(link)
            if len(printable_exhibitions) > 1:
                sorted_exhibitions = sorted(
                    ["* {}\n".format(x) for x in printable_exhibitions])
                text = "".join(sorted_exhibitions)
            else:
                text = printable_exhibitions[0]
            return text

    def get_inscriptions(self):
        """Format an inscription statement."""
        text = ""
        if self.inscriptions:
            for insc in self.inscriptions:
                printable = insc["text"].strip()
                printable = printable.replace("\n", " ")
                printable = printable.replace("\r", "")
                printable = re.sub(' +', ' ', printable)
                if insc.get("description"):
                    to_add = " ({}. {})".format(
                        insc["type"].strip(), insc["description"].strip())
                    printable += to_add
                else:
                    printable += " ({})".format(insc["type"].strip())
                text += "* {}\n".format(printable)
        return text

    def get_license_text(self):
        """Format a license template."""
        if self.copyright and self.default_copyright:
            # cannot deal with double license info yet
            raise NotImplementedError

        copyright = self.copyright or self.default_copyright

        # CC licenses are used for modern photographs
        if copyright.get('code') == 'by':
            return '{{CC-BY-4.0|%s}}' % self.get_byline()
        elif copyright.get('code') == 'by-sa':
            return '{{CC-BY-SA-4.0|%s}}' % self.get_byline()
        elif copyright.get('code') == 'pdm':
            # for PD try to get death date from creator (wikidata) else PD-70
            mapping = self.glam_info.mappings.get('people')
            persons = (self.creation.get('related_persons') or
                       copyright.get('persons') or
                       self.photographer.get("name"))
            death_years = []
            for person in persons:
                name = person.get('name')
                data = self.glam_info.mapped_and_wikidata(name, mapping)
                death_years.append(data.get('death_year'))
            death_years = list(filter(None, death_years))  # trim empties
            try:
                death_year = max(death_years)
            except ValueError:
                death_year = None
            if death_year and death_year < self.glam_info.pd_year:
                return '{{PD-old-auto|deathyear=%s}}' % death_year
            elif death_year and not self.is_photo:
                raise common.MyError(
                    'The creator death year is not late enough for PD and '
                    'this does not seem to be a photo')
            elif self.is_photo:
                return '{{PD-Sweden-photo}}'
            else:
                return '{{PD-old-70}}'

    def get_creation_date(self):
        """Format a creation date statement."""
        if self.creation and self.creation['date']:
            date_val = self.creation['date']
            if isinstance(date_val, tuple):
                return '{{other date|-|%s|%s}}' % date_val
            elif date_val not in self.glam_data.get("bad_dates"):
                return date_val
        return ''

    def get_other_versions(self):
        """
        Create a gallery for other images of the same object.

        Sliders are numbered from 0, but we want filenames
        to start from 1.
        Note that generate_filename must agree w/any changes here
        """
        txt = ""
        slider_plus_one = self.slider_order + 1
        if self.see_also:
            txt = "<gallery>\n"
            total_imgs = len(self.see_also) + 1
            for _ in range(1, total_imgs + 1):
                if _ != slider_plus_one:
                    idno = self.glam_id
                    title_desc = self.get_title_description()
                    glam = self.glam_data.get("name")
                    fname = helpers.format_filename(
                        title_desc, glam, idno)
                    fname += "_({})".format(_)
                    txt += "File:{}.jpg\n".format(fname)
            txt += "</gallery>"
        return txt

    def get_institution(self):
        """Get appropriate Institution template."""
        inst = self.glam_data.get("institution_template")
        return'{{Institution:%s}}' % inst

    def get_title(self):
        """Return the title element for the image."""
        if self.title:
            return self.title


if __name__ == "__main__":
    GLAMInfo.main()
