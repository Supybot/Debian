###
# Copyright (c) 2003-2005, James Vega
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
import time

from supybot.test import *

class DebianTestCase(PluginTestCase):
    plugins = ('Debian',)
    timeout = 100
    cleanDataDir = False
    fileDownloaded = False
    if network:
        def setUp(self, nick='test'):
            PluginTestCase.setUp(self)
            try:
                datadir = conf.supybot.directories.data
                if os.path.exists(datadir.dirize('Contents-i386.gz')):
                    pass
                else:
                    print
                    print "Downloading files, this may take awhile."
                    filename = datadir.dirize('Contents-i386.gz')
                    while not os.path.exists(filename):
                        time.sleep(1)
                    print "Download complete."
                    print "Starting test ..."
                    self.fileDownloaded = True
            except KeyboardInterrupt:
                pass

        def testDebBugNoHtml(self):
            self.assertNotRegexp('debian bug 287792', r'\<em\>')

        def testDebversion(self):
            self.assertHelp('debian version')
            self.assertRegexp('debian version lakjdfad',
                              r'^No package.*\(all\)')
            self.assertRegexp('debian version unstable alkdjfad',
                r'^No package.*\(unstable\)')
            self.assertRegexp('debian version gaim',
                              r'\d+ matches found:.*gaim.*\(stable')
            self.assertRegexp('debian version linux-wlan',
                              r'\d+ matches found:.*linux-wlan.*')
            self.assertRegexp('debian version --exact linux-wlan',
                              r'^No package.*\(all\)')
            self.assertError('debian version unstable')

        def testDebfile(self):
            self.assertHelp('file')
            if not self.fileDownloaded:
                pass
            self.assertRegexp('file --exact bin/gaim', r'net/gaim')

        def testDebincoming(self):
            self.assertNotError('incoming')

        def testDebianize(self):
            self.assertNotError('debianize supybot')

        def testDebstats(self):
            self.assertNotError('stats supybot')


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
