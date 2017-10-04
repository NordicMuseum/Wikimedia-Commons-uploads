#!/usr/bin/python
# -*- coding: utf-8  -*-
"""
Information template production

first mapping file generation could be separated (and if so also knav stuff)

A known assumption is that in avbildad_namn any string containing exactly
one comma is a person, and any others are assumed to be ships.
"""
import batchupload.helpers as helpers
import batchupload.common as common  # temp before this is merged with helper
import batchupload.listscraper as listscraper
import batchupload.csv_methods as csv_methods
from batchupload.make_info import MakeBaseInfo
import os
import pywikibot

OUT_PATH = u'connections'
BATCH_CAT = u'Images from Nordiska museet'  # stem for maintenance categories
BATCH_DATE = u'2017-10'  # branch for this particular batch upload
EXPECTED_HEADER = u'Identifikationsnr|Typ av objekt|Benämning|Material|' + \
                  u'Namn-Konstnär|Konstnär-KulturNav|Namn-Konstruktör|' + \
                  u'Konstruktör-KulturNav|Namn-Konstruktör|Namn-Fotograf|' + \
                  u'Namn-Tillverkare|Namn-Tillverkare|Namn-Tillverkare|' + \
                  u'Datering-Fotografering|Datering-Produktion|Avbildade namn|' + \
                  u'Avbildade-KulturNav|Avbildade namn|Avbildade namn|' + \
                  u'Avbildade - orter|Ämnesord|Beskrivning|Motiv-ämnesord|' + \
                  u'Motiv-beskrivning|Rättigheter|Samling|Dimukode'


class NordicMuseumInfo(MakeBaseInfo):
    """Construct file descriptions and filenames for the NordicMuseum batch upload."""

    def __init__(self):
        """
        Initialise a make_info object.

        @param batch_cat: base_name for maintanance categories
        @param batch_label: label for this particular batch
        """
        # handle kultur_nav connections
        self.k_nav_list = {}

        # black-listed values
        self.bad_namn = (u'okänd fotograf', u'okänd konstnär')
        self.bad_date = (u'odaterad', )

        super(NordicMuseumInfo, self).__init__(BATCH_CAT, BATCH_DATE)

    def load_data(self, in_file):
        """
        Load the provided data (in whichever format) and produce a dict with an
        entry per file which can be used for further processing.

        @param in_file: the path to the metadata file
        @return: dict
        """
        key_col = u'Identifikationsnr'
        lists = (u'Ämnesord', u'Material', u'Motiv-ämnesord')
        return csv_methods.csv_file_to_dict(in_file, key_col, EXPECTED_HEADER,
                                            non_unique=True, lists=lists,
                                            list_delimiter=',')

    def process_data(self, raw_data):
        """
        Take the loaded data and construct a NordicMuseumItem for each.
        """
        d = {}
        for key, value in raw_data.iteritems():
            d[key] = NordicMuseumItem.make_item_from_raw(value, self)

        self.data = d

    def add_to_k_nav_list(self, uuid, namn):
        """
        Add an uuid to self.k_nav_list
        """
        # Convert url to uuid
        if uuid.startswith(u'http://kulturnav.org'):
            uuid = uuid.split('/')[-1]
        if uuid:
            if uuid in self.k_nav_list.keys():
                if namn not in self.k_nav_list[uuid]['namn']:
                    self.k_nav_list[uuid]['namn'].append(namn)
            else:
                self.k_nav_list[uuid] = {'namn': [namn, ]}

    def load_mappings(self, update=True):
        """
        Update mapping files, load these and package appropriately.

        @param update: whether to first download the latest mappings
        """
        # update mappings
        pages = {'people': 'people', 'keywords': 'keywords',
                 'places': 'places', 'materials': 'materials'}
        if update:
            commons_prefix = u'Commons:Nordiska museet/Batch upload'
            listscraper.scrape(pages, commons_prefix,
                               working_path=self.cwd_path,
                               out_path=OUT_PATH)

        # read mappings
        for k, v in pages.iteritems():
            listfile = os.path.join(self.cwd_path, OUT_PATH,
                                    u'commons-%s.json' % v)
            pages[k] = common.open_and_read_file(
                listfile, codec='utf-8', as_json=True)

        # package mappings for consumption
        people = {}
        for p in pages['people']:
            if isinstance(p['more'], list):
                p['more'] = '/'.join(p['more'])  # since this should be an url
            people[p['name']] = listscraper.formatEntry(p)
        keywords = {}
        for p in pages['keywords']:
            keywords[p['name']] = listscraper.formatEntry(p)
        places = {}
        for p in pages['places']:
            places[p['name']] = listscraper.formatEntry(p)
        materials = {}
        for p in pages['materials']:
            materials[p['name']] = listscraper.formatEntry(p)

        # add to mappings
        self.mappings['people'] = people
        self.mappings['keywords'] = keywords
        self.mappings['places'] = places
        self.mappings['materials'] = materials

    def generate_filename(self, item):
        """
        Given an item (dict) generate an appropriate filename.

        The filename has the shape: descr - Collection - id
        and does not include filetype
        """
        descr = item.generate_filename_descr()
        return helpers.format_filename(descr, item.samling, item.idno)

    def make_info_template(self, item):
        """
        Given an item of any type return the filled out template.

        @param item: the metadata for the media file in question
        @return: str
        """
        if item.typ == u'Foto':
            return self.make_foto_info(item)
        elif item.typ == u'Föremål':
            return self.make_artwork_info(item)

    def make_foto_info(self, item):
        """
        given an item of typ=Foto output the filled out template
        """
        descr = u'{{Photograph\n'
        descr += u' |photographer         = %s\n' % self.get_creator(
            item.namn_fotograf)
        descr += u' |title                = \n'
        descr += u' |description          = %s\n' % item.get_description()
        descr += u' |original description = %s\n' % (
            item.get_original_description(), )
        descr += u' |depicted people      = %s\n' % '/'.join(
            self.get_depicted_object(item, typ='person'))
        descr += u' |depicted place       = %s\n' % (
            item.get_depicted_place(self.mappings), )
        if item.avbildat_fartyg:
            linked_objects = self.get_depicted_object(item, typ='ship')
            descr += NordicMuseumInfo.get_depicted_ship_field(linked_objects)
        descr += u' |date                 = %s\n' % (
            helpers.std_date_range(item.date_foto), )
        descr += u' |medium               = %s\n' % (
            item.get_materials(self.mappings), )
        descr += u' |institution          = %s\n' % item.get_institution()
        descr += u' |accession number     = %s\n' % item.get_id_link()
        descr += u' |source               = %s\n' % item.get_source()
        descr += u' |permission           = {{NordicMuseum cooperation project}}\n'
        descr += u'%s\n' % item.get_license()
        descr += u' |other_versions       = \n'
        descr += u'}}'
        return descr

    def make_artwork_info(self, item):
        """
        given an item of typ=Föremål output the filled out template
        """
        descr = u'{{Artwork\n'
        descr += u' |artist               = '
        if item.namn_konstnar:
            descr += self.get_creator(item.namn_konstnar)
        elif item.namn_konstruktor:
            descr += self.get_creator(item.namn_konstruktor)
        descr += u'\n'
        if item.namn_tillverkare:
            descr += NordicMuseumInfo.get_manufacturer_field(
                self.get_creator(item.namn_tillverkare))
        descr += u' |title                = \n'
        descr += u' |object type          = %s\n' % item.benamning
        descr += u' |description          = %s' % item.get_description()
        if item.avbildad_person:
            linked_objects = self.get_depicted_object(item, typ='person')
            descr += u'<br>\n{{depicted person|style=plain text|%s}}' % \
                     '|'.join(linked_objects)
        if item.avbildat_fartyg:
            linked_objects = self.get_depicted_object(item, typ='ship')
            descr += u'<br>\n{{depicted ship|style=plain text|%s}}' % \
                     '|'.join(linked_objects)
        if item.avbildad_ort:
            descr += u'<br>\n{{depicted place|%s}}' % (
                item.get_depicted_place(self.mappings), )
        descr += u'\n'
        descr += NordicMuseumInfo.get_original_caption_field(
            item.get_original_description())
        descr += u' |date                 = %s\n' % helpers.std_date_range(
            item.date_produktion)
        descr += u' |medium               = %s\n' % (
            item.get_materials(self.mappings), )
        descr += u' |institution          = %s\n' % item.get_institution()
        descr += u' |accession number     = %s\n' % item.get_id_link()
        descr += u' |source               = %s\n' % item.get_source()
        descr += u' |permission           = {{NordicMuseum cooperation project}}\n'
        descr += u'%s\n' % item.get_license()
        descr += u' |other_versions       = \n'
        descr += u'}}'
        return descr

    @staticmethod
    def get_depicted_ship_field(value):
        """Add the template field for depicted ships."""
        return u' |other_fields_2       = {{depicted ship' \
               u'|style=information field|%s}}\n' % '|'.join(value)

    @staticmethod
    def get_manufacturer_field(value):
        """Add the template field for manufacturer."""
        return u' |other_fields_1       = {{Information field' \
               u'|name={{LSH artwork/i18n|manufacturer}}' \
               u'|value=%s}}\n' % value

    @staticmethod
    def get_original_caption_field(value):
        """Add the template field for original caption."""
        return u' |other_fields_2       = {{Information field' \
               u'|name={{original caption/i18n|header}}' \
               u'|value=%s}}\n' % value

    def get_original_filename(self, item):
        """
        Convert the idno to the equivalent format used for the image files
        """
        return item.idno.replace(u':', u'_').replace(u'/', u'_')

    def get_creator(self, creator):
        """
        given a creator (or creators) return the creator template,
        linked entry or plain name
        """
        # multiple people
        if isinstance(creator, list):
            creators = []
            for person in creator:
                creators.append(self.get_creator(person))
            return '</br>'.join(creators)
        # single person with fallback chain creator, link, category, extlink
        if creator in self.mappings['people']:
            if self.mappings['people'][creator]['creator']:
                return u'{{Creator:%s}}' % (
                    self.mappings['people'][creator]['creator'], )
            elif self.mappings['people'][creator]['link']:
                return u'[[%s|%s]]' % (
                    self.mappings['people'][creator]['link'], creator)
            elif self.mappings['people'][creator]['category']:
                return u'[[:Category:%s|%s]]' % (
                    self.mappings['people'][creator]['category'][0], creator)
            elif self.mappings['people'][creator]['more']:  # kulturnav
                return u'[%s %s]' % (
                    self.mappings['people'][creator]['more'], creator)
        # if you get here you have failed to match
        return creator

    def generate_content_cats(self, item, withBenamning=True):
        """
        Extract any mapped keyword categories or depicted categories.

        @param item: the item to analyse
        @param withBenamning: whether item.benamning should be included
        """
        cats = []
        keywords = item.amnesord + item.motiv_amnesord
        if withBenamning and item.benamning:
            keywords += [item.benamning, ]
        for k in keywords:
            if k.lower() in self.mappings['keywords']:
                cats += self.mappings['keywords'][k.lower()]['category']
        # depicted objects
        for k in item.avbildad_namn:
            if k in self.mappings['people']:
                cats += self.mappings['people'][k]['category']
        # depicted places?

        cats = list(set(cats))  # remove any duplicates
        return cats

    def generate_meta_cats(self, item, content_cats):
        """
        Produce maintanance categories related to a media file.

        @param item: the metadata for the media file in question
        @param content_cats: any content categories for the file
        @return: list of categories (without "Category:" prefix)
        """
        pass
        cats = []

        # base cats
        cats.append(item.get_source_cat())
        cats.append(self.batch_cat)

        # problem cats
        if not self.generate_content_cats(item, withBenamning=False):
            # excludes item.benamning
            cats.append(self.make_maintanance_cat(u'improve categories'))
        if not item.get_description():
            cats.append(self.make_maintanance_cat(u'add description'))

        # creator cats
        creators = item.namn_tillverkare + item.namn_konstruktor
        creators.append(item.namn_konstnar)
        creators.append(item.namn_fotograf)
        for creator in creators:
            if creator and creator in self.mappings['people'] and \
                    self.mappings['people'][creator]['category']:
                cats += self.mappings['people'][creator]['category']

        cats = list(set(cats))  # remove any duplicates
        return cats

    def get_depicted_object(self, item, typ):
        """
        given an item get a linked version of the depicted person/ship
        param typ: one of "person", "ship", "all"
        """
        # determine type
        label = None
        if typ == 'person':
            label = item.avbildad_person
        elif typ == 'ship':
            label = item.avbildat_fartyg
        elif typ == 'all':
            label = item.avbildad_namn
        else:
            pywikibot.output(u'get_depicted_object() called with invalid type')
            return

        # extract links
        linked_objects = []
        for obj in label:
            if obj in self.mappings['people']:
                if self.mappings['people'][obj]['link']:
                    linked_objects.append(u'[[%s|%s]]' % (
                        self.mappings['people'][obj]['link'], obj))
                elif self.mappings['people'][obj]['category']:
                    if len(self.mappings['people'][obj]['category']) != 0:
                        pywikibot.output(
                            u'Object linking with multiple categoires: '
                            u'%s (%s)' % (obj, ', '.join(
                                self.mappings['people'][obj]['category'])))
                        linked_objects.append(obj)
                    else:
                        linked_objects.append(u'[[:Category:%s|%s]]' % (
                            self.mappings['people'][obj]['category'][0], obj))
                elif self.mappings['people'][obj]['more']:  # kulturnav
                    linked_objects.append(u'[%s %s]' % (
                        self.mappings['people'][obj]['more'], obj))
                else:
                    linked_objects.append(obj)
            else:
                linked_objects.append(obj)
        return linked_objects

    @classmethod
    def main(cls, *args):
        """Command line entry-point."""
        super(NordicMuseumInfo, cls).main(*args)


class NordicMuseumItem(object):
    """Store metadata and methods for a single media file."""

    def __init__(self, initial_data):
        """
        Create a NordicMuseumItem item from a dict where each key is an attribute.

        @param initial_data: dict of data to set up item with
        """
        for key, value in initial_data.iteritems():
            setattr(self, key, value)

    @staticmethod
    def make_item_from_raw(entry, NordicMuseum_info):
        """
        Given the raw metadata for an item, construct an NordicMuseumItem.

        @param entry: the raw metadata entry as a dict
        @param NordicMuseum_info: the parent NordicMuseum_info instance
        @return: NordicMuseumItem
        """
        d = {}
        # map to internal labels and flip names
        d['idno'] = entry[u'Identifikationsnr']
        d['typ'] = entry[u'Typ av objekt']
        d['benamning'] = entry[u'Benämning']
        d['material'] = entry[u'Material']
        d['namn_konstnar'] = helpers.flip_name(entry[u'Namn-Konstnär'])
        namn_konstnar_knav = entry[u'Konstnär-KulturNav']
        d['namn_konstruktor'] = helpers.flip_names(entry[u'Namn-Konstruktör'])
        namn_konstruktor_knav = entry[u'Konstruktör-KulturNav']
        d['namn_fotograf'] = helpers.flip_name(entry[u'Namn-Fotograf'])
        d['namn_tillverkare'] = helpers.flip_names(entry[u'Namn-Tillverkare'])
        d['date_foto'] = entry[u'Datering-Fotografering']
        d['date_produktion'] = entry[u'Datering-Produktion']
        avbildad_namn = entry[u'Avbildade namn']
        avbildad_namn_knav = entry[u'Avbildade-KulturNav']
        d['avbildad_ort'] = entry[u'Avbildade - orter']
        d['amnesord'] = entry[u'Ämnesord']
        d['beskrivning'] = entry[u'Beskrivning']
        d['motiv_amnesord'] = entry[u'Motiv-ämnesord']
        d['motiv_beskrivning'] = entry[u'Motiv-beskrivning']
        d['rattighet'] = entry[u'Rättigheter']
        d['samling'] = entry[u'Samling']
        d['dimukod'] = entry[u'Dimukode']

        # handle kulturNav
        if namn_konstnar_knav:
            NordicMuseum_info.add_to_k_nav_list(
                namn_konstnar_knav, d['namn_konstnar'])
        if namn_konstruktor_knav:
            NordicMuseum_info.add_to_k_nav_list(
                namn_konstruktor_knav,
                d['namn_konstruktor'][0])
        if avbildad_namn_knav:
            NordicMuseum_info.add_to_k_nav_list(
                avbildad_namn_knav,
                helpers.flip_name(avbildad_namn[0]))

        # split avbildad_namn into people and ships/boat types
        # a person is anyone with a name like Last, First
        d['avbildad_person'] = []
        d['avbildat_fartyg'] = []
        for a in avbildad_namn:
            if a != helpers.flip_name(a):
                d['avbildad_person'].append(helpers.flip_name(a))
            else:
                d['avbildat_fartyg'].append(a)
        # add to dict, now with flipped names
        d['avbildad_namn'] = d['avbildad_person'] + d['avbildat_fartyg']

        # cleanup lists
        d['avbildad_person'] = common.trim_list(d['avbildad_person'])
        d['avbildat_fartyg'] = common.trim_list(d['avbildat_fartyg'])
        d['avbildad_namn'] = common.trim_list(d['avbildad_namn'])

        # cleanup blacklisted
        if d['date_foto'].strip('.').lower() in NordicMuseum_info.bad_date:
            d['date_foto'] = ''
        if d['date_produktion'].strip('.').lower() in NordicMuseum_info.bad_date:
            d['date_produktion'] = ''
        if d['namn_konstnar'].lower() in NordicMuseum_info.bad_namn:
            d['namn_konstnar'] = ''
        if d['namn_fotograf'].lower() in NordicMuseum_info.bad_namn:
            d['namn_fotograf'] = ''

        return NordicMuseumItem(d)

    def get_original_description(self):
        """
        Given an item get an appropriate original description
        """
        descr = ''
        if self.benamning:
            descr += u'\n%s: %s\n' % (helpers.italicize(u'Benämning'),
                                      self.benamning)
        if self.motiv_beskrivning:
            descr += u'\n%s: %s\n' % (helpers.italicize(u'Motivbeskrivning'),
                                      self.motiv_beskrivning)
        if self.motiv_amnesord:
            descr += u'\n%s: %s\n' % (helpers.italicize(u'Motiv-ämnesord'),
                                      ', '.join(self.motiv_amnesord))
        if self.beskrivning:
            descr += u'\n%s: %s\n' % (helpers.italicize(u'Beskrivning'),
                                      self.beskrivning)
        if self.amnesord:
            descr += u'\n%s: %s\n' % (helpers.italicize(u'Ämnesord'),
                                      ', '.join(self.amnesord))
        return descr

    def get_description(self):
        """
        Given an item get an appropriate description
        """
        descr = ''
        if self.benamning:
            descr += u'%s: ' % self.benamning
        if self.motiv_beskrivning:
            descr += u'%s. ' % self.motiv_beskrivning
        if self.beskrivning:
            descr += u'%s. ' % self.beskrivning

        if len(descr) > 0:
            descr = u'{{sv|%s}}' % descr.rstrip(' :')
        return descr

    def get_id_link(self):
        """
        Format an accession number link
        """
        dimu_url = u'//digitaltmuseum.se/%s' % self.dimukod
        return u'[%s %s]' % (dimu_url, self.idno)

    def get_source(self):
        """
        Given an item produce a source statement
        """
        if self.namn_fotograf:
            return u'%s / %s' % (self.namn_fotograf, self.samling)
        else:
            return self.samling

    def get_institution(self):
        if self.samling == u'Sjöhistoriska museet':
            return u'{{Institution:Sjöhistoriska museet}}'
        elif self.samling == u'Vasamuseet':
            return u'{{Institution:Vasamuseet}}'
        else:
            pywikibot.output(u'No Institution')

    def get_license(self):
        """
        Sets rights and attribution and runs a minor sanity check
        note: cannot determine death year of creator
        """
        if self.rattighet == u'Erkännande-Dela lika':
            return u'{{CC-BY-SA-3.0|%s}}' % self.get_source()
        elif self.rattighet == u'Utgången skyddstid':
            if self.typ == u'Foto':
                if len(self.date_foto) > 0 and \
                        int(self.date_foto[:4]) > 1969:
                    pywikibot.output(
                        '%s: PD-Sweden-photo with year > 1969' % self.idno)
                return u'{{PD-Sweden-photo}}'
            elif self.typ == u'Föremål':
                testdate = self.date_produktion.lower().strip('ca efter')
                if len(self.date_produktion) > 0 and int(testdate[:4]) > 1945:
                    pywikibot.output(
                        '%s: PD-old-70 with year > 1945' % self.idno)
                return u'{{PD-old-70}}'

    def get_depicted_place(self, mappings):
        """
        given an item get a linked version of the depicted Place
        """
        place = self.avbildad_ort
        if place in mappings['places']:
            if mappings['places'][place]['other']:
                return mappings['places'][place]['other']

        return self.avbildad_ort

    def get_materials(self, mappings):
        """
        given an item get a linked version of the materials
        """
        linked_materials = []
        for material in self.material:
            material = material.lower()
            if material in mappings['materials'] and \
                    mappings['materials'][material]['technique']:
                linked_materials.append(
                    u'{{technique|%s}}' %
                    mappings['materials'][material]['technique'])
            else:
                linked_materials.append(material)
        return ', '.join(linked_materials)

    def generate_filename_descr(self):
        """
        Given an item generate an appropriate description for the filename.
        """
        # benamning which need more info
        need_more = (u'Fartygsmodell', u'Fartygsporträtt', u'Marinmotiv',
                     u'Modell', u'Ritning', u'Teckning', u'Akvarell', u'Karta',
                     u'Kopparstick', u'Lavering', u'Sjökort', u'Sjöstrid',
                     u'Porträtt')
        txt = u''
        if self.typ == u'Foto':
            if self.avbildad_namn:
                txt += ', '.join(self.avbildad_namn)
                if self.avbildad_ort:
                    txt += u'. %s' % self.avbildad_ort
                if self.date_foto:
                    txt += u'. %s' % self.date_foto
            elif self.motiv_beskrivning:
                txt += self.motiv_beskrivning
        elif self.typ == u'Föremål':
            txt += self.benamning
            if self.benamning in need_more:
                txt2 = ''
                if self.avbildad_namn:
                    txt2 += ', '.join(self.avbildad_namn)
                elif self.motiv_beskrivning:
                    txt2 += self.motiv_beskrivning
                if self.avbildad_ort:
                    txt2 += u'. %s' % self.avbildad_ort
                if self.date_produktion:
                    txt2 += u'. %s' % self.date_produktion
                txt = u'%s-%s' % (txt, txt2)
        return txt

    def get_source_cat(self):
        if self.samling == u'Sjöhistoriska museet':
            return u'Images from Sjöhistoriska museet'
        elif self.samling == u'Vasamuseet':
            return u'Images from Vasamuseet'
        else:
            pywikibot.output(u'No Institution-catalog')


if __name__ == "__main__":
    NordicMuseumInfo.main()
