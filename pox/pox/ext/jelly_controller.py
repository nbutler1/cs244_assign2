# Copyright 2012 James McCauley
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
This component is for use with the OpenFlow tutorial.

It acts as a simple hub, but can be modified to act like an L2
learning switch.

It's roughly similar to the one Brandon Heller did for NOX.
"""

from struct import pack
from zlib import crc32
from pox.core import core
from pox.lib.packet.tcp import tcp
from pox.lib.packet.udp import udp
from pox.lib.packet.ipv4 import ipv4
from pox.lib.packet.arp import arp
import pox.openflow.libopenflow_01 as of
from pox.ext.homestretch_routing import HomestretchRouting

log = core.getLogger()
IP_TYPE    = 0x0800



class Tutorial (object):
  """
  A Tutorial object is created for each switch that connects.
  A Connection object for that switch is passed to the __init__ function.
  """
  def __init__ (self, event):
    # Keep track of the connection to the switch so that we can
    # send it messages!
    connection = event.connection
    self.dpid = event.dpid
    self.connection = connection
    
    # This binds our PacketIn event listener
    connection.addListeners(self)

    # Use this table to keep track of which ethernet address is on
    # which switch port (keys are MACs, values are ports).
    self.mac_to_port = {}
    self.r = HomestretchRouting(0, './pox/ext/TOPOLOGY') 
    self.dpid_to_mac = {}

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

  def resend_packet (self, packet_in, out_port, event = None):
    """
    Instructs the switch to resend a packet that it had sent to us.
    "packet_in" is the ofp_packet_in object the switch had sent to the
    controller due to a table-miss.
    """
    msg = of.ofp_packet_out()
    msg.data = packet_in
    #else:
      #msg = of.ofp_packet_out(in_port=of.OFPP_NONE, data = event.ofp)
    #  msg = of.ofp_flow_mod()
    #  msg.data = event.ofp 
    #  msg.idle_timeout = 10
    #  msg.hard_timeout = 30
    # Add an action to send to the specified port
    action = of.ofp_action_output(port = out_port)
    msg.actions.append(action)

    # Send message to switch
    self.connection.send(msg)


  def act_like_hub (self, packet, packet_in):
    """
    Implement hub-like behavior -- send all packets to all ports besides
    the input port.
    """
    # We want to output to all ports -- we do that using the special
    # OFPP_ALL port as the output port.  (We could have also used
    # OFPP_FLOOD.)
    self.resend_packet(packet_in, of.OFPP_ALL)

    # Note that if we didn't get a valid buffer_id, a slightly better
    # implementation would check that we got the full data before
    # sending it (len(packet_in.data) should be == packet_in.total_len)).


  def get_hop(self, packet):
      if isinstance(packet.next, ipv4):
          next_hop = self.r.get_route(packet.next.srcip, packet.next.dstip, self._ecmp_hash(packet), 's' + str(self.dpid))
          if next_hop != -1 and next_hop in self.dpid_to_mac:
              return self.dpid_to_mac[next_hop]
      return packet.dst

  def act_like_switch (self, packet, packet_in, event):
    """
    Implement switch-like behavior.
    """

    if packet.src not in self.mac_to_port:
        self.mac_to_port[packet.src] = packet_in.in_port
    if event.dpid not in self.dpid_to_mac:
        self.dpid_to_mac[event.dpid] = packet.src
    #log.info(self.dpid_to_mac)  


    """
    if isinstance(packet.next, ipv4) and event.dpid < 1000:
      ip_pack = packet.next
      log.info("source: " + str(ip_pack.srcip))
      print "GETTING ROUTING INFORMATION"
      route, p = self.r.get_route(ip_pack.srcip, ip_pack.dstip, self._ecmp_hash(packet), 's' + str(self.dpid)) 
      if p is not None:
        log.info("Sending out specified port")
        port = p
        self.resend_packet(packet_in, p, event)
        return
      else:
        log.info("PORT IS NONE ERROR")
    """
    next_hop = self.get_hop(packet)
    if next_hop in self.mac_to_port:
        log.info('Installing Flow from ' + str(self.dpid) + ' ' + str(next_hop))
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.match.idle_timeout = 10
        msg.match.hard_timeout = 30
        action = of.ofp_action_output(port = self.mac_to_port[next_hop])
        msg.actions.append(action)
        self.connection.send(msg)
        self.resend_packet(packet_in, self.mac_to_port[next_hop])
    else:
        self.resend_packet(packet_in, of.OFPP_ALL)
    #if packet.dst not in self.mac_to_port:
      #print "HAVE NOT SEEN MAC ADDRESS"
    #log.info(packet.next)
    #self.resend_packet(packet_in, of.OFPP_ALL) 
    #else:
    #  print "ALREADY SEEN MAC ADDRESS!!"
      #log.info(packet.next)
    #  self.resend_packet(packet_in, self.mac_to_port[packet.dst], event)
    

  def _handle_PacketIn (self, event):
    """
    Handles packet in messages from the switch.
    """

    packet = event.parsed # This is the parsed packet data.
    if not packet.parsed:
      log.warning("Ignoring incomplete packet")
      return

    packet_in = event.ofp # The actual ofp_packet_in message.
    #print event.dpid
    # Comment out the following line and uncomment the one after
    # when starting the exercise.
    #print "Src: " + str(packet.src)
    #print "Dest: " + str(packet.dst)
    #print "Event port: " + str(event.port)
    #self.act_like_hub(packet, packet_in)
    #log.info("packet in")
    self.act_like_switch(packet, packet_in, event)



def launch ():
  """
  Starts the component
  """
  def start_switch (event):
    log.debug("Controlling %s" % (event.connection,))
    Tutorial(event)
  core.openflow.addListenerByName("ConnectionUp", start_switch)
