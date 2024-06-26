cp '/mnt/c/Users/yarna/AppData/Local/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db' /tmp
./perplex.py --plex /tmp --save /tmp/movies.db
./perplex.py --load /tmp/movies.db --justRename '/mnt/v/Net Movies' --dry --printDoubles
