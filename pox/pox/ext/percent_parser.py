import json
"""
This script reads in the given file of results from iperf
and outputs the percent utiilization assuming a line rate
"""

speeds = []                    
max_line_rate = 10.0              # Max line rate in Mbits/sec
filename = 'First_results.txt'    # Filename with results
print_individual_results = True  # Whether or not to print resutls

with open(filename, 'rb') as f:
    dumped = json.load(f)

def parse_out_speed(r):
    lines = r.split('\n')
    words = lines[-2].split(' ')
    return words[-2:]

for item in dumped:
    speed_obj = parse_out_speed(item['result'])
    speeds.append(float(speed_obj[0]) / max_line_rate)
    if print_individual_results:
        print "From "  + item['src'] + ' to ' + item['dest'] + ' results were: '
        print speed_obj[0] + ' ' + speed_obj[1]
        print '--------------------------------'


percentage = float(sum(speeds)) / float(len(speeds))
print "Percent utilization: " + str(percentage * 100) + '%'
