#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2013 Gianni Vialetto, http://www.rootcube.net
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import imaplib
import email
import sys
import subprocess
import concurrent.futures as cf
from argparse import ArgumentParser, RawDescriptionHelpFormatter

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================

def verbose_print(message, verbosity, min_verbosity=1):
    """
    print a message if verbosity level is >= min_verbosity
    """
    if verbosity >= min_verbosity:
        print(message)

def imap_fatal(mail, result, message):
    """
    check for imap command result

    params:
    - mail: an imap object from imaplib.IMAP4*
    - result: the result of the imap function
    - message: description of error

    """
    if result == 'OK':
        return True

    print('FATAL ERROR: %s' % message)
    imap_logout(mail)
    sys.exit(1)

# =============================================================================
# IMAP helpers
# =============================================================================

def imap_login(user, password,
               host, port=imaplib.IMAP4_PORT, ssl=False,
               verbose=0):
    try:
        m = imaplib.IMAP4_SSL(host, port) if ssl else imaplib.IMAP4(host, port)
        
        verbose_print('Connection to %s established.' % host,
            verbose)
        
        result, data = m.login(user, password)
        imap_fatal(m, result, 'login failed. Check your username/password')

        verbose_print('Login done.', verbose)
                       
        return m
    except OSError as e:
        print('connection failed: check your network or the IMAP server name')
        sys.exit(1)
    except Exception as e:
        print("connection failed: %s" % e)
        sys.exit(1)

def imap_logout(mail):
    mail.close()
    mail.logout()

# =============================================================================
# Spam checking functions
# =============================================================================

def spam_check(mail, 
               action='move',
               boxes=['INBOX'],
               spam_dir='Spam',
               only_unread=True, 
               verbose=0,
               workers=5):
    # get uids for every mailbox and do a parallel check using the
    # spamassassin daemon/client
    with cf.ThreadPoolExecutor(max_workers=workers) as tpe:
        results = []
        for box in boxes:
            uids = get_mailbox_uids(mail, box, only_unread, verbose)
            # let's optimize this a little if we have no messages
            if not uids:
                results.append([])
                continue
            results.append(check_mailbox(tpe, mail, uids))

    for box, res in zip(boxes, results):
        if not res:
            verbose_print('%s: 0 spam messages found' % box, 
                          verbose)
            continue
        
        result, num = mail.select(mailbox=box)
        if result != 'OK':
            verbose_print('cannot select mailbox %s.' % box,
                          verbose, 0)  
            continue
        
        spam_uids = [x[0] for x in res if x[1] == True]
        verbose_print('%s: %d spam messages found' % (box, len(spam_uids)),
                      verbose)

        if spam_uids:
            uid_str = b','.join(spam_uids)
            # move all the spam in "Spam" directory
            if action == 'move':
                mail.uid('copy', uid_str, spam_dir)

            mail.uid('store', uid_str, '+FLAGS', '(\Deleted)')
            mail.expunge()

def get_mailbox_uids(mail, box, only_unread=True, verbose=0):
    result, num = mail.select(mailbox=box)
    if result != 'OK':
        verbose_print('cannot select mailbox %s' % box,
                      verbose, 1)
        return []

    result, data = mail.uid('search', 
                            None, 
                            'UNSEEN' if only_unread else 'ALL')
    if result != 'OK':
        verbose_print('cannot get info from mailbox %s' % box,
                      verbose, 1)
        return []      
    
    # get a list of UIDs
    data = data[0].split()
    verbose_print('Found %d messages in %s' % (len(data), box),
                  verbose)

    return data

def check_mailbox(tpe, mail, uid_list):
    # RFC822.PEEK enable us to look at mails without marking them as read
    result, data = mail.uid('fetch', b','.join(uid_list), '(RFC822.PEEK)')
    # data as a result of multiple UID command is a list of 
    # <tuple>, <uid string>, <tuple>, <uid_string>, ...
    # we are only interested in the tuples (more precisely in the second
    # member of the tuple, which is the email in raw text (header+body)
    return tpe.map(do_spamcheck, 
                   uid_list, 
                   (x[1] for x in data if isinstance(x, tuple)))

def do_spamcheck(uid, mail_raw):
    p = subprocess.Popen(['spamc', '-c'], 
                          stdin=subprocess.PIPE, 
                          stdout=subprocess.PIPE)
    try:
        score = p.communicate(mail_raw)[0]
    except:
        return (uid, False, score)

    if score == '0/0\n':
        return (uid, False, score)

    if p.returncode == 0:
        return (uid, False, score)

    return (uid, True, score)

# =============================================================================
# Spam learning functions
# =============================================================================

def spam_learn(mail, spam_dir='Spam', workers=5, verbose=0):
    verbose_print('Starting learning mode on mailbox %s' % spam_dir, verbose)
    with cf.ThreadPoolExecutor(max_workers=workers) as tpe:
        result, num = mail.select(mailbox=spam_dir)
        if result != 'OK':
            print('Could not select mailbox %s. Aborting.' % spam_dir)
            return

        result, data = mail.uid('search', None, 'ALL')
        if result != 'OK':
            print('Cannot get info from mailbox %s. Aborting.' % spam_dir)
            return
    
        uid_list = data[0].split() 
        result, data = mail.uid('fetch', b','.join(uid_list), '(RFC822)')
        if result != 'OK':
            print('Cannot get fetch mails from mailbox %s. Aborting.' % spam_dir)
            return       

        # see check_mailbox for info
        l = tpe.map(do_spamlearn, 
                    uid_list, 
                    (x[1] for x in data if isinstance(x, tuple)))

        if verbose > 0:
            print('Learned %s new messages.' \
                      % len([x for x in l if x == True]))

def do_spamlearn(uid, mail_raw):
    # This needs spamd started with the --allow-tell option
    p = subprocess.Popen(['spamc', '-L', 'spam'], 
                         stdin=subprocess.PIPE, 
                         stdout=subprocess.PIPE)
    try:
        out = p.communicate(mail_raw)[0]
    except:
        return False
    code = p.returncode
    if code == 69 or code == 74: # error connecting
        return False
    if code == 5: # learned now
        return True
    if code == 6: # already learned
        return False
    # catch all not learned
    return False

# =============================================================================
# Config parsing
# =============================================================================

def config_check_args(args):
    if not args.config:
        # args.config not specified in options
        if not args.user or not args.password or not args.server:
            print('error: config file (-c/--config) or one or more ' \
                      'required arguments ' \
                      '(-s/--server, -u/--user, -w/--password) not specified.')
            return None
        
        return False
    else:
        if args.user or args.password or args.server:
            print('error: both config file (-c/--config) and one or more ' \
                      'required arguments ' \
                      '(-s/--server, -u/--user, -w/--password) specified.')
            return None
        return True

def config_parse(args):
   cfg_file = config_check_args(args)
   if cfg_file == None:
       # whhops, something is wrong with arguments
       return None

   if cfg_file:
       conf = config_file(args.config)
   else:
       conf = { 'user': args.user, 'pass': args.password, 'host': args.server }
   
   if not conf:
       return None

   if args.ssl == True and args.port == imaplib.IMAP4_PORT:
       port = imaplib.IMAP4_SSL_PORT
   else:
       port = args.port

   return dict({
           'port': port,
           'ssl': args.ssl,
           'boxes': args.mailboxes,
           'spam-dir': args.spam_dir,
           'method': args.method,
           'all-mail': args.all_mail}, **conf)
   
def config_file(path):
    import os
    import configparser

    try:
        if path == 'default':
            d = os.environ.get('XDG_CONFIG_HOME')
            if not d: raise IOError                
            path = '%s/imap-checker/config' % d
            
        if not os.path.isfile(path): raise IOError
        with open(path) as f: pass
    except IOError as e:
        print('ERROR: config file \'%s\' not found. Aborting.' % path)
        return None

    cp = configparser.ConfigParser()
    cp.read(path)
    d = {}
    
    if len(cp.sections()) != 1:
        print('ERROR: config file contains a number of sections that' \
                  'differs from one. Aborting.')
        return None

    srv = cp.sections()[0]
    d['host'] = srv

    if not set(['user', 'password']) <= set(cp.options(srv)):
        print('ERROR: option \'user\' and \'password\' are REQUIRED in ' \
                  'config file for IMAP server %s. Please check your ' \
                  'config.' % srv)
        return None
    d['user'] = cp[srv]['user']
    d['pass'] = cp[srv]['password']

    if 'domain' in cp[srv]: d['user'] = '%s/%s' % (cp[srv]['domain'], 
                                                   d['user'])
    if 'port' in cp[srv]: d['port'] = int(cp[srv]['port'])
    if 'ssl' in cp[srv]: d['ssl'] = cp[srv].getboolean('ssl')
    if 'boxes' in cp[srv]: d['boxes'] = ['INBOX'] + cp[srv]['boxes'].split(',')
    if 'all-mail' in cp[srv]: d['all-mail'] = cp[srv].getboolean('all-mail')
    if 'spam-dir' in cp[srv]: d['spam-dir'] = cp[srv]['spam-dir']

    return d

# =============================================================================
# MAIN
# =============================================================================

# unfortunately, we need this

def main(argc, argv):
    p = ArgumentParser(formatter_class=RawDescriptionHelpFormatter,
                       description='Detects & deletes spam ' \
                           'from IMAP servers',
                       epilog='Those a little paranoid (or using this script ' \
                           'on multiuser systems) can\nuse-c to pass the ' \
                           'command line options in an .ini config file ' \
                           'with the\nfollowing format: \n\n' \
                           '\t[<server hostname>]\n' \
                           '\tuser: <user>\n' \
                           '\tpassword: <password>\n' \
                           '\tdomain: <domain (for exchange servers)>\n' \
                           '\tport: <port number>\n' \
                           '\tssl: <true/false>\n' \
                           '\tboxes: <boxes>\n' \
                           '\tspam-dir: <spam directory>\n' \
                           '\tall-mail: <true/false>')
    srv = p.add_argument_group('server')
    srv.add_argument('-s', '--server', 
                     default='',
                     help='the target imap server')
    srv.add_argument('-p', '--port', 
                     default=imaplib.IMAP4_PORT,
                     help='the imap server port')
    srv.add_argument('--ssl', 
                     action='store_true',
                     default=False,
                     help='use ssl for connecting to the imap server. ' \
                         'Default: false')
    auth = p.add_argument_group('authentication')
    auth.add_argument('-u', '--user',
                      default='',
                      help='the user for imap auth')
    auth.add_argument('-w', '--password', 
                      default='',
                      help='the password for imap auth')
    opt = p.add_argument_group('options')
    opt.add_argument('-l', '--learn',
                     action='store_true',
                     default=False,
                     help='instead of detecting spam, learns new spam' \
                         ' from --spam-dir')
    opt.add_argument('-m', '--method',
                     default='move',
                     choices=['move', 'delete'],
                     help='what should be done with spam when found. ' \
                         'Default: move')
    opt.add_argument('-d', '--spam-dir',
                     default='Spam',
                     help='the imap mailbox where spam is to be moved. ' \
                         'Default: Spam')
    opt.add_argument('-b', '--mailboxes',
                     action='append',
                     default=['INBOX'],
                     help='additional mailboxes other than INBOX to analyze' \
                         ' while searching for spam')
    opt.add_argument('--all-mail',
                     action='store_true',
                     default=False,
                     help='check every mail in the mailbox, not only unread' \
                         ' mails. Default: false')
    opt.add_argument('--workers',
                     type=int,
                     default=5,
                     help='the number of workers to use for spam checking. ' \
                         'Default: 5')
    opt.add_argument('-c', '--config',
                     nargs='?',
                     type=str,
                     default=None,
                     const='default',
                     help='an optional config file to be used instead of ' \
                         'command line configuration. Default: ' \
                         '$XDG_CONFIG_HOME/imap-checker/config')
    opt.add_argument('-v', '--verbose',
                     action='count',
                     default=0,
                     help='verbosity level (use more than once to increase)')
                     
    args = p.parse_args(argv)
              
    conf = config_parse(args)
    if not conf:
        return 1

    print(conf)
    mail = imap_login(conf['user'], conf['pass'], 
                      conf['host'], conf['port'], conf['ssl'],
                      args.verbose)
    if not args.learn:
        spam_check(mail, conf['method'],
                   conf['boxes'], conf['spam-dir'], not conf['all-mail'], 
                   args.verbose, args.workers)
    else:
        spam_learn(mail, conf['spam-dir'], args.workers, args.verbose)

    imap_logout(mail)
    return 0

if __name__ == '__main__':
    # no need to pass the program name to main()
    sys.exit(main(len(sys.argv)-1, sys.argv[1:]))
        
