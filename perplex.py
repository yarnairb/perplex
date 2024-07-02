#!/usr/bin/env python
# -*- coding: utf8 -*-
# Perplex - A Movie Renamer for Plex Metadata
# Copyright (c) 2015 Konrad Rieck (konrad@mlsec.org)

# yarnairb modifications
# Since I run this under windows WSL/Ubuntu but my Plex server
# is running on the host Windows server I needed to make some
# changes.

import argparse
import configparser
import datetime
import gzip
import signal
import json
import os
import shutil
import sqlite3
import sys
import subprocess
import progressbar as pb
import pretty_errors
from icecream import ic
from plexapi.myplex import MyPlexAccount
from plexapi.library import Library

# Chars to remove from titles
del_chars = "."
forbiddenCharsInNames = "\\", "/", ":", "*", "?", '"', "<", ">", "|"

# Configure icecream for my debugging purposes
ic.configureOutput(prefix='DEBUG: ', includeContext=True)

def signal_handler(signal_caught, frame):
    print("\nOperations interupted. Exiting.")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

pretty_errors.configure(
    stack_depth=1,
    display_locals=1,
    lines_before=2,
    lines_after=1,
    display_timestamp=1,
    timestamp_function=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
)


def ConnectPlex():
    global plex
    print("Establishing a connection to the Plex Server")
    print("Please wait.....")
    config = configparser.ConfigParser()
    config.read("plex_account.ini")
    login = config["PLEX"]["login"]
    password = config["PLEX"]["password"]
    server = config["PLEX"]["server"]
    account = MyPlexAccount(login, password)
    plex = account.resource(server).connect()  # returns a PlexServer instance

def get_resolution(movie_id):
    movie = plex.library.section("Movies").search(libtype="movie", id=movie_id)
    if not movie:
        resolution = "unknown"
    else:
        resolution =  movie[0].media[0].videoResolution
    
    if resolution.isnumeric():
        return f"{resolution}p"
    else:
        return resolution.upper()


def find_db(plex_dir, name):
    """Search for database file in directory"""

    for root, dirs, files in os.walk(plex_dir, onerror=errorOut):
        for file in files:
            if file == name:
                databasePath = os.path.join(root, file)
                print("Found Database: " + databasePath)
                return databasePath

    return None


def build_db(plex_dir, movies={}):
    """Build movie database from sqlite database"""

    print("Analyzing Plex database:")
    dbfile = find_db(plex_dir, "com.plexapp.plugins.library.db")

    db = sqlite3.connect(dbfile)

    # Select only movies with year
#    query = """
#        SELECT id, title, originally_available_at FROM metadata_items
#        WHERE metadata_type = 1 AND originally_available_at
#    """
    query = """
        SELECT metadata_items.id, metadata_items.title, media_items.width, media_items.video_codec, media_items.audio_codec, metadata_items.originally_available_at FROM metadata_items INNER JOIN media_items ON metadata_items.id = media_items.metadata_item_id
        WHERE metadata_items.metadata_type = 1 AND metadata_items.library_section_id = 1 AND metadata_items.originally_available_at
    """

    for row in db.execute(query):
        resolution = get_resolution(row[0])
        title = convert([x for x in row[1] if x not in del_chars])
        #print(f"Got: {resolution} for {title}")
        width = row[2]
        video = row[3]
        audio = row[4]
        year = datetime.date.fromtimestamp(row[5]).strftime("%Y")
        #movies[row[0]] = (title, year, [])
        movies[row[0]] = (title, width, video, audio, year, resolution, [])

    # Get files for each movie
    query = """
        SELECT mp.file FROM media_items AS mi, media_parts AS mp
        WHERE mi.metadata_item_id = %s AND mi.id = mp.media_item_id """

    files = 0
    for id in movies:
        try:
            for file in db.execute(query % id):
                #movies[id][2].append(file[0])
                movies[id][6].append(file[0])
                files += 1
        except Exception as e:
            errorOut(e)
    db.close()
    print(("%d movies and %d files" % (len(movies), files)))

    return movies


def print_doubles(files):
    print("Found multiple files :")
    for old_name in enumerate(files):
        print(old_name)


def errorOut(error):
    print("Error occured: " + str(error))
    sys.exit(-1)


def convert(s):
    new = ""
    for x in s:
        if x not in forbiddenCharsInNames:
            new += x
    return new


def windows_to_wsl_path(windows_path):
    # Use wslpath to convert Windows path to WSL path
    result = subprocess.run(["wslpath", windows_path], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Error converting path: {result.stderr.strip()}")
    return result.stdout.strip()


def build_map(movies, dest, printDoubles, directoryToRunOn="", mapping=[]):
    """Build mapping to new names"""

    #for title, year, files in list(movies.values()):
    for title, width, video, audio, year, resolution, files in list(movies.values()):
        counter = 0
        for i, old_name in enumerate(files):
            old_name = windows_to_wsl_path(old_name)
            if not str(old_name).__contains__(directoryToRunOn):
                continue
            counter = counter + 1
            if counter > 1 and printDoubles:
                print_doubles(files)
            _, ext = os.path.splitext(old_name)

            # BRM don't sub-dir
            #template = "%s (%s)/%s (%s)" % (title, year, title, year)
            #template = "%s (%s)" % (title, year)
            template = "%s (%s)-%s.%s.%s" % (title, year, video, resolution, audio)
            template += "-part%d" % (i + 1) if len(files) > 1 else ""
            template += ext
            template = "_".join(template.split())

            if dest is None:
                dest, garbage = str(_).rsplit("/", 1)
            else:
                dest = os.path.normpath(dest)

            new_name = os.path.join(dest, *template.split("/"))
            if new_name == old_name:
                continue
            mapping.append((old_name, new_name))

    mapping = [x_y for x_y in mapping if x_y[0].lower() != x_y[1].lower()]
    return mapping


def progressbar(dry):
    if dry:
        widgets = [""]
    else:
        widgets = [pb.Percentage(), " ", pb.Bar(), " ", pb.ETA()]
    return pb.ProgressBar(widgets=widgets)


def rename(mapping, dry):
    pbar = progressbar(dry)
    for old_name, new_name in pbar(mapping):
        try:
            if not os.path.exists(os.path.dirname(new_name)):
                if not dry:
                    os.makedirs(os.path.dirname(new_name))
            if not os.path.exists(new_name):
                if dry:
                    print(("%s\n\t%s" % (old_name, new_name)))
                else:
                    # BRM not taking chances
                    print(("Renaming: %s\n\tTo: %s" % (old_name, new_name)))
                    os.rename(old_name, new_name)
        except Exception as e:
            print("Exception on file " + old_name + " : " + str(e))


def copy_rename(mapping, dest, dry):
    """Copy and rename files to destination"""
    pbar = progressbar(dry)
    for old_name, new_name in pbar(mapping):
        dp = os.path.join(dest, os.path.dirname(new_name))
        fp = os.path.join(dp, os.path.basename(new_name))
        try:
            if not os.path.exists(dp):
                if not dry:
                    os.makedirs(dp)
            if not os.path.exists(fp):
                if dry:
                    print(("%s\n    %s" % (old_name, fp)))
                else:
                    # BRM not taking chances
                    pass
                    # shutil.copy(old_name, fp)
        except Exception as e:
            print("Exception on file " + old_name + " : " + str(e))


if __name__ == "__main__":
    # Parse command-line arguments

    parser = argparse.ArgumentParser(description="Plex-based Movie Renamer.")
    parser.add_argument(
        "--plex", metavar="<dir>", type=str, help="set directory of Plex database."
    )
    parser.add_argument(
        "--dest", metavar="<dir>", type=str, help="copy and rename files to directory"
    )
    parser.add_argument(
        "--save",
        metavar="<file>",
        type=str,
        help="save database of movie titles and files",
    )
    parser.add_argument(
        "--load",
        metavar="<file>",
        type=str,
        help="load database of movie titles and files",
    )
    parser.add_argument(
        "--dry", action="store_true", help="show dry run of what will happen"
    )
    parser.add_argument(
        "--justRename",
        metavar="<dir>",
        type=str,
        help="renames the original files instead of copying them - provide the <dir> to rename files in",
    )
    parser.add_argument(
        "--printDoubles",
        action="store_true",
        help="Print double movies with locations if found",
    )

    parser.set_defaults(dry=False)
    parser.set_defaults(printDoubles=False)
    args = parser.parse_args()

    if (args.justRename is not None and args.justRename is not False) and (
        args.dest is not None
    ):
        errorOut("Cant provide --dest and --justRename Args at the same time")

    ConnectPlex()

    if args.plex:
        movies = build_db(args.plex)
    elif args.load:
        print(("Loading metadata from " + args.load))
        movies = json.load(gzip.open(args.load))
    else:
        print("Error: Provide a Plex database or stored database.")
        sys.exit(-1)

    if args.save:
        print(("Saving metadata to " + args.save))
        with gzip.open(args.save, "wt", encoding="ascii") as file:
            json.dump(movies, file)

    if args.printDoubles:
        printDoubles = True
    else:
        printDoubles = False

    if args.justRename:
        print(("Building file mapping for each Movie itself"))
        mapping = build_map(movies, None, printDoubles, args.justRename)
        print(("Start Renaming the files in their original path"))
        rename(mapping, args.dry)
    elif args.dest:
        print(("Building file mapping for " + args.dest))
        mapping = build_map(movies, args.dest, printDoubles)
        print(("Copying renamed files to " + args.dest))
        copy_rename(mapping, args.dest, args.dry)
    else:
        if args.printDoubles:
            print(
                "Print doubles can only be used when building the mapping, try it with the --dry parameter"
            )
