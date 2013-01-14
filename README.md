IMAP-CHECKER
============

I was a little fed up with spam storms regularly filling my work mail, 
so i hacked this little script up to keep it at bay. 

Please see LICENSE for the license. Nothing restrictive (not worth it for a
little script i believe) but the third paragraph is *always* worth mentioning.
No warranty whatsoever, if your mail disappear it's not my fault. :)

Dependencies
------------

- spamassassin (spamd must be running)


How to use
----------

Kill spam in your inbox (unread mail only, useful mainly in crontab - yes i know it's not good 
at all for security, but this is made to run on your own laptop/pc, so...)
     
     $ imap-checker -s <server> -u <user> -w <password> --ssl

By default detected spam mails are moved in a "Spam" imap mailbox. 
If you do not like that you can simply nuke it all:

     $ imap-checker <credentials as above> -m delete

Or change the destination mailbox (directory/label):

     $ imap-checker <credentials as above> -d Trash

For other options use:

     $ imap-checker -h


