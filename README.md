IMAP-CHECKER
============

I was a little fed up with spam storms regularly filling my work mail, 
so i hacked this little script up to keep it at bay. 

Please see LICENSE for the license. Nothing restrictive (not worth it for a
little script i believe) but the third paragraph is *always* worth mentioning.
No warranty whatsoever, if your mails disappear it's not my fault. :)

Dependencies
------------

- spamassassin (spamd must be running)
- python 3


Basic usage
-----------

Kill spam in your inbox (unread mail only, useful mainly in crontab - yes i know 
it's not good at all for security, but this is made to run on your own 
laptop/pc, so...):
     
     $ imap-checker.py -s <server> -u <user> -w <password> --ssl

As an alternative you can use an ini config file like this:

     $ imap-checker.py -c <config_path>

The default location for the config file (when no config_path is specified) is
$XDG_CONFIG_HOME/imap-checker/config. The .ini file has the following format
(only 'user' and 'password' options are required, the rest can be passed on the
command line as parameters):

     [<imap_server_host>]
     user: <username>
     password: <password>
     domain: <domain of the user, useful for exchange servers>
     port: <port number, defaults to IMAP standard port>
     ssl: <enable ssl or not, defaults to disabled>
     boxes: <additional IMAP mailboxes to be checked>
     all-mail: <check everything, not only unread emails>
     treshold: <consider spam every mail above this rating (default: 4.5)>

Modes
-----

By default detected spam mails are moved in a "Spam" imap mailbox. 
If you do not like that you can simply nuke it all:

     $ imap-checker <credentials as above> -m delete

You can also change the destination mailbox (aka directory/label):

     $ imap-checker.py <credentials as above> -d Trash

Other options
-------------

     $ imap-checker.py -h


