import math
import os
import random
import sys
import json
import pickle
from multiprocessing.pool import ThreadPool
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.node import OVSController
from mininet.node import Controller
from mininet.node import RemoteController
from mininet.cli import CLI
sys.path.append("../../")
import networkx as nx
from pox.ext.jelly_pox import JELLYPOX
from subprocess import Popen
from time import sleep, time
from collections import defaultdict
from pox.ext.iperf_utils import iperfPairs

# Choosing fairly takes significantly more time.
CHOOSE_EQUAL_PATHS_FAIRLY = False
num_servers = 10
k_total_ports = 4
r_reserved_ports = 2
N_num_racks = int(math.ceil(num_servers / (k_total_ports - r_reserved_ports))) + 1
ip_mappings = {}

# Set these variables
old_topo = True # This sets if you are using a saved topology or a new one
seconds = 60 # Number of seconds to run iperf for
tcp8 = False # Set to true to run tcp 8 flows
remote = True # Sets if you are running a remote controller       

class JellyFishTop(Topo):

    def no_mappings_left(self, s1, switch_mappings, racks, saturated_switches, switch_wire_count, all_switches):
        # Get an available switch
        available_switches = list(set(all_switches) - set(switch_mappings[s1]))
        s3 = None
        while s3 is None:
            if len(available_switches) == 0:
                return switch_wire_count
            s2 = available_switches[random.randint(0, len(available_switches)-1)]
	    available_switches.remove(s2)        
            # Get a swtich connected to s2 but not s2
            s3_candidates = [elem for elem in switch_mappings[s2] if elem in available_switches]
            if len(s3_candidates) == 0:
            	if available_switches == []:
                    return switch_wire_count
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
        rack_count = 0
        """
        for i in range(N_num_racks):
          current_switch = self.addSwitch('s' + str(i))
          servers_on_switch = 0
          while server_count < num_servers and servers_on_switch < k_total_ports - r_reserved_ports:
            next_server = self.addHost('h' + str(server_count))
            self.addLink(current_switch, next_server)
            server_count += 1
            servers_on_switch += 1
          racks.append(current_switch)
	"""
        current_switch = self.addSwitch('s' + str(len(racks) + 1))
	fencepost = True
        for i in range(num_servers):
            next_server = self.addHost('h' + str(i + 1))
            self.addLink(current_switch, next_server, bw=10)
            rack_count += 1
            if rack_count == (k_total_ports - r_reserved_ports):
                rack_count = 0
                racks.append(current_switch)
                if i == num_servers - 1:
                    fencepost = False
                else:
                    current_switch = self.addSwitch('s' + str(len(racks) + 1))
        if fencepost:
            racks.append(current_switch)            
	print racks 
            
	# Mapping from switch index to indices it's mapped to
	print "Wiring Switches"
	switch_mappings = {i: [] for i in range(len(racks))}
	saturated_switches = []
	all_switches = [i for i in range(len(racks))]
	switch_wire_count = 0
	
	while switch_wire_count < (len(racks) * r_reserved_ports) and len(saturated_switches) < len(racks):
            switches_left = list(set(all_switches) - set(saturated_switches))
            #print switch_mappings
            #print saturated_switches
            #print "-----------------------------------"
            if len(switches_left) == 0:
	        break
	    if len(switches_left) == 1:
                s1 = switches_left[0]
                # Just have an odd port left so we are done...
                if len(switch_mappings[s1]) >= r_reserved_ports - 1:
                    #print "Breaking out here.."
                    break
		switch_wire_count = self.no_mappings_left(s1, switch_mappings, racks, saturated_switches, switch_wire_count, all_switches)
		continue

            # Get first switch
	    index = random.randint(0, len(switches_left)-1)
            s1 = switches_left[index]
            available_mappings = list(set(switches_left) - set(switch_mappings[s1]))
            if len(available_mappings) <= 1:
                for i in range(len(switches_left)):
	    	    index = random.randint(0, len(switches_left)-1)
                    #s1 = switches_left[i]
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
             
            #print "Mapping: " + str(s1) + '->' + str(s2)

            # Update saturated list
            if len(switch_mappings[s1]) >= r_reserved_ports or len(switch_mappings[s1]) >= len(racks) - 1:
                saturated_switches.append(s1)
            if len(switch_mappings[s2]) >= r_reserved_ports or len(switch_mappings[s2]) >= len(racks) - 1:
                saturated_switches.append(s2)
            switch_wire_count += 1

        switches = self.switches()
        print switches
        for i in range(len(racks)):
            for j in switch_mappings[i]:
                if j > i:
                    self.addLink(racks[i], racks[j], bw=10)
        print switch_mappings
        print racks
	print "Done bulding"

def writeOutJson(link_counts, filename):
        with open(filename, 'w') as file:
            file.write(json.dumps(link_counts))

def randomized_shortest_simple_paths(net, src, dst):
  """Randomize the order of equal-length paths.

  This is a drop-in replacement for nx.shortest_simple_paths(), but it takes
  significantly more time.
  """
  paths = nx.shortest_simple_paths(net, src, dst)
  equal_len_paths = []
  current_len = 0
  for p in paths:
    if len(p) > current_len:
      random.shuffle(equal_len_paths)
      for eq_p in equal_len_paths:
        yield eq_p
      equal_len_paths = []
      current_len = len(p)
    equal_len_paths.append(p)

  random.shuffle(equal_len_paths)
  for eq_p in equal_len_paths:
    yield eq_p

def eight_shortest_paths(matches, net):
        link_counts = {}
        for link in net.edges():
            if link[0].startswith('s') and link[1].startswith('s'):
                link_counts['%s-%s' % (link[0], link[1])] = 0
                link_counts['%s-%s' % (link[1], link[0])] = 0
        for pair in matches:
            #print pair
            shortest_paths = nx.shortest_simple_paths
            if CHOOSE_EQUAL_PATHS_FAIRLY:
              shortest_paths = randomized_shortest_simple_paths
	    paths = shortest_paths(net, pair[0], pair[1])
            count = 0
	    for p in paths:
		if count == 8:
		    break
                for i in range(1, len(p)):
                    if p[i-1].startswith('s') and p[i].startswith('s'):
                        link_counts[p[i-1] + '-' + p[i]] += 1
		count += 1
	print "RETURNING FROM 8SP"
        writeOutJson(link_counts, "8SP.txt")

def ecmp_routing(matches, net, num):
        link_counts = {}
        for link in net.edges():
            if link[0].startswith('s') and link[1].startswith('s'):
                link_counts['%s-%s' % (link[0], link[1])] = 0
                link_counts['%s-%s' % (link[1], link[0])] = 0

        for pair in matches:
            shortest_paths = nx.shortest_simple_paths
            if CHOOSE_EQUAL_PATHS_FAIRLY:
              shortest_paths = randomized_shortest_simple_paths
	    paths = shortest_paths(net, pair[0], pair[1])
            paths_considered = []
	    first = True
            #print '-----'
            for p in paths:
		if first:
		    smallest_len = len(p)
		    first = False
                if len(p) == smallest_len:
                    print p
                    paths_considered.append(p)
                    if len(paths_considered) == num:
                        break
                else:
                    break

            for p in paths_considered:
                for i in range(1, len(p)):
                    if p[i-1].startswith('s') and p[i].startswith('s'):
                        link_counts[p[i-1] + '-' + p[i]] += 1

        writeOutJson(link_counts, "ECMP_LINKS_" + str(num) + ".txt")

def getShortestPathMeasures(nx_graph):
        link_counts = defaultdict(int)
        
        # First Randomly match servers

        print "MATCHING"
        matches = get_permutation_map(
                ['h' + str(k) for k in range(num_servers)])

        # Now, get shortest paths
        print "8SP"
        eight_shortest_paths(matches, nx_graph)
        print "ECMP 8"
        ecmp_routing(matches, nx_graph, 8)
        print "ECMP 64"
        ecmp_routing(matches, nx_graph, 64)

def get_permutation_map(server_list):
  """Each member of the set must be mapped to a different member of the set."""
  assert len(server_list) > 1
  link_from = server_list
  link_to = list(server_list)
  while any(x == y for x, y in zip(link_from, link_to)):
    random.shuffle(link_to)
  return zip(link_from, link_to)

def run_iperf(arg):
        net = arg[0]
        m = arg[1]
        s = arg[2]
	""" Runs iperf.  Needed for multithreading. """
	speeds = net.iperf(hosts=[net.get(m[0]), net.get(m[1])], seconds=s)
	print "RETURNING"
	return speeds

def createIPMappings(hosts):
    ip_first = '10.0.'
    ip_second = 0
    ip_third = 1
    reverse_mapping = {}
    for i in range(len(hosts)):
        ip_str = ip_first + str(ip_second)  + '.' + str(ip_third)
        ip_mappings[ip_str] = hosts[i]
        reverse_mapping[hosts[i]] = ip_str
        ip_third += 1
        if ip_third == 256:
            ip_third = 0
            ip_second += 1
    writeOutJson(ip_mappings, "IPMAPPINGS.json") 
    #print reverse_mapping
    return reverse_mapping

def setIPs(net, reverse_map):
    for host in reverse_map.keys():
        net.get(host).setIP(reverse_map[host])


def experiment(net, seconds = 60, tcp8 = False):
        """ Runs experiment"""
        net.start()
        sleep(3)
        print "GETTING MATCHES"
        matches = get_permutation_map(
                ['h' + str(k + 1) for k in range(num_servers)])
	
        # Loop through and run iperf on matches.  DO WE NEED TO MULTITHREAD??
        #seconds = 60 # How long to run iperf

        print "Running Ping Tests"
        servers, clients = [], []
        for m in matches:
            servers.append(net.get(m[0]))
            clients.append(net.get(m[1]))
            print net.ping(hosts=[net.get(m[0]), net.get(m[1])])
        print "CALL TO IPERF PAIRS"
        #h1 = net.get('h1')
        #h1.ping('h2')
        #h1.ping('h3')
        results = iperfPairs({'time':seconds}, servers, clients, tcp8) 
        #print results
        writeOutJson(results, 'First_results.txt')	
	net.stop()

def main():
 

	# Clear the mininet
        os.system('sudo mn -c')

        # Buld topology or load one
        if old_topo:
            jelly_topo = pickle.load(open('testing_topo', 'rb'))
        else:
	    jelly_topo = JellyFishTop()
            with open('testing_topo', 'w') as f:
                pickle.dump(jelly_topo, f)

        # Convert to nx graph and pickle
        print "CONVERTING"
        nx_graph = nx.Graph(jelly_topo.convertTo(nx.MultiGraph))
        if not old_topo:
            with open('TOPOLOGY', 'w') as f:
                pickle.dump(nx_graph, f)

        # Create ip mappings
        reverse_map = createIPMappings(jelly_topo.hosts())
        
        # Build Mininet
        print "BUILDING MININET"
        # Use this if running a remote controller
        if remote:
	    net = Mininet(topo=jelly_topo, host=CPULimitedHost, link=TCLink,
                      controller=RemoteController)
	else:
            net = Mininet(topo=jelly_topo, host=CPULimitedHost, link=TCLink,
                      controller=JELLYPOX)

        # Run the experiment
        print "RUNNING EXPERIMENT"
        setIPs(net, reverse_map)
        experiment(net, seconds, tcp8)

if __name__ == "__main__":
	main()

