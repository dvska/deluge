#
# core.py
#
# Copyright (C) 2009 Andrew Resch <andrewresch@gmail.com>
#
# Basic plugin template created by:
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
# Copyright (C) 2007-2009 Andrew Resch <andrewresch@gmail.com>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
# 	The Free Software Foundation, Inc.,
# 	51 Franklin Street, Fifth Floor
# 	Boston, MA  02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception
#    statement from all source files in the program, then also delete it here.
#

import time

from deluge.log import LOG as log
from deluge.plugins.pluginbase import CorePluginBase
import deluge.component as component
import deluge.configmanager
from deluge.core.rpcserver import export
from deluge.event import DelugeEvent

from twisted.internet import reactor

DEFAULT_PREFS = {
    "low_down": -1.0,
    "low_up": -1.0,
    "low_active": -1,
    "button_state": [[1] * 7 for dummy in xrange(24)]
}

STATES = {
    0: "Green",
    1: "Yellow",
    2: "Red"
}

class SchedulerEvent(DelugeEvent):
    """
    Emitted when a schedule state changes.
    """
    def __init__(self, colour):
        """
        :param colour: str, the current scheduler state
        """
        self._args = [colour]

class Core(CorePluginBase):
    def enable(self):
        # Create the defaults with the core config
        core_config = component.get("Core").config
        DEFAULT_PREFS["low_down"] = core_config["max_download_speed"]
        DEFAULT_PREFS["low_up"] = core_config["max_upload_speed"]
        DEFAULT_PREFS["low_active"] = core_config["max_active_limit"]

        self.config = deluge.configmanager.ConfigManager("scheduler.conf", DEFAULT_PREFS)

        self.state = self.get_state()

        # Apply the scheduling rules
        self.do_schedule(False)

        # Schedule the next do_schedule() call for on the next hour
        now = time.localtime(time.time())
        secs_to_next_hour = ((60 - now[4]) * 60) + (60 - now[5])
        self.timer = reactor.callLater(secs_to_next_hour, self.do_schedule)

    def disable(self):
        try:
            self.timer.cancel()
        except:
            pass

    def update(self):
        pass


    def do_schedule(self, timer=True):
        """
        This is where we apply schedule rules.
        """

        state = self.get_state()

        if state == "Green":
            # This is Green (Normal) so we just make sure we've applied the
            # global defaults
            core_config = deluge.configmanager.ConfigManager("core.conf")
            core_config.apply_set_functions("max_download_speed")
            core_config.apply_set_functions("max_upload_speed")
            core_config.apply_set_functions("max_active_limit")
            # Resume the session if necessary
            component.get("Core").session.resume()
        elif state == "Yellow":
            # This is Yellow (Slow), so use the settings provided from the user
            session = component.get("Core").session
            session.set_download_rate_limit(int(self.config["low_down"] * 1024))
            session.set_upload_rate_limit(int(self.config["low_up"] * 1024))
            settings = session.settings()
            settings.active_limit = self.config["low_active"]
            session.set_settings(settings)
            # Resume the session if necessary
            component.get("Core").session.resume()
        elif state == "Red":
            # This is Red (Stop), so pause the libtorrent session
            component.get("Core").session.pause()

        if state != self.state:
            # The state has changed since last update so we need to emit an event
            self.state = state
            component.get("EventManager").emit(SchedulerEvent(self.state))

        if timer:
            # Call this again in 1 hour
            self.timer = reactor.callLater(3600, self.do_schedule)

    @export()
    def set_config(self, config):
        "sets the config dictionary"
        for key in config.keys():
            self.config[key] = config[key]
        self.config.save()
        self.do_schedule(False)

    @export()
    def get_config(self):
        "returns the config dictionary"
        return self.config.config

    @export()
    def get_state(self):
        now = time.localtime(time.time())
        level = self.config["button_state"][now[3]][now[6]]
        return STATES[level]
