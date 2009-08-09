###
# Copyright (c) 2003-2006,2008-2009 James Vega
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import os
import re
import gzip
import time
import popen2
import fnmatch

from ZSI.client import Binding

import supybot.conf as conf
import supybot.utils as utils
import supybot.world as world
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
from supybot.utils.iter import all, imap, ifilter

class Debian(callbacks.Plugin, plugins.PeriodicFileDownloader):
    threaded = True
    periodicFiles = {
        # This file is only updated once a week, so there's no sense in
        # downloading a new one every day.
        'Contents-i386.gz': ('ftp://ftp.us.debian.org/'
                             'debian/dists/unstable/Contents-i386.gz',
                             604800, None)
        }
    contents = conf.supybot.directories.data.dirize('Contents-i386.gz')
    def __init__(self, irc):
        callbacks.Plugin.__init__(self, irc)
        plugins.PeriodicFileDownloader.__init__(self)

    def file(self, irc, msg, args, optlist, glob):
        """[--{regexp,exact} <value>] [<glob>]

        Returns packages in Debian that includes files matching <glob>. If
        --regexp is given, returns packages that include files matching the
        given regexp.  If --exact is given, returns packages that include files
        matching exactly the string given.
        """
        self.getFile('Contents-i386.gz')
        # Make sure it's anchored, make sure it doesn't have a leading slash
        # (the filenames don't have leading slashes, and people may not know
        # that).
        if not optlist and not glob:
            raise callbacks.ArgumentError
        if optlist and glob:
            irc.error('You must specify either a glob or a regexp/exact '
                      'search, but not both.', Raise=True)
        for (option, arg) in optlist:
            if option == 'exact':
                regexp = arg.lstrip('/')
            elif option == 'regexp':
                regexp = arg
        if glob:
            regexp = fnmatch.translate(glob.lstrip('/'))
            regexp = regexp.rstrip('$')
            regexp = ".*%s.* " % regexp
        try:
            re_obj = re.compile(regexp, re.I)
        except re.error, e:
            irc.error(format('Error in regexp: %s', e), Raise=True)
        if self.registryValue('pythonZgrep'):
            fd = gzip.open(self.contents)
            r = imap(lambda tup: tup[0],
                     ifilter(lambda tup: tup[0],
                             imap(lambda line:(re_obj.search(line), line),fd)))
        else:
            try:
                (r, w) = popen2.popen4(['zgrep', '-ie', regexp, self.contents])
                w.close()
            except TypeError:
                # We're on Windows.
                irc.error(format('This command won\'t work on this platform.  '
                                 'If you think it should (i.e., you know that '
                                 'you have a zgrep binary somewhere) then '
                                 'file a bug about it at %u.',
                                 'http://sourceforge.net/projects/supybot'),
                          Raise=True)
        packages = set()  # Make packages unique
        try:
            for line in r:
                if len(packages) > 100:
                    irc.error('More than 100 packages matched, '
                              'please narrow your search.', Raise=True)
                try:
                    if hasattr(line, 'group'): # we're actually using
                        line = line.group(0)   # pythonZgrep  :(
                    (filename, pkg_list) = line.split()
                    if filename == 'FILE':
                        # This is the last line before the actual files.
                        continue
                except ValueError: # Unpack list of wrong size.
                    continue       # We've not gotten to the files yet.
                packages.update(pkg_list.split(','))
        finally:
            if hasattr(r, 'close'):
                r.close()
        if len(packages) == 0:
            irc.reply('I found no packages with that file.')
        else:
            irc.reply(format('%L', sorted(packages)))
    file = wrap(file, [getopts({'regexp':'regexpMatcher','exact':'something'}),
                       additional('glob')])

    _madisonUrl = \
        'http://qa.debian.org/madison.php?package=%s&text=on&a=%s&s=%s'
    _splitRe = re.compile(r'\s*\|\s*')
    def version(self, irc, msg, args, optlist, suite, package):
        """[--arch=<value>] [--verbose] [<suite>] <package name>

        Returns the current version(s) of a Debian package in the given suite
        (if any, otherwise all available ones are displayed), architecture, and
        component.

        Valid suites are: oldstable, stable, testing, unstable, experimental
        Valid architectures are: alpha, amd64, arm, armel, hppa, hurd-i386,
        i386, ia64, mips, mipsel, powerpc, s390, sparc
        """
        arch = ''
        verbose = False
        for (opt, val) in optlist:
            if opt == 'arch':
                arch = val
            if opt == 'verbose':
                verbose = True
        package = utils.web.urlquote(package)
        try:
            fd = utils.web.getUrlFd(self._madisonUrl %
                                    (utils.web.urlquote(package), arch, suite))
        except utils.web.Error, e:
            irc.error(format('I couldn\'t reach the search page (%s).', e),
                      Raise=True)
        versions = {}
        for line in fd:
            # package | version | suite | architectures
            (pkg, ver, ste, arch)  = self._splitRe.split(line.strip())
            versions.setdefault(ver, [[],[]])
            versions[ver][0].append(ste)
            versions[ver][1].append(arch)
        if versions:
            responses = []
            for (ver, (suites, archs)) in versions.iteritems():
                if verbose:
                    L = [': '.join((self.bold(suite), arch)) \
                         for (suite, arch) in zip(suites, archs)]
                    s = format('%s (%s)', ver, ', '.join(L))
                else:
                    s = format('%s (%s)', ver, ', '.join(suites))
                responses.append(s)
            responses.sort()
            irc.reply('; '.join(responses))
        else:
            irc.reply(format('No version information found for %s.', package))
    version = wrap(version, [getopts({'verbose': '',
                                      'arch': ('literal', ('alpha', 'amd64',
                                                           'arm', 'armel',
                                                           'hppa', 'hurd-i386',
                                                           'i386', 'ia64',
                                                           'mips',
                                                           'mipsel', 'powerpc',
                                                           's390', 'sparc')),
                                     }),
                             optional(('literal', ('oldstable', 'stable',
                                                   'testing', 'unstable',
                                                   'experimental')), ''),
                             'something'])

    _incomingRe = re.compile(r'<a href="(.*?\.deb)">', re.I)
    def incoming(self, irc, msg, args, optlist, globs):
        """[--{regexp,arch} <value>] [<glob> ...]

        Checks debian incoming for a matching package name.  The arch
        parameter defaults to i386; --regexp returns only those package names
        that match a given regexp, and normal matches use standard *nix
        globbing.
        """
        predicates = []
        archPredicate = lambda s: ('_i386.' in s)
        for (option, arg) in optlist:
            if option == 'regexp':
                predicates.append(r.search)
            elif option == 'arch':
                arg = '_%s.' % arg
                archPredicate = lambda s, arg=arg: (arg in s)
        predicates.append(archPredicate)
        for glob in globs:
            glob = fnmatch.translate(glob)
            predicates.append(re.compile(glob).search)
        packages = []
        try:
            fd = utils.web.getUrlFd('http://incoming.debian.org/')
        except utils.web.Error, e:
            irc.error(str(e), Raise=True)
        for line in fd:
            m = self._incomingRe.search(line)
            if m:
                name = m.group(1)
                if all(None, imap(lambda p: p(name), predicates)):
                    realname = utils.str.rsplit(name, '_', 1)[0]
                    packages.append(realname)
        if len(packages) == 0:
            irc.error('No packages matched that search.')
        else:
            irc.reply(format('%L', packages))
    incoming = thread(wrap(incoming,
                           [getopts({'regexp': 'regexpMatcher',
                                     'arch': 'something'}),
                            any('glob')]))

    def bold(self, s):
        if self.registryValue('bold', dynamic.channel):
            return ircutils.bold(s)
        return s

    _ptsUri = 'http://packages.qa.debian.org/cgi-bin/soap-alpha.cgi'
    def stats(self, irc, msg, args, pkg):
        """<source package>

        Reports various statistics (from http://packages.qa.debian.org/) about
        <source package>.
        """
        pkg = pkg.lower()
        pts = Binding(self._ptsUri)
        try:
            version = pts.latest_version(pkg)
            maintainer = pts.maintainer(pkg)
            bugCounts = pts.bug_counts(pkg)
        except ZSI.FaultException:
            irc.errorInvalid('source package name')
        version = '%s: %s' % (self.bold('Latest version'), version)
        mname = maintainer['name']
        memail = maintainer['email']
        maintainer = format('%s: %s %u', self.bold('Maintainer'), mname,
                            utils.web.mungeEmail(memail))
        bugsAll = format('%i Total', bugCounts['all'])
        bugsRC = format('%i RC', bugCounts['rc'])
        bugs = format('%i Important/Normal', bugCounts['in'])
        bugsMinor = format('%i Minor/Wishlist', bugCounts['mw'])
        bugsFixed = format('%i Fixed/Pending', bugCounts['fp'])
        bugL = (bugsAll, bugsRC, bugs, bugsMinor, bugsFixed)
        s = '.  '.join((version, maintainer,
                        '%s: %s' % (self.bold('Bugs'), '; '.join(bugL))))
        irc.reply(s)
    stats = wrap(stats, ['somethingWithoutSpaces'])

    _newpkgre = re.compile(r'<li><a href[^>]+>([^<]+)</a>')
    def new(self, irc, msg, args, section, glob):
        """[{main,contrib,non-free}] [<glob>]

        Checks for packages that have been added to Debian's unstable branch
        in the past week.  If no glob is specified, returns a list of all
        packages.  If no section is specified, defaults to main.
        """
        try:
            fd = utils.web.getUrlFd(
                'http://packages.debian.org/unstable/newpkg_%s' % section)
        except utils.web.Error, e:
            irc.error(str(e), Raise=True)
        packages = []
        for line in fd:
            m = self._newpkgre.search(line)
            if m:
                m = m.group(1)
                if fnmatch.fnmatch(m, glob):
                    packages.append(m)
        fd.close()
        if packages:
            irc.reply(format('%L', packages))
        else:
            irc.error('No packages matched that search.')
    new = wrap(new, [optional(('literal', ('main', 'contrib', 'non-free')),
                              'main'),
                     additional('glob', '*')])

    _bugUri = 'http://bugs.debian.org/%s'
    _soapUri = 'http://bugs.debian.org/cgi-bin/soap.cgi'
    _soapNs = 'Debbugs/SOAP/1'
    def bug(self, irc, msg, args, bug):
        """<num>

        Returns a description of the bug with bug id <num>.
        """
        server = Binding(self._soapUri, self._soapNs)
        response = server.get_status(bug)
        # response = {'s-gensym3': {bug1: {'date':..., ...}, bug2: ...}}
        status = response['s-gensym3']
        if status is None:
            irc.error('I could not find a bug report matching that number.',
                      Raise=True)
        status = status[bug]
        timeFormat = conf.supybot.reply.format.time()
        searches = (status['package'], status['subject'], status['originator'],
                    time.strftime(timeFormat, time.gmtime(status['date'])))
        severity = status['severity']
        tags = status['tags'].split()
        L = map(self.bold, ('Package', 'Subject', 'Reported'))
        resp = format('%s: %%s; %s: %%s; %s: by %%s on %%s', *L)
        resp = format(resp, *searches)
        if severity:
            resp += format('; %s: %s', self.bold('Severity'), severity)
        if tags:
            resp += format('; %s: %L', self.bold('Tags'), tags)
        resp += format('; %u', self._bugUri % bug)
        irc.reply(resp)
    bug = wrap(bug, [('id', 'bug')])

    _dpnRe = re.compile(r'"\+2">([^<]+)</font', re.I)
    def debianize(self, irc, msg, args, words):
        """<text>

        Turns <text> into a 'debian package name' using
        http://www.pigdog.com/features/dpn.html.
        """
        url = r'http://www.pigdog.org/cgi_bin/dpn.phtml?name=%s'
        try:
            text = utils.web.getUrl(url % '+'.join(words))
        except utils.web.Error, e:
            irc.error(str(e), Raise=True)
        m = self._dpnRe.search(text)
        if m is not None:
            irc.reply(m.group(1))
        else:
            irc.errorPossibleBug('Unable to parse webpage.')
    debianize = wrap(debianize, [many('something')])


Class = Debian


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
