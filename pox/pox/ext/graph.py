import matplotlib.pyplot as mtl
import json
import operator

def order_shit(obj):
    ranks = sorted([obj[k] for k in obj.keys()])
    return [i + 1 for i in range(len(ranks))], ranks 

def openjson(filename):
    with open(filename) as json_data:
        d = json.load(json_data)
    return order_shit(d)


x, y = openjson('8SP.txt')
mtl.plot(x, y, 'b', label= '8 shortest paths')

x, y = openjson('ECMP_LINKS_64.txt')
mtl.plot(x, y, 'r', label='64 way ECMP')

x, y = openjson('ECMP_LINKS_8.txt')
mtl.plot(x, y, 'g', label='8 way ECMP')


mtl.title('Figure 9 Recreation')
mtl.xlabel('Link Ranks')
mtl.ylabel('# of distinct paths link is on')
mtl.legend()
mtl.grid()
mtl.savefig('Output.png')
mtl.show()
