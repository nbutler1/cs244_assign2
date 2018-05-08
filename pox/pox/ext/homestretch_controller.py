# Copyright 2011-2012 James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
An L2 learning switch.

It is derived from one written live for an SDN crash course.
It is somwhat similar to NOX's pyswitch in that it installs
exact-match rules for each flow.
"""

from struct import pack
from zlib import crc32

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpid_to_str
from pox.lib.util import str_to_bool
from pox.lib.packet.tcp import tcp
from pox.lib.packet.udp import udp
from pox.lib.packet.ipv4 import ipv4
from pox.ext.homestretch_routing import HomestretchRouting

import time

log = core.getLogger()

# We don't want to flood immediately when a switch connects.
# Can be overriden on commandline.
_flood_delay = 0
IP_TYPE    = 0x0800

class BadassSwitch (object):
  """
  The learning switch "brain" associated with a single OpenFlow switch.

  When we see a packet, we'd like to output it on a port which will
  eventually lead to the destination.  To accomplish this, we build a
  table that maps addresses to ports.

  We populate the table by observing traffic.  When we see a packet
  from some source coming from some port, we know that source is out
  that port.

  When we want to forward traffic, we look up the desintation in our
  table.  If we don't know the port, we simply send the message out
  all ports except the one it came in on.  (In the presence of loops,
  this is bad!).

  In short, our algorithm looks like this:

  For each packet from the switch:
  1) Use source address and switch port to update address/port table
  2) Is transparent = False and either Ethertype is LLDP or the packet's
     destination address is a Bridge Filtered address?
     Yes:
        2a) Drop packet -- don't forward link-local traffic (LLDP, 802.1x)
            DONE
  3) Is destination multicast?
     Yes:
        3a) Flood the packet
            DONE
  4) Port for destination address in our address/port table?
     No:
        4a) Flood the packet
            DONE
  5) Is output port the same as input port?
     Yes:
        5a) Drop packet and similar ones for a while
  6) Install flow table entry in the switch so that this
     flow goes out the appopriate port
     6a) Send the packet out appropriate port
  """
  def __init__ (self, connection, transparent, routing_object, dpid):
    # Switch we'll be adding L2 learning switch capabilities to
    self.connection = connection
    self.transparent = transparent

    # Our table
    self.macToPort = {}
    self.dpidToMac = {}

    # We want to hear PacketIn messages, so we listen
    # to the connection
    connection.addListeners(self)

    # We just use this to know when to log a helpful message
    self.hold_down_expired = _flood_delay == 0
    self.r = routing_object
    self.dpid = dpid

    #log.debug("Initializing LearningSwitch, transparent=%s",
    #          str(self.transparent))
  
  def _ecmp_hash(self, packet):
    ''' Return an ECMP-style 5-tuple hash for TCP/IP packets, otherwise 0.
    RFC2992 '''
    hash_input = [0] * 5
    if isinstance(packet.next, ipv4):
      ip = packet.next
      hash_input[0] = ip.srcip.toUnsigned()
      hash_input[1] = ip.dstip.toUnsigned()
      hash_input[2] = ip.protocol
      if isinstance(ip.next, tcp) or isinstance(ip.next, udp):
        l4 = ip.next
        hash_input[3] = l4.srcport
        hash_input[4] = l4.dstport
        return crc32(pack('LLHHH', *hash_input))
      return 0

  def _handle_PacketIn (self, event):
    """
    Handle packet in messages from the switch to implement above algorithm.
    """

    packet = event.parsed

    def flood (message = None):
      """ Floods the packet """
      msg = of.ofp_packet_out()
      if time.time() - self.connection.connect_time >= _flood_delay:
        # Only flood if we've been connected for a little while...

        if self.hold_down_expired is False:
          # Oh yes it is!
          self.hold_down_expired = True
          log.info("%s: Flood hold-down expired -- flooding",
              dpid_to_str(event.dpid))

        if message is not None: log.debug(message)
        #log.debug("%i: flood %s -> %s", event.dpid,packet.src,packet.dst)
        # OFPP_FLOOD is optional; on some switches you may need to change
        # this to OFPP_ALL.
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
      else:
        pass
        #log.info("Holding down flood for %s", dpid_to_str(event.dpid))
      msg.data = event.ofp
      msg.in_port = event.port
      self.connection.send(msg)

    def drop (duration = None):
      """
      Drops this packet and optionally installs a flow to continue
      dropping similar ones for a while
      """
      if duration is not None:
        if not isinstance(duration, tuple):
          duration = (duration,duration)
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = duration[0]
        msg.hard_timeout = duration[1]
        msg.buffer_id = event.ofp.buffer_id
        self.connection.send(msg)
      elif event.ofp.buffer_id is not None:
        msg = of.ofp_packet_out()
        msg.buffer_id = event.ofp.buffer_id
        msg.in_port = event.port
        self.connection.send(msg)

    # map mac to port and dpid to mac
    self.macToPort[packet.src] = event.port # 1
    self.dpidToMac[event.dpid] = packet.src
    
    # if multicast, flood
    if packet.dst.is_multicast:
      flood() # 3a
      return
    

    if packet.dst not in self.macToPort: # 4
      flood("Port for %s unknown -- flooding" % (packet.dst,)) 
    else:
      port = self.macToPort[packet.dst]
      # Get route for
      if packet.type == IP_TYPE:
	ip_pack = packet.next
        log.info("source: " + str(ip_pack.srcip))
        route = self.r.get_route(ip_pack.srcip, ip_pack.dstip, self._ecmp_hash(packet)) 
        next_dpid = -1
        for i in range(len(route)):
          if route[i] == self.dpid and i < len(route) - 1:
            next_dpid = route[i + 1]
            break
        if next_dpid != -1:
          port = self.macToPort[self.dpidToMac[next_dpid]]     
  
      if port == event.port:
        log.warning("Same port for packet from %s -> %s on %s.%s.  Drop."
              % (packet.src, packet.dst, dpid_to_str(event.dpid), port))
        drop(10)
        return
      
      log.debug("installing flow for %s.%i -> %s.%i" %
                  (packet.src, event.port, packet.dst, port))
      msg = of.ofp_flow_mod()
      msg.match = of.ofp_match.from_packet(packet, event.port)
      msg.idle_timeout = 10
      msg.hard_timeout = 30
      msg.actions.append(of.ofp_action_output(port = port))
      msg.data = event.ofp # 6a
      self.connection.send(msg)


class homestretch (object):
  """
  Waits for OpenFlow switches to connect and makes them learning switches.
  """
  def __init__ (self, transparent):
    core.openflow.addListeners(self)
    self.transparent = transparent
    self.r = HomestretchRouting(0, './pox/ext/TOPOLOGY')

  def _handle_ConnectionUp (self, event):
    log.debug("Connection %s" % (event.connection,))
    BadassSwitch(event.connection, self.transparent, self.r, event.dpid)


def launch (transparent=False, hold_down=_flood_delay):
  """
  Starts an L2 learning switch.
  """
  log.debug("FUCK YOU IM HERE")
  try:
    global _flood_delay
    _flood_delay = int(str(hold_down), 10)
    assert _flood_delay >= 0
  except:
    raise RuntimeError("Expected hold-down to be a number")

  core.registerNew(homestretch, str_to_bool(transparent))
