#!/usr/bin/python
# -*- coding: utf-8  -*-
"""
Construct image information templates and categories for Nordic Museum data.

These templates may be Artwork/Photograph/Information depending on the image
type.

Transforms the partially processed data from nm_massload into a
BatchUploadTools compliant json file.
"""
import os.path
from collections import OrderedDict

import pywikibot

import batchupload.common as common
import batchupload.helpers as helpers
from batchupload.make_info import MakeBaseInfo
import importer.DiMuMappingUpdater as mapping_updater


DIR_PATH = os.path.dirname(os.path.realpath(__file__))
MAPPINGS_DIR = 'mappings'
BATCH_CAT = 'Images from Nordiska museet'  # stem for maintenance categories (We use "Images from Nordiska museet" for both content and maintenance today, consider splitting these)
BATCH_DATE = '2017-10'  # branch for this particular batch upload
LOGFILE = 'nm_processing_october.log'


class NMInfo(MakeBaseInfo):
    """Construct descriptions + filenames for a Nordic Museum batch upload."""

    def __init__(self, **options):
        """Initialise a make_info object."""
        batch_date = pop(options, 'batch_label') or BATCH_DATE
        batch_cat = pop(options, 'base_meta_cat') or BATCH_CAT
        super(NMInfo, self).__init__(batch_cat, batch_date, **options)

        # black-listed values
        self.bad_names = ('Nordiska museets arkiv', )
        self.bad_dates = ('odaterad', )

        self.commons = pywikibot.Site('commons', 'commons')
        self.wikidata = pywikibot.Site('wikidata', 'wikidata')
        self.category_cache = {}  # cache for category_exists()
        self.wikidata_cache = {}  # cache for Wikidata results
        #self.k_nav_list = {}
        #self.photographer_cache = {}
        self.log = common.LogFile('', LOGFILE)

    def load_data(self, in_file):
        """
        Load the provided data (output from nm_massload).

        Return this as a dict with an entry per file which can be used for
        further processing.

        :param in_file: the path to the metadata file
        :return: dict
        """
        return common.open_and_read_file(in_file, as_json=True)

    def load_mappings(self, update_mappings):
        """
        Update mapping files, load these and package appropriately.

        :param update_mappings: whether to first download the latest mappings
        """
        self.mappings = mapping_updater.load_mappings(
            update_mappings, load_mapping_lists=True)

    def mapped_and_wikidata(self, entry, mapping):
        """Add the linked wikidata info to a mapping."""
        if entry in mapping:
            mapped_info = mapping.get(entry)
            if mapped_info.get('wikidata'):
                mapped_info.update(
                    self.nm_info.get_wikidata_info(
                        mapped_info.get('wikidata')))
            return mapped_info
        return {}

    def process_data(self, raw_data):
        """
        Take the loaded data and construct a NMItem for each.

        Populates self.data.

        :param raw_data: output from load_data()
        """
        self.data = {key: NMItem(value, self)
                     for key, value in raw_data.items()}

    def generate_filename(self, item):
        """
        Given an item (dict) generate an appropriate filename.

        The filename has the shape: descr - Collection - id
        and does not include filetype

        :param item: the metadata for the media file in question
        :return: str
        """
        return helpers.format_filename(
            item.get_title_description(), 'Nordiska museet', item.glam_id)

    def make_info_template(self, item):
        """
        Given an item of any type return the filled out template.

        @param item: the metadata for the media file in question
        @return: str
        """
        if item.type == "Photograph":
            if item.is_photo:
                self.make_photograph_template(item)
            else:
                self.make_artwork_info(item)
        else:
            # haven't figured out Thing yet
            raise NotImplementedError

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
        template_data['original description'] = item.get_original_description()
        template_data['depicted people'] = item.get_depicted_object(
            typ='person')
        template_data['depicted place'] = item.get_depicted_place()
        template_data['date'] = item.get_creation_date()
        template_data['medium'] = item.get_materials()
        template_data['institution'] = '{{Institution:Nordiska museet}}'
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
        template_data['institution'] = '{{Institution:Nordiska museet}}'
        template_data['location'] = ''
        template_data['references'] = ''
        template_data['object history'] = ''
        template_data['credit line'] = ''
        template_data['inscriptions'] = ''
        template_data['notes'] = ''
        template_data['accession number'] = item.get_id_link()
        template_data['source'] = item.get_source()
        template_data['permission'] = item.get_license_text()
        template_data['other_versions'] = item.get_other_versions()

        txt = helpers.output_block_template(template_name, template_data, 0)
        txt += self.get_object_location(item)

        return txt

    # @todo: ensure that these work with uploade_by_url
    # can also try the CORS enabled fdms01.dimu.org server
    def get_original_filename(self, item):
        """
        Generate the url where the original files can be found.

        Uses media_id instead of filename as the latter is not guaranteed to
        exist or be mapped to the right image.
        """
        server = 'http://dms01.dimu.org'
        return '{server}/image/{id}?dimension=max&filename={id}.jpg'.format(
            server=server, id=item.media_id)

    # @todo: check need
    def get_creator(self, creator):
        """
        given a creator (or creators) return the creator template,
        linked entry or plain name
        """
        raise NotImplementedError

    def generate_content_cats(self, item):
        """
        Extract any mapped keyword categories or depicted categories.

        @param item: the item to analyse
        """
        raise NotImplementedError

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
        for creator_cat in creator_cats:
            cats.add(creator_cat)

        return list(cats)

    def category_exists(self, cat):
        """
        Ensure a given category really exists on Commons.

        The replies are cached to reduce the number of lookups.

        :param cat: category name (with or without "Category" prefix)
        :return: bool
        """
        cache = self.category_cache
        if not cat.lower().startswith('category:'):
            cat = 'Category:{0}'.format(cat)

        if cat in cache:
            return cache[cat]

        exists = pywikibot.Page(self.commons, cat).exists()
        cache[cat] = exists

        return exists

    def get_wikidata_info(self, qid):
        """
        Query Wikidata for additional info about an item.

        The replies are cached to reduce the number of lookups.

        :param qid: Qid for the Wikidata item
        :return: bool
        """
        cache = self.wikidata_cache
        if qid in cache:
            return cache[qid]

        item = pywikibot.ItemPage(self.wikidata, qid)
        if not item.exists():
            cache[qid] = {}
        else:
            commonscat = return_first_claim(item, 'P373')
            creator = return_first_claim(item, 'P1472')
            death_year = return_first_claim(item, 'P570')
            if death_year:
                death_year = death_year.year
            cache[qid] = {
                'commonscat': commonscat,
                'creator': creator,
                'death_year': death_year
            }

        return cache[qid]

    # @todo update
    @classmethod
    def main(cls, *args):
        """Command line entry-point."""
        usage = (
            'Usage:'
            '\tpython make_info.py -in_file:PATH -dir:PATH\n'
            '\t-in_file:PATH path to metadata file\n'
            '\t-dir:PATH specifies the path to the directory containing a '
            'user_config.py file (optional)\n'
            '\t-update_mappings:BOOL if mappings should first be updated '
            'against online sources (defaults to True)\n'
            '\tExample:\n'
            '\tpython make_NordicMuseum_info.py -in_file:nm_data.json '
            '-base_name:nm_output -update_mappings:True -dir:NM\n'
        )
        info = super(NMInfo, cls).main(usage=usage, *args)
        if info:
            pywikibot.output(info.log.close_and_confirm())


class NMItem(object):
    """Store metadata and methods for a single media file."""

    def __init__(self, initial_data, nm_info):
        """
        Create a NMItem item from a dict where each key is an attribute.

        :param initial_data: dict of data to set up item with
        :param nm_info: the NMInfo instance
        """
        # ensure all required variables are present
        required_entries = ('latitude', 'longitude', 'is_photo',
                            'photographer')
        for entry in required_entries:
            if entry not in initial_data:
                initial_data[entry] = None

        for key, value in initial_data.items():
            setattr(self, key, value)

        self.wd = {}  # store for relevant Wikidata identifiers
        self.content_cats = set()  # content relevant categories without prefix
        self.meta_cats = set()  # meta/maintenance proto categories
        self.nm_info = nm_info  # the NMInfo instance creating this NMItem
        self.log = nm_info.log
        self.commons = nm_info.commons
        self.glam_id = self.get_glam_id()  # set the id used by the glam

    # @todo: consider loading glam identifier from settings
    def get_glam_id(self):
        """Set the identifier used by the Nordic museum."""
        for (glam, idno) in self.glam_id:
            if glam == 'S-NM':
                return idno

        # without a glam_id we have to abort
        raise common.MyError('Could not find an id for this GLAM in the data!')

    def get_title_description(self):
        """Construct an appropriate description for a filename."""
        if self.description:
            return self.description.strip()
        else:
            raise NotImplementedError

    # @todo: adapt for depicted person, other keywords
    def get_original_description(self):
        """
        Given an item get an appropriate original description
        """
        original_desc = self.description
        if self.subjects:
            original_desc += '<br />{label}: {words}'.format(
                label=helpers.bolden('Ämnesord'),
                words='; '.join(self.subjects))

        return '{{Nordiska museet description|1=%s}}' % original_desc

    def get_id_link(self):
        """Create the id link template."""
        series, _, idno = self.glam_id.partition('.')
        return '{{Nordiska museet link|{series}|{id}}}'.format(
            series=series, id=idno)

    def get_source(self):
        """Produce a linked source statement."""
        template = '{{Nordiska museet cooperation project}}'
        txt = ''
        if (self.photographer and
                self.photographer not in self.nm_info.bad_names):
            txt += '{} / '.format(self.photographer)
        txt += 'Nordiska museet'
        return '[{url} {link_text}]\n{template}'.format(
            url=self.get_dimu_url(), link_text=txt, template=template)

    def get_dimu_url(self):
        """Create the url for the item on DigitaltMuseum."""
        return 'https://digitaltmuseum.se/{id}/?slide={order}'.format(
            id=self.dimu_id, order=self.slider_order)

    def get_description(self, with_depicted=True):
        """
        Given an item get an appropriate description

        :param with_depicted: whether to also include depicted data
        """
        desc = '{{sv|%s}}' % self.description

        return desc
        #Use get_depicted_place
        #handle view over
        #get_depicted_object(item, typ='person')
        #{{depicted place|%s}}' % (item.get_depicted_place(self.mappings),
        #{{depicted person|%s|style=information field}} ' % '|'.join(formatted_depicted) #<- run this through mapping to pick up links/wikidata

    def get_depicted_place(self):
        """Format at depicted place statement."""
        if self.depicted_place:
            raise NotImplementedError
        return ''

    def get_creator(self):
        """Return correctly formated creator values in wikitext."""
        mapping = self.nm_info.mappings.get('people')
        persons = self.creation.get('related_persons')
        display_names = []
        for name in [person.get('name') for person in persons]:
            display_name = name  # default
            mapped_info = self.nm_info.mapped_and_wikidata(name, mapping)
            if mapped_info.get('creator'):
                display_name = '{{Creator:%s}}' % mapped_info.get('creator')
            elif mapped_info.get('wikidata'):
                display_name = '{{Item|%s}}' % mapped_info.get('wikidata')
            display_names.append(display_name)
        return ', '.join(display_names)

    def get_creator_cat(self):
        """Return the commonscat(s) for the creator(s)."""
        mapping = self.nm_info.mappings.get('people')
        persons = self.creation.get('related_persons')
        cats = []
        for name in [person.get('name') for person in persons]:
            mapped_info = self.nm_info.mapped_and_wikidata(name, mapping)
            if mapped_info.get('commonscat'):
                cats.append(mapped_info.get('commonscat'))
        return cats

    def get_materials(self):
        """Format at materials/technique statement."""
        # need to be run through the mappings and formatted accordingly
        if self.technique or self.material:
            raise NotImplementedError
        return ''

    def get_license_text(self):
        """Format a license template."""
        # look at self.copyright and self.default_copyright
        # map licenses to templates
        # for PD try to get death date from creator (wikidata) else PD-70
        # or are some cc0?
        # use
        raise NotImplementedError

    def get_creation_date(self):
        """Format a creation date statement."""
        if self.creation and self.creation['date']:
            date_val = self.creation['date']
            if isinstance(date_val, tuple):
                return '{{other date|-|%s|%s}}' % date_val
            elif date_val not in self.nm_info.bad_dates:
                return date_val
        return ''

    def get_other_versions(self):
        """Create a gallery for other images of the same object."""
        if self.see_also:
            raise NotImplementedError
        return ''

    # @todo consider using other value here...
    def get_title(self):
        """Return the title element for the image."""
        if self.title:
            raise NotImplementedError
        return ''


def return_first_claim(item, prop):
    """Return the first claim of a wikiata item for a given property."""
    claims = item.claims.get(prop)
    if claims:
        claims[0].target


# @todo move to batchuploads
def pop(d, val):
    """A poper which returns None if the value isn't present."""
    try:
        return d.pop(val)
    except KeyError:
        return None


if __name__ == "__main__":
    NMInfo.main()
