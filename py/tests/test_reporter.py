from distutils.spawn import find_executable
import json
import math
import os
import os.path
import shutil
import subprocess
import tempfile
import unittest
import valhalla


#get the distance between a lat,lon using equirectangular approximation
rad_per_deg = math.pi / 180
meters_per_deg = 20037581.187 / 180
def difference(a, b):
  x = (a['lon'] - b['lon']) * meters_per_deg * math.cos(.5 * (a['lat'] + b['lat']) * rad_per_deg)
  y = (a['lat'] - b['lat']) * meters_per_deg
  return x * x + y * y, a['time'] - b['time']


#get the length of a series of points
def sum_difference(p):
  l = 0
  e = 0
  for i in range(1, len(p)):
    d, t = difference(p[i], p[i - 1])
    l += d
    e += t
  return l, e


class ReporterTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        for cmd_name in ['valhalla_build_tiles',
                         'valhalla_build_config',
                         'osmium',
                         'osmlr',
                         'valhalla_associate_segments',
                         'tar']:
            path = find_executable(cmd_name)
            if path is None:
                raise Exception('Unable to find %s' % cmd_name)
            attr = '_%s_bin' % cmd_name
            setattr(cls, attr, path)

    def setUp(self):
        self._prev_dir = os.getcwd()
        self._base_dir = tempfile.mkdtemp()
        os.chdir(self._base_dir)

    def tearDown(self):
        shutil.rmtree(self._base_dir)
        os.chdir(self._prev_dir)

    def _build_config(self):
        config = subprocess.check_output(
            [ReporterTest._valhalla_build_config_bin,
             '--mjolnir-tile-dir', self._base_dir])
        config_file = os.path.join(self._base_dir, 'config.json')
        with open(config_file, 'w') as fh:
            fh.write(config)
        return config_file

    def _build_pbf(self, xml):
        xml_file = os.path.join(self._base_dir, 'input.osm')
        pbf_file = os.path.join(self._base_dir, 'input.osm.pbf')
        with open(xml_file, 'w') as fh:
            fh.write(xml)
        subprocess.check_call(
            [ReporterTest._osmium_bin, 'cat',
             '--output-format=.pbf',
             '--output=%s' % pbf_file,
             '--overwrite',
             '--input-format=.osm',
             xml_file])
        return pbf_file

    def _build_tiles(self, config_file, pbf_file):
        subprocess.check_call(
            [ReporterTest._valhalla_build_tiles_bin,
             '--config', config_file,
             pbf_file])

    def _build_tiles_tar(self):
        files = []
        for dirpath, dirnames, filenames in os.walk('.'):
            for filename in filenames:
                if filename.endswith('.gph'):
                    fullpath = os.path.join(dirpath, filename)
                    files.append(fullpath)
        subprocess.check_call(
            [ReporterTest._tar_bin, 'cf', 'tiles.tar'] +
            list(sorted(files)))

    def _build_osmlr(self, config_file):
        osmlr_tile_dir = os.path.join(self._base_dir, 'osmlr_tiles')

        subprocess.check_call(
            [ReporterTest._osmlr_bin,
             '--config', config_file,
             '-T', osmlr_tile_dir])

        subprocess.check_call(
            [ReporterTest._valhalla_associate_segments_bin,
             '--config', config_file,
             '--osmlr-tile-dir', osmlr_tile_dir])

    def testSomething(self):
        config_file = self._build_config()

        pbf_file = self._build_pbf('''
<osm version="0.6">
  <node id="1" lon="-0.47138214111328125" lat="51.55909024804244"/>
  <node id="2" lon="-0.48090934753417974" lat="51.55999738544502"/>
  <node id="3" lon="-0.49163818359375" lat="51.56095786414904"/>
  <node id="4" lon="-0.5015945434570312" lat="51.56170488911645"/>
  <node id="5" lon="-0.510263442993164" lat="51.56170488911645"/>
  <node id="6" lon="-0.517730712890625" lat="51.56095786414904"/>
  <node id="7" lon="-0.5251979827880859" lat="51.56031754726698"/>
  <node id="8" lon="-0.5312061309814453" lat="51.56069106654385"/>
  <node id="9" lon="-0.5395317077636719" lat="51.56181160596717"/>
  <node id="10" lon="-0.5475997924804686" lat="51.56277204635416"/>
  <node id="11" lon="-0.5278587341308594" lat="51.55674227897659"/>
  <way id="1">
    <nd ref="1"/>
    <nd ref="2"/>
    <nd ref="3"/>
    <nd ref="4"/>
    <tag k="highway" v="primary"/>
    <tag k="name" v="A40"/>
  </way>
  <way id="2">
    <nd ref="4"/>
    <nd ref="5"/>
    <nd ref="6"/>
    <nd ref="7"/>
    <tag k="highway" v="motorway"/>
    <tag k="name" v="M40"/>
  </way>
  <way id="3">
    <nd ref="7"/>
    <nd ref="8"/>
    <nd ref="9"/>
    <nd ref="10"/>
    <tag k="highway" v="motorway"/>
    <tag k="name" v="M40"/>
  </way>
  <way id="3">
    <nd ref="7"/>
    <nd ref="11"/>
    <tag k="highway" v="motorway_link"/>
  </way>
</osm>
''')

        trace = {
            'uuid': '',
            'trace': [
                { 'lon': -0.5015945434570312, 'lat': 51.56170488911645, 'time': 1494419212 },
                { 'lon': -0.5102634429931640, 'lat': 51.56170488911645, 'time': 1494419220 },
                { 'lon': -0.5177307128906250, 'lat': 51.56095786414904, 'time': 1494419228 },
                { 'lon': -0.5251979827880859, 'lat': 51.56031754726698, 'time': 1494419236 },
                { 'lon': -0.5312061309814453, 'lat': 51.56069106654385, 'time': 1494419244 }
            ]
        }

        sq_distance, elapsed_time = sum_difference(trace['trace'])
        trace['sq_distance'] = sq_distance
        trace['elapsed_time'] = elapsed_time

        self._build_tiles(config_file, pbf_file)
        self._build_osmlr(config_file)
        self._build_tiles_tar()
        self.assertTrue(os.access('tiles.tar', os.F_OK))

        valhalla.Configure(config_file)
        matcher = valhalla.SegmentMatcher()
        result = matcher.Match(json.dumps(trace, separators=(',', ':')))
        segments = json.loads(result)

        segs = segments.get('segments')
        self.assertTrue(segs is not None)
        self.assertEqual(3, len(segs))
        self.assertEqual(1494419212, segs[0]['start_time'])
        self.assertEqual(segs[0]['end_time'], segs[1]['start_time'])
        self.assertEqual(segs[0]['end_shape_index'],
                         segs[1]['begin_shape_index'])
        self.assertEqual(segs[1]['end_time'], segs[2]['start_time'])
        self.assertEqual(segs[1]['end_shape_index'],
                         segs[2]['begin_shape_index'])
        self.assertEqual(-1, segs[2]['end_time'])
        self.assertEqual(-1, segs[2]['length'])
