import math
import os
import random
import sys
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.node import OVSController
from mininet.node import Controller
from mininet.node import RemoteController
from mininet.cli import CLI
sys.path.append("../../")
from pox.ext.jelly_pox import JELLYPOX
from subprocess import Popen
from time import sleep, time

num_servers = 686
k_total_ports = 48
r_reserved_ports = 36
N_num_racks = int(math.ceil(num_servers / (k_total_ports - r_reserved_ports)))

class JellyFishTop(Topo):
    ''' TODO, build your topology here'''
    def no_mappings_left(self, s1, switch_mappings, racks, saturated_switches, switch_wire_count, all_switches):
        # Get an available switch
        available_switches = list(set(all_switches) - set(switch_mappings[s1]))
        s3 = None
        while s3 is None:
            s2 = available_switches[random.randint(0, len(available_switches)-1)]
	    available_switches.remove(s2)        

            # Get a swtich connected to s2 but not s2
            s3_candidates = [elem for elem in switch_mappings[s2] if elem in available_switches]
            if len(s3_candidates) == 0:
                available_switches.append(s2)
                continue
            s3 = s3_candidates[random.randint(0, len(s3_candidates)-1)]

        # Remove link between s3 and s2
        switch_mappings[s2].remove(s3)
        switch_mappings[s3].remove(s2)

        # Add new Link
        switch_mappings[s1].append(s2)
        switch_mappings[s1].append(s3)
        switch_mappings[s2].append(s1)
        switch_mappings[s3].append(s1)

	# Updated saturated switches
        if len(switch_mappings[s1]) >= r_reserved_ports:
            saturated_switches.append(s1)
        return switch_wire_count + 2

    def build(self):
    	racks = []
        
        # Wire up servers
	print "Wiring Servers"
	server_count = 0
	for i in range(N_num_racks):
	    current_switch = self.addSwitch('s' + str(i))
	    servers_on_switch = 0
	    while server_count < num_servers and servers_on_switch < k_total_ports - r_reserved_ports:
                next_server = self.addHost('h' + str(server_count))
		self.addLink(current_switch, next_server)
                server_count += 1
                servers_on_switch += 1
            racks.append(current_switch)

	# Mapping from switch index to indices it's mapped to
	print "Wiring Switches"
	switch_mappings = {i: [] for i in range(len(racks))}
	saturated_switches = []
	all_switches = [i for i in range(len(racks))]
	switch_wire_count = 0
	while switch_wire_count < (N_num_racks * r_reserved_ports):
	    switches_left = list(set(all_switches) - set(saturated_switches))
            if len(switches_left) == 0:
	        break
	    if len(switches_left) == 1:
                s1 = switches_left[0]
                # Just have an odd port left so we are done...
                if len(switch_mappings[s1]) >= r_reserved_ports - 1:
                    break
		switch_wire_count = self.no_mappings_left(s1, switch_mappings, racks, saturated_switches, switch_wire_count, all_switches)
		continue

            # Get first switch
	    index = random.randint(0, len(switches_left)-1)
            s1 = switches_left[index]
            available_mappings = list(set(switches_left) - set(switch_mappings[s1]))
            if len(available_mappings) == 1:
                for i in range(len(switches_left)):
	    	    #index = random.randint(0, len(switches_left)-1)
                    s1 = switches_left[i]
                    available_mappings = list(set(switches_left) - set(switch_mappings[s1]))
                    if len(available_mappings) >= 2:
                        break                   
 
            available_mappings.remove(s1)
            
	    # If no available mappings, need to remove a link
            if len(available_mappings) == 0:
		switch_wire_count = self.no_mappings_left(s1, switch_mappings, racks, saturated_switches, switch_wire_count, all_switches)
		continue
            
            # Get second switch
            index2 = random.randint(0, len(available_mappings)-1)
            s2 = available_mappings[index2]
            
	    # Update mappings
            switch_mappings[s1].append(s2)
            switch_mappings[s2].append(s1)

            # Update saturated list
            if len(switch_mappings[s1]) >= r_reserved_ports:
                saturated_switches.append(s1)
            if len(switch_mappings[s2]) >= r_reserved_ports:
                saturated_switches.append(s2)
            switch_wire_count += 1

        for i in range(len(racks)):
            for j in switch_mappings[i]:
                if j > i:
                    self.addLink(racks[i], racks[j])
	print "Done bulding"


def experiment(net):
        net.start()
        sleep(3)
        net.pingAll()
        net.stop()

def main():
	topo = JellyFishTop()
	net = Mininet(topo=topo, host=CPULimitedHost, link = TCLink, controller=JELLYPOX)
	experiment(net)
	print "TESTING HERE"

if __name__ == "__main__":
	main()

