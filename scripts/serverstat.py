try:
  import os
except:
  print 'Library "os" is required'

import subprocess
import decimal
import socket
import fcntl
import struct
import array
import time
import sys
import platform;
import urllib
import urllib2

available_metrics=['cpu','load','disk','memory','network','users','processes','uptime']
long_running_metrics=['cpu','network']
LONG_RUNNING_SLEEP_TIME=5
VERSION="1.0.0"
API_PROTOCOL='http'
API_HOST='api.serverstat.io'
API_VERSION='v1'

try:
  is_64bits = sys.maxsize > 2**32
except AttributeError:
  import platform
  if platform.architecture()[0] == '32bit':
    is_64bits = False
  else:
    is_64bits = True

debug=False;


def send(data, core, key, host):
  if debug:
    print("Sending data")
  try:
    import json
  except:
    import simplejson as json
  current_time=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
  json_string=json.dumps({"host":core,current_time:data})
  opener = urllib2.build_opener(urllib2.HTTPHandler)
  request = urllib2.Request(API_PROTOCOL+'://'+API_HOST+'/'+API_VERSION+'/metric', data=json_string)
  request.add_header('X-org-key', key)
  request.add_header('X-host-key', host)
  request.get_method = lambda: 'POST'
  try:
    response = opener.open(request)
    response.read()
    sys.exit(0)
  except urllib2.HTTPError, e:
    print e.read()
    sys.exit(1)

  sys.exit(0)

def cpu_count():
  ''' Returns the number of CPUs in the system '''
  num = 1
  if sys.platform == 'win32':
    # fetch the cpu count for windows systems
    try:
      num = int(os.environ['NUMBER_OF_PROCESSORS'])
    except (ValueError, KeyError):
      pass
  elif sys.platform == 'darwin':
    # fetch teh cpu count for MacOS X systems
    try:
      num = int(os.popen('sysctl -n hw.ncpu').read())
    except ValueError:
      pass
  else:
    # an finally fetch the cpu count for Unix-like systems
    try:
      num = os.sysconf('SC_NPROCESSORS_ONLN')
    except (ValueError, OSError, AttributeError):
      pass
  return num


def get_cpu_time_list():
  statFile = file("/proc/stat", "r")
  cpus = {}
  lines = statFile.readlines()
  statFile.close()
  for line in lines:
    if line.startswith('cpu'):
      time_list = line.split()[1:5]
      for y in range(len(time_list)):
        time_list[y] = int(time_list[y])
      if line.split()[0] == 'cpu':
        key='total'
      else:
        key=line.split()[0];
      cpus[key] = time_list;
  if cpu_count() == 1:
    return {'total': cpus['total']}
  else:
    return cpus


def get_cpu_time_interval(x, y):
  if len(x) is 2:
    for i in range(len(x['total'])):
      y['total'][i] -= x['total'][i]
  else:
    for key, values in x.iteritems():
      for i in range(len(values)):
        y[key][i] -= x[key][i]

  return y


def diskstats_parse(dev=None):
  file_path = '/proc/diskstats'
  result = {}

  # ref: http://lxr.osuosl.org/source/Documentation/iostats.txt
  columns_disk = ['m', 'mm', 'dev', 'reads', 'rd_mrg', 'rd_sectors',
                  'ms_reading', 'writes', 'wr_mrg', 'wr_sectors',
                  'ms_writing', 'cur_ios', 'ms_doing_io', 'ms_weighted']

  columns_partition = ['m', 'mm', 'dev', 'reads', 'rd_sectors', 'writes', 'wr_sectors']

  lines = open(file_path, 'r').readlines()
  for line in lines:
    if line == '': continue
    split = line.split()
    if len(split) == len(columns_disk):
      columns = columns_disk
    elif len(split) == len(columns_partition):
      columns = columns_partition
    else:
      # No match
      continue
    data = dict(zip(columns_disk, split))
    if dev != None and dev != data['dev']:
      continue
    for key in data:
      if key != 'dev':
        data[key] = int(data[key])
    result[data['dev']] = data
  return result


def get_core_info():
  return {"client_version":VERSION,"cpus":cpu_count(), "hostname":platform.node(), "os":platform.system(), "tz": time.tzname[time.daylight]}


def get_network_bytes(interface):
  f=open('/proc/net/dev', 'r')
  lines=f.read().split("\n")[2:]
  for line in lines:
    if interface in line:
      data=line.split(':')[1].split()
      rx_bytes, tx_bytes=(data[0], data[8])
      return [int(rx_bytes), int(tx_bytes)]
  raise Exception('Device not found')


def all_interfaces():
  max_possible = 128  # arbitrary. raise if needed.
  bytes = max_possible * 32
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  names = array.array('B', '\0' * bytes)
  outbytes = struct.unpack('iL', fcntl.ioctl(
      s.fileno(),
      0x8912,  # SIOCGIFCONF
      struct.pack('iL', bytes, names.buffer_info()[0])
  ))[0]
  namestr = names.tostring()
  if is_64bits:
    lst = []
    for i in range(0, outbytes, 40):
      name = namestr[i:i+16].split('\0', 1)[0]
      ip   = namestr[i+20:i+24]
      lst.append([name, format_ip(ip)])
    return lst
  else:
    ret=[]
    vals=[namestr[i:i+32].split('\0', 1)[0] for i in range(0, outbytes, 32)]
    for int in vals:
      ret.append([int,'0.0.0.0'])
    return ret


def format_ip(addr):
  return str(ord(addr[0])) + '.' + \
    str(ord(addr[1])) + '.' + \
    str(ord(addr[2])) + '.' + \
    str(ord(addr[3]))


def getload():
  if debug:
    print("Getting load")
  load = os.getloadavg()
  return {'one': round(load[0], 2),
          'five': round(load[1], 2),
          'fifteen': round(load[2], 2)}


def getdisk():
  if debug:
    print("Getting disk information")
  stats = diskstats_parse()
  df=subprocess.Popen(["df", "-l", "-P"], stdout=subprocess.PIPE)
  disks=df.communicate()[0].decode().split("\n")[1:-1]
  found_disks={}
  for disk in disks:
    if disk.startswith("/dev"):
      device=disk.split()[0]
      found_disks[str(disk.split()[5])]={'dev':str(disk.split()[0]),
                                    'total':int(disk.split()[1])*1024,
                                    'used':int(disk.split()[2])*1024,
                                    'free':int(disk.split()[3])*1024,
                                    'percent':str(disk.split()[4])}

  return found_disks


def getmemory():
  if debug:
    print("getting memory")
  free=subprocess.Popen(["free", "-b"], stdout=subprocess.PIPE)
  output=free.communicate()[0].decode().split("\n")[1:]
  return {'ptotal': int(output[0].split()[1]),
          'pused': int(output[0].split()[2]),
          'stotal': int(output[2].split()[1]),
          'sused': int(output[2].split()[2]),
          'buffers': int(output[0].split()[5]),
          'cached': int(output[0].split()[6])}


def networkformatusage(first, second):
  ret = {}
  interfaces=all_interfaces()
  for int in interfaces:
    try:
      rx1,tx1=first[int[0]]
      rx2,tx2=second[int[0]]
      ret[int[0]] = {'addr':int[1],
                     'rx_total':rx2,
                     'tx_total':tx2,
                     'rx_avg':float((rx2-rx1)/LONG_RUNNING_SLEEP_TIME),
                     'tx_avg':float((tx2-tx1)/LONG_RUNNING_SLEEP_TIME)}
    except:
      pass
  return ret

def get_network_data():
  ret = {}
  interfaces=all_interfaces()
  for int in interfaces:
    try:
      ret[int[0]]=get_network_bytes(int[0])
    except:
      pass
  return ret

def getusers():
  if debug:
    print("Getting users")
  who=subprocess.Popen(["who", "-q"], stdout=subprocess.PIPE)
  output=who.communicate()[0].decode().split("\n")[1:-1]
  return {'count':int(output[0].split('=')[1])}


def getcpudata():
  return get_cpu_time_list()


def cpuformatusage(dt):
  '''
  dt = get_cpu_time_interval(2)
  '''
  vals = {}
  for key, values in dt.iteritems():
    total=sum(values)
    if total is 0:
      percent = 0.0;
    else:
      percent = 100 - (values[len(values) - 1] * 100.00 / total)
    vals[key] = {"percent": str('%.2f' %percent)}
  return vals


def getprocesses():
  if debug:
    print("Getting processes")
  ps=subprocess.Popen(["ps", "aux"], stdout=subprocess.PIPE)
  output=ps.communicate()[0].decode().split("\n")[1:]
  return {'count':len(output)}


def getuptime():
  f = open('/proc/uptime', 'r')
  try:
    val=int(float(f.readline().split()[0]))
  except:
    val=0
  try:
    f.close()
  except:
    pass
  return {'value':val}

args=None;

try:
  import argparse
  parser = argparse.ArgumentParser(description='Collect core metrics and send to the hostplot.me API')
  parser.add_argument("key", nargs='?', help="Your hostplot.me account key.")
  parser.add_argument("host", nargs='?', help="Your hostplot.me host UUID for this host.")
  parser.add_argument("-m", "--metrics", default='all', help="The metrics you wish to run.")
  parser.add_argument("-A", "--apihost", default=None, help="API Hostname to use, useful for development.")
  parser.add_argument("-V", "--version", action="store_true", help="Show client version.")
  parser.add_argument("-t", "--test", default=None, help="Run a test. Allowed values are all," + ','.join(available_metrics))
  args = parser.parse_args()
  key=args.key
  host=args.host
except ImportError:
  import optparse
  parser = optparse.OptionParser(usage="usage: %prog [-h] [-m METRICS] key host")
  parser.add_option("-m", "--metrics", default="all", dest="metrics", help="The metrics you wish to run.")
  parser.add_option("-A", "--apihost", default=None, dest="apihost", help="API Hostname to use, useful for development..")
  parser.add_option("-V", "--version", action="store_true", help="Show client version.")
  parser.add_option("-t", "--test", default=None, dest="test", help="Run a test. Allowed values are all," + ','.join(available_metrics))
  args, opts = parser.parse_args()
  key=opts[0]
  host=opts[1]

data={}

if not args:
  sys.exit(0)

if args.version is True:
  print VERSION
  sys.exit(0)

if key is None or host is None:
  print "Additional arguments required"
  sys.exit(1)

if args.apihost is not None:
  API_HOST=args.apihost


if args.test is not None:
  if "all" in args.test:
    test_metrics=available_metrics
  else:
    test_metrics=args.test.split(',')

  long_running = {}
  # find any log running metrics and kick them off
  for metric in test_metrics:
    if metric in long_running_metrics:
      if metric=='cpu':
        print "Running first-pass cpu metric test"
        long_running[metric]=get_cpu_time_list()
      elif metric=='network':
        long_running[metric]=get_network_data()
        print "Running first-pass network metric test"

  # if there are long running metrics then sleep
  if len(long_running) > 0:
    time.sleep(LONG_RUNNING_SLEEP_TIME)

  # now run the second pass for long running metrics
  for metric in test_metrics:
    if metric in long_running_metrics and long_running.has_key(metric):
      if metric=='cpu':
        print "Running second-pass cpu metric test"
        print cpuformatusage(get_cpu_time_interval(long_running[metric], get_cpu_time_list()))
      elif metric=='network':
        print "Running second-pass network metric test"
        print networkformatusage(long_running[metric], get_network_data())

  for metric in test_metrics:
    if metric not in long_running_metrics:
      if metric=="load":
        print 'Testing Load'
        print getload()
      elif metric=="disk":
        print 'Testing Disk'
        print getdisk()
      elif metric=="memory":
        print 'Testing Memory'
        print getmemory()
      elif metric=="users":
        print 'Testing Users'
        print getusers()
      elif metric=="processes":
        print 'Testing Processes'
        print getprocesses()
      elif metric=="uptime":
        print 'Testing Uptime'
        print getuptime()
      else:
        pass
else:
  if "all" in args.metrics:
    metrics=available_metrics
  else:
    metrics=args.metrics.split(',')

  long_running = {}

  # find any log running metrics and kick them off
  for metric in metrics:
    if metric in long_running_metrics:
      if metric=='cpu':
        long_running[metric]=get_cpu_time_list()
      elif metric=='network':
        long_running[metric]=get_network_data()

  # if there are long running metrics then sleep
  if len(long_running) > 0:
    time.sleep(LONG_RUNNING_SLEEP_TIME)

  # now run the second pass for long running metrics
  for metric in metrics:
    if metric in long_running_metrics and long_running.has_key(metric):
      if metric=='cpu':
        data['cpu']=cpuformatusage(get_cpu_time_interval(long_running[metric], get_cpu_time_list()))
      elif metric=='network':
        data['network'] = networkformatusage(long_running[metric], get_network_data())

  for metric in metrics:
    if metric not in long_running_metrics:
      if metric=="load":
        data['load'] = getload()
      elif metric=="disk":
        data['disk']=getdisk()
      elif metric=="memory":
        data['memory']=getmemory()
      elif metric=="users":
        data['users']=getusers()
      elif metric=="processes":
        data['processes']=getprocesses()
      elif metric=="uptime":
        data['uptime']=getuptime()
      else:
        pass

  send(data, get_core_info(), key, host)
