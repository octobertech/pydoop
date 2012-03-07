# BEGIN_COPYRIGHT
# END_COPYRIGHT

# DEV NOTE: this module is used by the setup script, so it MUST NOT
# rely on extension modules.

import os, re, subprocess
import glob

class HadoopVersionError(Exception):
  pass


def __is_exe(fpath):
  return os.path.exists(fpath) and os.access(fpath, os.X_OK)

def version_tuple(version_string):
  """
  Break a version string into its components.

  The first 3 elements of the tuple are converted to integers and represents
  the major, minor, and bugfix Hadoop version numbers.  Subsequent elements,
  if they exist, are other various appendages (e.g., SNAPSHOt, cdh3, etc.).

  raises HadoopVersionError if the version string is in an unrecognized format.
  """
  # sample version strings:  "0.20.3-cdh3", "0.20.2", "0.21.2", '0.20.203.1-SNAPSHOT'
  error_msg = "unrecognized version string format: %r" % version_string
  if not re.match(r"(\d+)(\.\d+)*(-.+)?", version_string):
    raise HadoopVersionError(error_msg)

  parts = re.split('[.-]', version_string)
  if len(parts) < 3:
    raise HadoopVersionError(error_msg)
  try:
    vt = map(int, parts[0:3])
    if len(parts) > 3:
      vt = vt + parts[3:]
    vt = tuple(vt)
  except ValueError:
    raise HadoopVersionError(error_msg)
  return vt


def get_hadoop_version(hadoop_home=None):
  """
  Gets the Hadoop version for the version of Hadoop in the
  hadoop_home directory provided.

  If hadoop_home is None, tries to execute "hadoop version"
  and scans its output to detect the version number (see the
  version_tuple method for the format of the return value).
  """
  msg = "couldn't detect version for %r" % hadoop_home + ": %s"
  version = os.getenv("HADOOP_VERSION")
  if version:
    return version_tuple(version)
  hadoop_bin = get_hadoop_exec(hadoop_home)
  if not hadoop_bin:
    raise RuntimeError("Couldn't find hadoop executable in HADOOP_HOME/bin nor in your PATH.  Please adjust either of those variables.")
  args = [hadoop_bin, "version"]
  try:
    version = subprocess.Popen(
      args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
      ).communicate()[0].splitlines()[0].split()[-1]
  except (OSError, IndexError) as e:
    raise HadoopVersionError(msg % ("'%s %s' failed" % tuple(args)))
  else:
    return version_tuple(version)

def get_hadoop_exec(hadoop_home=None):
  # check whatever hadoop home the caller gave us
  if hadoop_home:
    hadoop = os.path.join(hadoop_home, "bin", "hadoop")
    if __is_exe(hadoop):
      return hadoop
  # check the environment's HADOOP_HOME
  if os.environ.has_key("HADOOP_HOME"):
    hadoop = os.path.join(os.environ["HADOOP_HOME"], "bin", "hadoop")
    if __is_exe(hadoop):
      return hadoop
  # search the PATH for hadoop
  for path in os.environ["PATH"].split(os.pathsep):
    hadoop = os.path.join(path, 'hadoop')
    if __is_exe(hadoop):
      return hadoop

  return None

class PathFinder(object):
  """
  Path finder
  Class that encapsulates the logic to find paths and other info required by
  Pydoop, such as:
  * Hadoop home
  * Hadoop version
  """

  def __init__(self):
    self.__hadoop_home = None
    self.__hadoop_conf = None
    self.__hadoop_version = None
    self.__initialized = False

  def hadoop_home(self):
    if not self.__initialized:
      self.__init_paths()
    if self.__hadoop_home is None:
      raise ValueError("HADOOP_HOME not set")
    return self.__hadoop_home

  def hadoop_version(self):
    if not self.__initialized:
      self.__init_paths()
    if self.__hadoop_version is None:
      raise HadoopVersionError("Could not determine Hadoop version")
    return self.__hadoop_version

  def hadoop_conf(self):
    if not self.__initialized:
      self.__init_paths()
    if self.__hadoop_conf is None:
      raise ValueError("HADOOP_CONF_DIR not set")
    return self.__hadoop_conf

  def cloudera(self):
    return self.__cloudera_version(self.hadoop_version())

  @staticmethod
  def __cloudera_version(ver):
    if ver is not None and len(ver) > 3:
      cloudera_re = re.compile("cdh.*")
      return any(map(cloudera_re.match, ver[3:]))
    else:
      return False

  def __init_paths(self):
    ######### HADOOP_HOME
    if os.environ.has_key("HADOOP_HOME"):
      self.__hadoop_home = os.getenv("HADOOP_HOME")
    else:
      # look in hadoop config files, under /etc/default.  In the hadoop-0.20
      # package from cloudera this is called hadoop-0.20.  I don't know how
      # they'll handle later versions (e.g., 0.20.203, 1.0.1, etc.).  Conflicting
      # packages?  More version appendages?  For now we'll just grab the
      # first of the sorted list of versions (should be the newest).
      hadoop_cfg_files = sorted(glob.glob("/etc/default/hadoop*"), reverse=True)
      if hadoop_cfg_files:
        with open(hadoop_cfg_files[0]) as f:
          # get HADOOP_HOME directories from this file.  If there's
          # more than one we keep the last one.
          dirs = [ line.rstrip("\n").split('=',1) for line in f.xreadlines() if re.match(r"\s*HADOOP_HOME=.*", line) ]
          if len(dirs) > 0:
            home_path = dirs[-1]
            if os.path.isdir(home_path):
              self.__hadoop_home = home_path

    if self.__hadoop_home is None:
      # Still no hadoop home.  Try a few standard paths then reduce the result to a single list
      paths = reduce(list.__add__, map(glob.glob, ("/opt/hadoop*", "/usr/lib/hadoop*", "/usr/local/lib/hadoop*"))) # others?
      if len(paths) > 0:
        self.__hadoop_home = paths[0]
    # give up on HADOOP_HOME

    ######### HADOOP_VERSION
    try:
      self.__hadoop_version = get_hadoop_version(self.__hadoop_home)
    except:
      pass # leave self.hadoop_version as None

    ######### HADOOP_CONF_DIR
    if os.environ.has_key("HADOOP_CONF_DIR"):
      self.__hadoop_conf = os.environ["HADOOP_CONF_DIR"]
    elif self.__cloudera_version(self.__hadoop_version):
      candidate = '/etc/hadoop-%d.%d/conf' % self.__hadoop_version[0:2]
      if os.path.isdir(candidate):
        self.__hadoop_conf = candidate

    if self.__hadoop_conf is None: # still no conf dir.  Try in hadoop home
      if self.__hadoop_home is not None:
        candidate = os.path.join(self.__hadoop_home, 'conf')
        if os.path.isdir(candidate):
          self.__hadoop_conf = candidate
    # else give up on hadoop conf

    self.__initialized = True
