## About this repo
This repo contains the python3 scripts used by the Nordic Museum to upload images
to Wikimedia Commons. It is based on [lokal-profil/upload-batches](https://github.com/lokal-profil/upload-batches).

To run it you will have to install [`BatchUploadTools`](https://github.com/lokal-profil/BatchUploadTools)
and [`pywikibot`](https://github.com/wikimedia/pywikibot-core) using:
`pip install -r requirements.txt`

*Note*: You might have to add the `--process-dependency-links` flag to the above
command if you are running a different version of pywikibot from the required one.

This is a work in progress during the fall of 2017. For more details, contact
[Aron Ambrosiani](https://github.com/Ambrosiani).

## User account

The script must be run from an account which has the `upload_by_url` user right.
On Wikimedia Commons this is limited to users with one of the `image-reviewer`,
`bot`, `gwtoolset` or `sysop` flags.

## Usage

The basic workflow is the following:

1. Create settings.json including the folder to be uploaded
2. Create user-config.py with the bot username
3. Create user-password.py with the bot username & password
4. Run `python importer/DiMuHarvester.py` to scrape info from the DiMu API
5. Run `python importer/DiMuMappingUpdater.py` to generate mapping files for Wikimedia Commons
6. Upload the mappings to Wikimedia Commons
7. Run `python importer/make_NordicMuseum_info.py -in_file:nm_data.json -base_name:nm_output -update_mappings:True` to prepare the batch file
8. Run `python importer/uploader.py -in_path:nm_output.json -type:URL` to perform the actual batch upload. `-cutoff:X` limits the number of files uploaded to `X`
