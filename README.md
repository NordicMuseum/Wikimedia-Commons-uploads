## About This Repository
This repository contains the python3 scripts used by the Nordic Museum to upload
images to Wikimedia Commons. It is based on [lokal-profil/upload_batches](https://github.com/lokal-profil/upload_batches).

This is a work in progress during the fall of 2017 and winter of 2018. For more
details, contact [Aron Ambrosiani](https://github.com/Ambrosiani). The remaining
work is listed as [Issues](https://github.com/NordicMuseum/Wikimedia-Commons-uploads/issues).
Most importantly, artifacts of the type "Thing" are not included in the upload
to Wikimedia Commons as they have a separate metadata structure than photographs.

### Additional Reading:
* [blog post (in Swedish)](http://nyamedier.blogg.nordiskamuseet.se/2017/12/att-flytta-bilder-fran-digitalt-museum-till-wikimedia-commons/)
about how to copy images from Digitalt museum to Wikimedia Commons using this
repository
* [Documentation of the Digitalt Museum API](https://github.com/NordicMuseum/DiMu-API-documentation)

## Requirements

To run it you will have to install [`BatchUploadTools`](https://github.com/lokal-profil/BatchUploadTools)
and [`pywikibot`](https://github.com/wikimedia/pywikibot-core) using:
`pip install -r requirements.txt`

*Note*: You might have to add the `--process-dependency-links` flag to the above
command if you are running a different version of pywikibot from the required one.

## User Account

The script must be run from an account which has the `upload_by_url` user right.
On Wikimedia Commons this is limited to users with one of the `image-reviewer`,
`bot`, `gwtoolset` or `sysop` flags. [Apply for `bot` rights](https://commons.wikimedia.org/wiki/Commons:Bots/Requests).

## Settings

The settings can be provided either via command line parameters (use `-help` to
see the available ones) or through the `settings.json` file (see `settings.example.json`
for the allowed paramters). Command lines values take preferene over those
provided by the settings file. If neither is given it falls back to the default
options.

The following settings cannot use the default options:

* **api_key**: your [Digitalt museum API key](https://dok.digitaltmuseum.org/sv/api)
(as provided by [KulturIT](mailto:support@kulturit.no)).
* **glam_code**: institution code in Digitalt Museum. [List of institution codes for Swedish museums](http://api.dimu.org/api/owners?country=se&api.key=demo)
* **folder_id**: unique id (12 digits) or uuid (8-4-4-4-12 hexadecimal digits)
of the Digitalt Museum folder used
* **wiki_mapping_root**: root page on Wikimedia Commons of which all mapping
tables are subpages (e.g. [Commons:Nordiska_museet/mapping](https://commons.wikimedia.org/wiki/Commons:Nordiska_museet/mapping)
for Nordic Museum)
* **default_intro_text**: Default wikitext to add at the top of mapping table
page. With `{key}` being the placeholder for the mapping table type (one of
`keywords`, `people` or `places`)


## Usage

### The basic workflow is the following:
1. Create settings.json (see above)
2. Create user-config.py with the bot username
3. Create user-password.py with the bot username & password. [Generate a bot password](https://commons.wikimedia.org/wiki/Special:BotPasswords).
### The following commands are run from the root folder of your installation:
4. Run `python importer/DiMuHarvester.py` to scrape info from the DiMu API and
generate a "harvest file". [Example output](https://github.com/NordicMuseum/Wikimedia-Commons-uploads/blob/master/examples/dimu_harvest_data.json)
5. Run `python importer/DiMuMappingUpdater.py` to pull the harvest file and
generate mapping files for Wikimedia Commons
### Upload mappings to Wikimedia Commons
6. Upload the generated mappings files in the `/connections` folder to Wikimedia
Commons. Example: location of the [Nordic Museum mappings](https://commons.wikimedia.org/wiki/Special:PrefixIndex/Commons:Nordiska_museet/)
7. Perform the mapping in the mapping tables.
### After uploading the mappings to Wikimedia Commons, the following commands are run from the root folder of your installation:
8. Run `python importer/make_NordicMuseum_info.py -in_file:dimu_harvest_data.json -base_name:nm_output -update_mappings:True`
to pull the harvest file and mappings and prepare the batch file. [Example output](https://github.com/NordicMuseum/Wikimedia-Commons-uploads/blob/master/examples/nm_output.json)
9. Run `python importer/uploader.py -in_path:nm_output.json -type:URL` to
perform the actual batch upload. `-cutoff:X` limits the number of files
uploaded to `X` (this will override settings)
