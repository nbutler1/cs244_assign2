
import networkx as nx
import pickle
import json


ROUTING_TYPE_ECMP8 = 0
ROUTING_TYPE_ECMP64 = 1
ROUTING_TYPE_8SP = 2

class HomestretchRouting(object):
  def __init__(self, routing_type, path_to_file):
    """
    Args:
      routing_type: one of ROUTING_TYPE_{ECMP8,ECMP64,8SP}.
      path_to_file: string file path pointing to a pickled nx.Graph.
    """
    self.routing_type = routing_type
    with open(path_to_file, 'r') as f:
      self.nx_graph = pickle.load(f)
    with open('./pox/ext/IPMAPPINGS.json', 'rb') as fp:
      self.ip_mappings = json.load(fp)

  def ip_lookup(self, s, d):
    for k in self.ip_mappings.keys():
      print k
    return self.ip_mappings[s], self.ip_mappings[d]


  def get_route(self, src_name, dst_name, packet_hash):
    """Get list of names connecting src to dst.

    Args:
      src_name: String name of the node at which the packet is.
      dst_name: String name of the node at which the packet needs to go.
      packet_hash: An arbitrary integer, used to choose from among the multiple
          possible paths.
    Returns:
      A list of names, describing a simple path from src to dst.
    """
    src_name, dst_name = self.ip_lookup(str(src_name), str(dst_name))
    path_generator = nx.shortest_simple_paths(self.nx_graph, src_name, dst_name)
    paths = []
    if self.routing_type == ROUTING_TYPE_ECMP8:
      limit = 8
      for p in path_generator:
        paths.append(p)
        if len(paths) >= limit:
          break
    else:
      paths.append(path_generator.next())
      limit = self.routing_type == ROUTING_TYPE_ECMP8 and 8 or 64
      for p in path_generator:
        # All candidate paths must be the same cost (length).
        if len(p) != len(paths[0]):
          break
        paths.append(p)
        if len(paths) >= limit:
          break
    h = packet_hash % len(paths)
    return paths[h]


if __name__ == '__main__':
  # For testing
  r = HomestretchRouting(ROUTING_TYPE_8SP, 'TOPOLOGY')
  #print r.get_route('h0', 'h1', 0)
